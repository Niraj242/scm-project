import os
import re
import pandas as pd
import requests
import io
import gc
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

FAM_REGEX = re.compile(r'(\d{3,5})')

# Hardcoded Matrix from User Chart Image
OPERATION_EXCLUSIONS = {
    '1': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    '2': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    '4': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    '5': {'OD': ['IR']},
    '8': {'OD': ['IR']},
    '11': {'OD': ['IR']},
    '12': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    '13': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    'T1': {'OD': ['IR']},
    'T2': {'OD': ['IR']},
    'T3': {'OD': ['IR']},
    'T4': {'OD': ['IR']},
    'T5': {'OD': ['IR']},
    'T6': {'OD': ['IR']},
    'T7': {'OD': ['IR']},
    'T8': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    'T9': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
    'T10': {'OD': ['IR']},
    'T11': {'FACE': ['IR', 'OR'], 'OD': ['IR', 'OR']},
}

# The 7 specific furnaces strictly enforced
FURNACE_SPECS = {
    "AICHELIN.(896)": 350.0,
    "CASTLINK FURNACE( 1018 )": 250.0,
    "ROLLER FURNACE ( 148 )": 250.0,
    "SIMPLICITY FURNACE(1238)": 180.0,
    "BIRLEC FURNACE   ( 1158 )": 170.0,
    "SHOEI FURNACE    ( 1062 )": 350.0,
    "AICHELIN UNITHERM ( 2033 )": 250.0
}

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

def normalize_channel(ch_str):
    ch = str(ch_str).strip().upper()
    ch = ch.replace("CH", "").replace("CHANNEL", "").strip()
    if ch.isdigit(): return str(int(ch))
    return ch

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if "INDUSTRILA" in text: text = text.replace("INDUSTRILA", "INDUSTRIAL")
    if "AUTOMOTIVE" in text: return None
    if not text or text in ["NAN", "NONE", "", "UNKNOWN"]: return None
    
    if "HUB" in text:
        match_hub = re.search(r'(T?\s*HUB\s*\d+\.?\d*)', text)
        if match_hub: return match_hub.group(1).replace(" ", "")
        return "HUB"
        
    if text.startswith("T ") or re.match(r'^T\d+', text):
        match_t = re.search(r'(T\s*\d+)', text)
        if match_t: return match_t.group(1).replace(" ", "")
        return "T"

    t_norm = text.replace("-", " ").replace("_", " ").replace("/", " ")
    words = t_norm.split()
    
    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    
    if "BT" in words or text.startswith("BT") or "-BT" in text or " BT" in text: base = f"BT-{base}"
    elif "BB" in words or text.startswith("BB") or "-BB" in text or " BB" in text: base = f"BB-{base}"
    elif "UC" in text:
        match_uc = re.search(r'(UC\s*\d+)', text)
        if match_uc: base = match_uc.group(1).replace(" ", "")
        
    return base

def normalize_fam_key(text):
    match = re.search(r'(\d+)', str(text))
    return str(int(match.group(1))) if match else str(text).strip().upper()

def safe_float(val):
    if pd.isna(val) or val is None: return 0.0
    try:
        s_val = str(val).replace(',', '').strip().lower()
        if s_val in ['nan', 'none', '', 'null']: return 0.0
        return float(s_val)
    except Exception:
        return 0.0

def is_target_date(val, target_date):
    if val is None or pd.isna(val): return False
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.day == target_date.day and val.month == target_date.month
        
    v_str = str(val).strip().upper()
    for symbol in ['-', '/', '.', '_', ':', ' ']: v_str = v_str.replace(symbol, ' ')
    tokens = v_str.split()
    
    day_str = str(target_date.day)
    day_padded = f"{target_date.day:02d}"
    
    if day_str in tokens or day_padded in tokens:
        month_str = target_date.strftime("%b").upper()
        if any(m in v_str for m in ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]):
            return month_str in v_str
        return True
    return False

def load_excel_all_sheets(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "": return None, logs
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None, logs
        content = io.BytesIO(resp.content)
        try:
            return pd.read_excel(content, sheet_name=None, header=None, engine='calamine'), logs
        except Exception:
            return pd.read_excel(content, sheet_name=None, header=None), logs
    except Exception as e:
        return None, [f"[{file_label}] ERR: {str(e)}"]

def get_rate_for_part(fam, p_code, rates):
    fam_key = normalize_fam_key(fam)
    if f"{fam_key}_{p_code}" in rates: return rates[f"{fam_key}_{p_code}"]
    exact_key = f"{str(fam).strip().upper()}_{p_code}"
    if exact_key in rates: return rates[exact_key]
    return 0.0 

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = [] 
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # 1. PARSE ZEROSET DEMANDS
        channel_demands = {} 
        sheets_zero, logs1 = load_excel_all_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                r_idx, type_col_idx, c1, c2 = None, None, None, None
                
                for i in range(min(25, len(df_zero))):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[i].values]
                    row_joined = " ".join(row_strs)
                    
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF", "PART NO", "BRG NO"] or "TYPE" in val: 
                                type_col_idx = j
                                break
                                
                    if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                        r_idx = i
                        for j, val in enumerate(df_zero.iloc[i].values):
                            if is_target_date(val, req_date): c1 = j
                            if is_target_date(val, next_date): c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None and (c1 is not None or c2 is not None):
                    for idx in range(r_idx + 1, len(df_zero)):
                        cell_val = df_zero.iloc[idx, type_col_idx]
                        if pd.notna(cell_val) and str(cell_val).strip() != "":
                            active_raw_type = str(cell_val).strip().upper()
                            
                        if not active_raw_type: continue
                        fam = parse_family(active_raw_type)
                        if not fam: continue
                        
                        val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        r1 = val1 * 1000 if 0 < val1 <= 70 else val1
                        r2 = val2 * 1000 if 0 < val2 <= 70 else val2
                        combined_qty = r1 + r2
                        
                        if combined_qty > 0:
                            if fam not in channel_demands: 
                                channel_demands[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            
                            is_ir = any(x in active_raw_type for x in ['IR', '120'])
                            is_or = any(x in active_raw_type for x in ['OR', '100', '010'])
                            if not is_ir and not is_or:
                                is_ir = True
                                is_or = True
                                
                            if is_ir: channel_demands[fam]['IR'] += combined_qty
                            if is_or: channel_demands[fam]['OR'] += combined_qty
                                
            del sheets_zero
            gc.collect()

        # 2. PARSE BOX MATRIX WITH ADVANCED FALLBACKS
        box_matrix = {}
        sheets_box, _ = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box:
            # Fallback parsing first (e.g. BB1 4719 (19/40) 10K)
            for s_name in ["BOX PER DAY DGBB", "BOX PER DAY TRB"]:
                if s_name in sheets_box:
                    df_f = sheets_box[s_name].fillna('').astype(str)
                    for r in range(len(df_f)):
                        for c in range(len(df_f.columns)):
                            val = df_f.iloc[r, c].strip().upper()
                            if not val or val in ['NAN', 'NONE']: continue
                            match = re.search(r'\(\s*([\d\.]+)\s*/\s*([\d\.]+)\s*\)\s*([\d\.]+)K', val)
                            if match:
                                ir_bx = safe_float(match.group(1))
                                or_bx = safe_float(match.group(2))
                                qty = safe_float(match.group(3)) * 1000
                                if ir_bx > 0 and or_bx > 0 and qty > 0:
                                    name_part = val[:match.start()].strip()
                                    fam = parse_family(name_part)
                                    if fam:
                                        box_matrix[fam] = {'IR': qty/ir_bx, 'OR': qty/or_bx}

            # Primary sheet overwrites fallbacks
            if 'RING PER BOX.' in sheets_box:
                df_box = sheets_box['RING PER BOX.'].fillna('')
                for idx in range(1, len(df_box)):
                    row_vals = list(df_box.iloc[idx])
                    for i in range(0, len(row_vals) - 2, 3):
                        fam_raw = str(row_vals[i]).strip()
                        if not fam_raw: continue
                        fam = parse_family(fam_raw)
                        if fam:
                            or_qty = safe_float(row_vals[i+1])
                            ir_qty = safe_float(row_vals[i+2])
                            if fam not in box_matrix: box_matrix[fam] = {}
                            if or_qty > 0: box_matrix[fam]['OR'] = or_qty
                            if ir_qty > 0: box_matrix[fam]['IR'] = ir_qty
            del sheets_box
            gc.collect()

        # 3. COMPUTE BUFFERS & DEMANDS
        buffers_by_fam = {}
        BUFFER_MAP = {
            'ch_buffer_1': ('type_1', 'CH'), 'ch_buffer_2': ('next_type_1', 'CH'),
            'od_buffer_1': ('type_2', 'OD'), 'od_buffer_2': ('next_type_2', 'OD'),
            'face_buffer_1': ('type_3', 'FACE'), 'face_buffer_2': ('type_4', 'FACE'),
            'ht_buffer_1': ('type_5', 'HT'), 'ht_buffer_2': ('type_6', 'HT')
        }

        for buf_prefix, (type_prefix, stage) in BUFFER_MAP.items():
            for key, val in payload.entries.items():
                if key.startswith(type_prefix + '_'):
                    parts = key.split('_')
                    if len(parts) < 3: continue
                    col_channel, sub_ring_type = parts[-2], parts[-1]
                    
                    fam = parse_family(val)
                    if not fam: continue
                    buf_val = safe_float(payload.entries.get(f"{buf_prefix}_{col_channel}_{sub_ring_type}", 0))
                    if buf_val <= 0: continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}, 'HT': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[fam][stage][sub_ring_type] += buf_val

        face_req, od_req, ht_req = {}, {}, {}
        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100.0)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100.0)
            
            req_boxes_ir = demands['IR'] / rpb_ir
            req_boxes_or = demands['OR'] / rpb_or
            
            def get_buf_boxes(stage, side, base_boxes, rpb_rate):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(side, 0)
                if payload.unit_mode == 'Days': return raw_buf * base_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb_rate
                return raw_buf 
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_boxes_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_boxes_or, rpb_or)
            od_buf_ir = get_buf_boxes('OD', 'IR', req_boxes_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_boxes_or, rpb_or)
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_boxes_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_boxes_or, rpb_or)

            net_face_ir = max(0.0, req_boxes_ir - face_buf_ir)
            net_face_or = max(0.0, req_boxes_or - face_buf_or)
            
            net_od_ir = max(0.0, req_boxes_ir - od_buf_ir)
            net_od_or = max(0.0, req_boxes_or - od_buf_or)
            
            net_ht_ir = max(0.0, req_boxes_ir - ch_buf_ir)
            net_ht_or = max(0.0, req_boxes_or - ch_buf_or)

            if net_face_ir > 0 or net_face_or > 0: 
                face_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': demands['channel']}
            if net_od_ir > 0 or net_od_or > 0: 
                od_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': demands['channel']}
            if net_ht_ir > 0 or net_ht_or > 0: 
                ht_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'rings': {'IR': net_ht_ir * rpb_ir, 'OR': net_ht_or * rpb_or}, 'channel': demands['channel']}

        # 4. PARSE MACHINE PRODUCTION DATA (Robust rate matching)
        weight_matrix, furnace_map, machines_data = {}, {}, {'FACE': {}, 'OD': {}}
        sheets_prod, logs3 = load_excel_all_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS']
                df_w.columns = [str(x).strip().upper() for x in df_w.iloc[0]]
                for idx, r in df_w.iloc[1:].iterrows():
                    if pd.notna(r.get('TYPE')):
                        part_code = 'OR' if str(r.get('IR/OR')) == '100' else 'IR'
                        fam = parse_family(r.get('TYPE'))
                        if fam: weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('WEIGHT PER RING', 0.15))

            fur_sheet_key = next((k for k in sheets_prod.keys() if 'FURNACE' in str(k).upper()), None)
            if fur_sheet_key:
                df_f = sheets_prod[fur_sheet_key]
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for idx, r in df_f.iloc[1:].iterrows():
                    fam_val = r.get('TYPE', r.iloc[0] if len(r) > 0 else '')
                    fam = parse_family(fam_val)
                    if fam: 
                        fur_col = next((c for c in df_f.columns if 'FURNACE' in c), None)
                        fur_raw = str(r[fur_col]) if fur_col else str(r.iloc[1] if len(r) > 1 else '')
                        furnaces = [f.strip() for f in re.split(r'[,/|]', fur_raw) if f.strip() and f.strip().upper() != 'NAN']
                        if furnaces: furnace_map[fam] = furnaces
            
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                
                vals = df_m.values
                num_rows = vals.shape[0]
                
                for r in range(num_rows):
                    row = vals[r]
                    has_machine = False
                    row_cells = []
                    for val in row:
                        if pd.notna(val) and val != '':
                            val_str = str(val).strip()
                            row_cells.append(val_str)
                            if 'MACHINE' in val_str.upper() or 'M/C' in val_str.upper():
                                has_machine = True
                                
                    if has_machine:
                        m_num = row_cells[1] if len(row_cells) > 1 else f"MC_{r}"
                        m_type = "UNKNOWN"
                        m_num_upper = m_num.upper()
                        sheet_upper = sheet_name.upper()
                        
                        if "FACE" in sheet_upper or "DDS" in m_num_upper or "BG" in m_num_upper: 
                            m_type = "FACE"
                        elif "OD" in sheet_upper or "CL" in m_num_upper or "CELL" in m_num_upper or "+" in m_num: 
                            m_type = "OD"
                            
                        if m_type in ['FACE', 'OD']:
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                                
                            header_idx = -1
                            for offset in range(1, 6):
                                if r + offset >= num_rows: break
                                h_row = [str(x).strip().upper() for x in vals[r + offset] if pd.notna(x)]
                                if 'TYPE' in h_row or 'BEARING' in h_row:
                                    header_idx = r + offset
                                    break
                                    
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in vals[header_idx]]
                                
                                type_col, part_col, rate_col, rpb_col = -1, -1, -1, -1
                                rate_is_rings = False
                                
                                for idx, h in enumerate(headers):
                                    if 'TYPE' in h or 'BEARING' in h: type_col = idx
                                    elif 'PART' in h: part_col = idx
                                    elif 'BOXES/HR' in h or 'BOX/HR' in h or 'BOXES/HOUR' in h: 
                                        rate_col = idx
                                        rate_is_rings = False
                                    elif 'STD' in h or 'RINGS/HR' in h or 'RINGS / HR' in h:
                                        if rate_col == -1: 
                                            rate_col = idx
                                            rate_is_rings = True
                                    elif 'RING' in h and 'BOX' in h: 
                                        rpb_col = idx
                                        
                                if type_col != -1:
                                    for offset_row in range(header_idx + 1, min(header_idx + 35, num_rows)): 
                                        b_row = vals[offset_row]
                                        if type_col >= len(b_row) or pd.isna(b_row[type_col]) or str(b_row[type_col]).strip() == '':
                                            continue
                                            
                                        raw_type = str(b_row[type_col]).strip()
                                        fam = parse_family(raw_type)
                                        if not fam: continue
                                        
                                        part_val = str(b_row[part_col]).strip().upper() if part_col != -1 else ""
                                        
                                        p_codes = []
                                        if '100' in part_val or 'OR' in part_val or '010' in part_val: p_codes.append('OR')
                                        if '120' in part_val or 'IR' in part_val: p_codes.append('IR')
                                        if not p_codes: p_codes = ['IR', 'OR']
                                        
                                        rate_val = safe_float(b_row[rate_col]) if rate_col != -1 and rate_col < len(b_row) else 0.0
                                        
                                        if rate_val > 0:
                                            fam_key = normalize_fam_key(fam)
                                            if rate_is_rings:
                                                rpb_val = safe_float(b_row[rpb_col]) if rpb_col != -1 and rpb_col < len(b_row) else 0.0
                                                for pc in p_codes:
                                                    final_rpb = rpb_val if rpb_val > 0 else box_matrix.get(fam, {}).get(pc, 100.0)
                                                    boxes_hr = rate_val / final_rpb
                                                    machines_data[m_type][m_num]['rates'][f"{fam_key}_{pc}"] = boxes_hr
                                                    machines_data[m_type][m_num]['rates'][f"{str(fam).strip().upper()}_{pc}"] = boxes_hr
                                            else:
                                                for pc in p_codes:
                                                    machines_data[m_type][m_num]['rates'][f"{fam_key}_{pc}"] = rate_val
                                                    machines_data[m_type][m_num]['rates'][f"{str(fam).strip().upper()}_{pc}"] = rate_val

            del sheets_prod
            gc.collect()

        # 5. GRINDING ALLOCATION
        def allocate_grinding(m_type, demands_dict):
            allocated_result = {m_num: {"machine": m_num, "rows": []} for m_num in machines_data.get(m_type, {})}
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            
            machine_clocks = {m_num: m_info['avail_hours'] for m_num, m_info in machines_data.get(m_type, {}).items()}
            machine_last_fam = {m_num: None for m_num in machines_data.get(m_type, {})}
            
            for fam, data in sorted_fams:
                ch_normalized = normalize_channel(data['channel'])
                for p_code in ['IR', 'OR']:
                    if ch_normalized in OPERATION_EXCLUSIONS and p_code in OPERATION_EXCLUSIONS[ch_normalized].get(m_type, []):
                        continue 
                            
                    boxes_needed = data[p_code]
                    if boxes_needed <= 0: continue
                    
                    candidates = []
                    for m_num, m_info in machines_data.get(m_type, {}).items():
                        rate = get_rate_for_part(fam, p_code, m_info.get('rates', {}))
                        if rate > 0 and machine_clocks[m_num] > 0:
                            candidates.append((m_num, rate))
                    
                    placed = False
                    if candidates:
                        candidates.sort(key=lambda x: x[1], reverse=True) 
                        for m_num, rate in candidates:
                            if boxes_needed <= 0: break
                            if machine_clocks[m_num] <= 0: continue
                            
                            hours_left = machine_clocks[m_num]
                            current_fam = machine_last_fam[m_num]
                            setup_cost = 2.0 if (current_fam and current_fam != fam) else 0.0
                            
                            if hours_left <= setup_cost:
                                machine_clocks[m_num] = 0.0
                                continue
                                
                            hours_left -= setup_cost
                            time_required = boxes_needed / rate
                            
                            if time_required <= hours_left:
                                boxes_needed = 0.0
                                hours_left -= time_required
                            else:
                                boxes_needed -= (hours_left * rate)
                                hours_left = 0.0
                                
                            machine_clocks[m_num] = hours_left
                            machine_last_fam[m_num] = fam
                            placed = True
                            
                            allocated_result[m_num]["rows"].append({
                                "part": f"{fam} {p_code}",
                                "std_box": str(round(rate, 1)),
                                "p_2nd": "1" if len(allocated_result[m_num]["rows"]) == 0 else "",
                                "p_3rd": "1" if len(allocated_result[m_num]["rows"]) == 1 else "",
                                "alert": False,
                                "p_label": f"P{len(allocated_result[m_num]['rows']) + 1}"
                            })
                    
                    if boxes_needed > 0.5:
                        reason = "Capacity Exhausted" if placed else "Missing Machine Rate (0.0)"
                        unscheduled.append({ "stage": m_type, "part": f"{fam} {p_code}", "missed_boxes": f"{round(boxes_needed, 1)} boxes - {reason}" })

            return list(allocated_result.values())

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # 6. HEAT TREATMENT ROUTING (Chunking Logic)
        furnace_clocks = {f: {"avail_hours": 20.5, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}

        for fam, data in sorted(ht_req.items(), key=lambda x: x[1]['rings']['IR'] + x[1]['rings']['OR'], reverse=True):
            rings_ir = data['rings']['IR']
            rings_or = data['rings']['OR']
            if rings_ir <= 0 and rings_or <= 0: continue
            
            w_ir = weight_matrix.get(f"{fam}_IR", 0.15)
            w_or = weight_matrix.get(f"{fam}_OR", 0.15)
            
            for p_code, total_qty in [('IR', rings_ir), ('OR', rings_or)]:
                if total_qty <= 0: continue
                unit_weight = w_or if p_code == 'OR' else w_ir
                
                preferred_furnaces = furnace_map.get(fam, [])
                matched_furnaces = []
                for pf in preferred_furnaces:
                    for f_name in FURNACE_SPECS.keys():
                        if pf.upper()[:4] in f_name.upper(): matched_furnaces.append(f_name)
                
                if not matched_furnaces: matched_furnaces = list(FURNACE_SPECS.keys())
                
                remaining_qty = total_qty
                
                while remaining_qty > 0.5:
                    best_furnace = None
                    best_avail = -1
                    
                    for f_name in matched_furnaces:
                        ctx = furnace_clocks[f_name]
                        setup = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                        if (ctx["avail_hours"] - setup) > 0 and (ctx["avail_hours"] - setup) > best_avail:
                            best_avail = ctx["avail_hours"] - setup
                            best_furnace = f_name
                            
                    if not best_furnace:
                        for f_name in FURNACE_SPECS.keys():
                            if f_name in matched_furnaces: continue
                            ctx = furnace_clocks[f_name]
                            setup = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                            if (ctx["avail_hours"] - setup) > 0 and (ctx["avail_hours"] - setup) > best_avail:
                                best_avail = ctx["avail_hours"] - setup
                                best_furnace = f_name
                    
                    if not best_furnace:
                        unscheduled.append({ "stage": "HT", "part": f"{fam} {p_code}", "missed_boxes": "Capacity Exceeded" })
                        break 
                        
                    ctx = furnace_clocks[best_furnace]
                    kg_per_hr = FURNACE_SPECS[best_furnace]
                    setup_penalty = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                    
                    remaining_weight_kg = remaining_qty * unit_weight
                    time_needed = remaining_weight_kg / kg_per_hr
                    
                    if time_needed <= (ctx["avail_hours"] - setup_penalty):
                        ctx["avail_hours"] -= (time_needed + setup_penalty)
                        ctx["current_fam"] = fam
                        ctx["rows"].append({
                            "part": f"{fam}-{p_code}", 
                            "qty": str(int(remaining_qty)), 
                            "cha": data['channel'],
                            "rate": f"{round(remaining_weight_kg, 1)} kg",
                            "alert": False 
                        })
                        remaining_qty = 0
                    else:
                        max_weight = (ctx["avail_hours"] - setup_penalty) * kg_per_hr
                        max_qty = max_weight / unit_weight
                        
                        ctx["avail_hours"] = 0.0
                        ctx["current_fam"] = fam
                        ctx["rows"].append({
                            "part": f"{fam}-{p_code}", 
                            "qty": str(int(max_qty)), 
                            "cha": data['channel'],
                            "rate": f"{round(max_weight, 1)} kg",
                            "alert": False 
                        })
                        remaining_qty -= max_qty

        ht_formatted = [
            {"furnace": fur, "capacity": f"Total Cap: {int(f_data['capacity'])} kg/hr", "rows": f_data["rows"]}
            for fur, f_data in furnace_clocks.items()
        ]

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {
                "face_grinding": final_face,
                "od_grinding": final_od,
                "heat_treatment": ht_formatted,
                "unscheduled": unscheduled
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs + [f"CRITICAL ERROR: {traceback.format_exc()}"], "detail": str(e)}
