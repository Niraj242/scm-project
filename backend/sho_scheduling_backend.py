import os
import re
import math
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

# The 7 specific furnaces requested by the user
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

def extract_num(text):
    match = re.search(r'(\d{4,5})', str(text))
    if match: return match.group(1)
    match_hub = re.search(r'HUB\s*(\d+\.?\d*)', str(text).upper())
    if match_hub: return "HUB" + match_hub.group(1).replace(" ", "")
    return str(text)

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
    exact_key = f"{fam}_{p_code}"
    if exact_key in rates: return rates[exact_key]
    
    num1 = extract_num(fam)
    for k, v in rates.items():
        if not k.endswith(f"_{p_code}"): continue
        k_fam = k.split('_')[0]
        num2 = extract_num(k_fam)
        if (num1 and num1 != fam and num1 == num2) or (num1 in k_fam) or (k_fam in num1):
            return v
    return 0.0 

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # 1. PARSE ZEROSET
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
                            active_raw_type = str(cell_val).strip()
                            
                            fam = parse_family(active_raw_type)
                            if not fam: continue
                            
                            val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                            val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                            
                            r1 = val1 * 1000 if val1 > 0 else 0.0
                            r2 = val2 * 1000 if val2 > 0 else 0.0
                            
                            if r1 > 0 or r2 > 0:
                                if fam not in channel_demands: 
                                    channel_demands[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                                
                                combined_qty = r1 + r2
                                channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], combined_qty)
                                channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], combined_qty)
            del sheets_zero
            gc.collect()

        # 2. BOX MATRIX
        box_matrix = {}
        sheets_box, _ = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box and 'RING PER BOX.' in sheets_box:
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
                        box_matrix[fam] = {'OR': or_qty if or_qty > 0 else 100, 'IR': ir_qty if ir_qty > 0 else 100}
            del sheets_box
            gc.collect()

        # 3. BUFFERS
        buffers_by_fam = {}
        BUFFER_MAP = {
            'ch_buffer_1': ('type_1', 'CH'), 'ch_buffer_2': ('next_type_1', 'CH'),
            'od_buffer_1': ('type_2', 'OD'), 'od_buffer_2': ('next_type_2', 'OD'),
            'face_buffer_1': ('type_3', 'FACE'), 'face_buffer_2': ('type_4', 'FACE')
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
                        buffers_by_fam[fam] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[fam][stage][sub_ring_type] += buf_val

        face_req, od_req, ht_req = {}, {}, {}
        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
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
            net_od_ir = max(0.0, net_face_ir - od_buf_ir)
            net_od_or = max(0.0, net_face_or - od_buf_or)
            net_ht_ir = max(0.0, net_od_ir - ch_buf_ir)
            net_ht_or = max(0.0, net_od_or - ch_buf_or)

            if net_face_ir > 0 or net_face_or > 0: face_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': demands['channel']}
            if net_od_ir > 0 or net_od_or > 0: od_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': demands['channel']}
            if net_ht_ir > 0 or net_ht_or > 0: ht_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'rings': {'IR': net_ht_ir * rpb_ir, 'OR': net_ht_or * rpb_or}, 'channel': demands['channel']}

        # 4. EXTREMELY ROBUST PRODUCTION DATA PARSER
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
                        if fam: weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('WEIGHT', r.get('WEIGHT PER RING', 0.15)))

            fur_sheet_key = next((k for k in sheets_prod.keys() if 'FURNACE' in str(k).upper() and 'FLEX' in str(k).upper()), None)
            if fur_sheet_key:
                df_f = sheets_prod[fur_sheet_key]
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for idx, r in df_f.iloc[1:].iterrows():
                    comp_level = str(r.get('COMP LEVEL 1', r.iloc[0] if len(r) > 0 else '')).strip()
                    if not comp_level: continue
                    p_code = 'IR' if comp_level.startswith('IM') else ('OR' if comp_level.startswith('OM') else None)
                    fam = extract_num(comp_level) 
                    if fam and p_code:
                        prim = str(r.get('PRIMARY FURNA', r.get('PRIMARY FURNACE', ''))).strip()
                        alt1 = str(r.get('ALTERNATIVE 1', '')).strip()
                        alt2 = str(r.get('ALTERNATIVE 2', '')).strip()
                        valid_furnaces = []
                        for fn in [prim, alt1, alt2]:
                            matched_fn = next((k for k in FURNACE_SPECS.keys() if fn.upper()[:4] in k.upper()), None)
                            if matched_fn and matched_fn not in valid_furnaces: valid_furnaces.append(matched_fn)
                        if valid_furnaces: furnace_map[f"{fam}_{p_code}"] = valid_furnaces
            
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                
                # Scan entire sheet for tables indicating a machine
                for r in range(len(df_m)):
                    row_vals = [str(x).strip().upper() for x in df_m.iloc[r].values]
                    
                    has_type = any(c == 'TYPE' or 'BEARING' in c for c in row_vals)
                    has_std = any('STD' in c for c in row_vals)
                    has_part = any('PART' in c or '100' in c or '120' in c for c in row_vals)
                    
                    if has_type and (has_std or has_part):
                        # Block identified! Find machine name above it
                        m_num = f"Machine_Block_{r}"
                        for back_r in range(r-1, max(-1, r-5), -1):
                            back_vals = [str(x).strip().upper() for x in df_m.iloc[back_r].values if str(x).strip() not in ['NAN', 'NONE', '']]
                            if back_vals:
                                m_num = back_vals[1] if len(back_vals) > 1 and ('MACHINE' in back_vals[0] or 'M/C' in back_vals[0]) else back_vals[0]
                                break
                                
                        m_type = "UNKNOWN"
                        if "FACE" in sheet_name.upper() or "DDS" in m_num.upper() or "BG" in m_num.upper() or "FACE" in m_num.upper(): m_type = "FACE"
                        elif "OD" in sheet_name.upper() or "CL" in m_num.upper() or "CELL" in m_num.upper() or "+" in m_num or "OD" in m_num.upper(): m_type = "OD"
                        
                        if m_type not in ['FACE', 'OD']:
                            if "FACE" in sheet_name.upper(): m_type = "FACE"
                            elif "OD" in sheet_name.upper(): m_type = "OD"
                            else: continue

                        if m_num not in machines_data[m_type]:
                            machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                        
                        # Pinpoint column indexes
                        type_idx = next((i for i, c in enumerate(row_vals) if c == 'TYPE' or 'BEARING' in c), -1)
                        part_idx = next((i for i, c in enumerate(row_vals) if 'PART' in c), -1)
                        std_idx = next((i for i, c in enumerate(row_vals) if 'STD' in c), -1)
                        rpb_idx = next((i for i, c in enumerate(row_vals) if 'RING' in c and 'BOX' in c), -1)
                        
                        for data_r in range(r+1, min(r+60, len(df_m))):
                            d_vals = [str(x).strip().upper() for x in df_m.iloc[data_r].values]
                            if type_idx == -1 or len(d_vals) <= type_idx: continue
                            
                            raw_type = d_vals[type_idx]
                            if not raw_type or raw_type in ['NAN', 'NONE', '']: continue
                            
                            fam = parse_family(raw_type)
                            if not fam: continue
                            
                            p_codes = []
                            if part_idx != -1 and len(d_vals) > part_idx:
                                p_val = d_vals[part_idx]
                                if '100' in p_val or 'OR' in p_val: p_codes.append('OR')
                                if '120' in p_val or 'IR' in p_val or '010' in p_val: p_codes.append('IR')
                            if not p_codes: p_codes = ['IR', 'OR']
                            
                            std_hr = safe_float(d_vals[std_idx]) if std_idx != -1 and len(d_vals) > std_idx else 0.0
                            if std_hr > 0:
                                for pc in p_codes:
                                    rpb = 100.0
                                    if rpb_idx != -1 and len(d_vals) > rpb_idx:
                                        local_rpb = safe_float(d_vals[rpb_idx])
                                        if local_rpb > 0: rpb = local_rpb
                                        else: rpb = box_matrix.get(fam, {}).get(pc, 100.0)
                                    else:
                                        rpb = box_matrix.get(fam, {}).get(pc, 100.0)
                                        
                                    rate_boxes = std_hr / rpb
                                    machines_data[m_type][m_num]['rates'][f"{fam}_{pc}"] = rate_boxes
            del sheets_prod
            gc.collect()

        # 5. UNLIMITED GRINDING SCHEDULER
        def allocate_grinding(m_type, demands_dict):
            # Guarantee every detected machine displays in the UI
            allocated_result = {m_num: {"machine": m_num, "rows": []} for m_num in machines_data.get(m_type, {})}
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            machine_clocks = {m_num: m_info['avail_hours'] for m_num, m_info in machines_data.get(m_type, {}).items()}
            machine_last_fam = {m_num: None for m_num in machines_data.get(m_type, {})}
            
            for fam, data in sorted_fams:
                ch_normalized = normalize_channel(data['channel'])
                for p_code in ['IR', 'OR']:
                    if ch_normalized in OPERATION_EXCLUSIONS and p_code in OPERATION_EXCLUSIONS[ch_normalized].get(m_type, []):
                        continue # Bypassed based on User Matrix
                            
                    boxes_needed = data[p_code]
                    if boxes_needed <= 0: continue
                    
                    candidates = []
                    for m_num, m_info in machines_data.get(m_type, {}).items():
                        rate = get_rate_for_part(fam, p_code, m_info.get('rates', {}))
                        if rate > 0 and machine_clocks[m_num] > 0:
                            candidates.append((m_num, rate))
                    
                    candidates.sort(key=lambda x: x[1], reverse=True) # Send to fastest machine
                    placed = False
                    
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
                        reason = "Capacity Exhausted" if placed else "Missing Rate Data"
                        unscheduled.append({ "stage": m_type, "part": f"{fam} {p_code}", "missed_boxes": f"{round(boxes_needed, 1)} bx ({reason})" })

            return list(allocated_result.values())

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # 6. HEAT TREATMENT ROUTING (7 FURNACES | 20.5 HR AVAIL | 0.5 HR SETUP)
        # Latency = 3.5 hrs. So 24.0 - 3.5 = 20.5 total allocatable hours. 0.5 hr switch.
        furnace_clocks = {f: {"avail_hours": 20.5, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}

        for fam, data in sorted(ht_req.items(), key=lambda x: x[1]['rings']['IR'] + x[1]['rings']['OR'], reverse=True):
            for p_code, qty in [('IR', data['rings']['IR']), ('OR', data['rings']['OR'])]:
                if qty <= 0: continue
                
                search_key = f"{extract_num(fam)}_{p_code}"
                preferred_furnaces = furnace_map.get(search_key, [])
                if not preferred_furnaces:
                    preferred_furnaces = list(FURNACE_SPECS.keys())
                
                unit_weight = weight_matrix.get(f"{fam}_{p_code}", 0.15)
                total_weight_kg = qty * unit_weight
                
                scheduled_flag = False
                for f_name in preferred_furnaces:
                    if f_name not in furnace_clocks: continue
                    
                    kg_per_hr = FURNACE_SPECS[f_name]
                    time_needed = total_weight_kg / kg_per_hr
                    ctx = furnace_clocks[f_name]
                    
                    setup_penalty = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                    
                    if (ctx["avail_hours"] - setup_penalty) >= time_needed:
                        ctx["avail_hours"] -= (time_needed + setup_penalty)
                        ctx["current_fam"] = fam
                        ctx["rows"].append({
                            "part": f"{fam}-{p_code}", 
                            "qty": str(int(qty)), 
                            "cha": data['channel'],
                            "rate": f"{round(total_weight_kg, 1)} kg", 
                            "alert": False 
                        })
                        scheduled_flag = True
                        break
                        
                if not scheduled_flag:
                    unscheduled.append({ "stage": "HT", "part": f"{fam} {p_code}", "missed_boxes": "Capacity Exceeded" })

        # Formatting Output with the 7 strict furnaces 
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
