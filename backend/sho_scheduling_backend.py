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
    if not text or text in ["NAN", "NONE", "", "UNKNOWN", "TYPE"]: return None
    
    # 1. Hardcoded fixes for known unusual names
    if "BB1B420205" in text: return "UC205"
    
    # 2. Aggressively strip known prefixes
    for prefix in ["BB1", "BTH", "BT-", "BB-"]:
        if text.startswith(prefix):
            # Only remove the exact prefix at the start
            text = text[len(prefix):].strip()
            
    # Safe check in case stripping leaves the string totally empty
    if not text: return None
            
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
    # Safe fallback if split fails for some unforeseen string condition
    base = match.group(1) if match else (text.split()[0].split('-')[0] if text.split() else text)
    
    if "BT" in words or text.startswith("BT") or " BT" in text: base = f"BT-{base}"
    elif "BB" in words or text.startswith("BB") or " BB" in text: base = f"BB-{base}"
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
        # Using default engine to ensure 100% stability and prevent 502 crashes
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
                    active_raw_type = None
                    for idx in range(r_idx + 1, len(df_zero)):
                        cell_val = df_zero.iloc[idx, type_col_idx]
                        if pd.notna(cell_val) and str(cell_val).strip() != "":
                            active_raw_type = str(cell_val).strip()
                            
                        if not active_raw_type: continue
                        fam = parse_family(active_raw_type)
                        if not fam: continue
                        
                        val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0 or r2 > 0:
                            if r1 == 0 and r2 > 0: continue 
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
        if sheets_box:
            # Primary Source
            if 'RING PER BOX.' in sheets_box:
                df_box = sheets_box['RING PER BOX.'].fillna('')
                
                # Start at index 2 to bypass the main headers and subheaders
                for idx in range(2, len(df_box)):
                    row_vals = list(df_box.iloc[idx])
                    for i in range(0, len(row_vals) - 2, 3):
                        fam_raw = str(row_vals[i]).strip()
                        if not fam_raw or fam_raw.upper() in ["TYPE", "TRB", "DGBB", "HUB"]: continue
                        
                        # Split families joined by a slash (e.g., 331074/32214)
                        fams_to_process = fam_raw.split("/") if "/" in fam_raw else [fam_raw]
                        
                        for f_raw in fams_to_process:
                            fam = parse_family(f_raw)
                            if fam:
                                or_qty = safe_float(row_vals[i+1])
                                ir_qty = safe_float(row_vals[i+2])
                                
                                if fam not in box_matrix: box_matrix[fam] = {}
                                if or_qty > 0: box_matrix[fam]['OR'] = or_qty
                                if ir_qty > 0: box_matrix[fam]['IR'] = ir_qty
            
            # Fallback Sources
            for fb_sheet in ['BOX PER DAY DGBB', 'BOX PER DAY TRB']:
                if fb_sheet in sheets_box:
                    df_fb = sheets_box[fb_sheet].fillna('')
                    type_col, ir_col, or_col, single_rpb_col = -1, -1, -1, -1
                    
                    for r_idx in range(min(20, len(df_fb))):
                        row_strs = [str(x).strip().upper() for x in df_fb.iloc[r_idx]]
                        norm_strs = [re.sub(r'[\s./]', '', x) for x in row_strs]
                        
                        t_c = next((j for j, h in enumerate(norm_strs) if 'TYPE' in h or 'BEARING' in h), -1)
                        i_c = next((j for j, h in enumerate(norm_strs) if 'IR' in h and 'BOX' in h), -1)
                        o_c = next((j for j, h in enumerate(norm_strs) if 'OR' in h and 'BOX' in h), -1)
                        s_c = next((j for j, h in enumerate(norm_strs) if 'RING' in h and 'BOX' in h and 'IR' not in h and 'OR' not in h), -1)
                        
                        if t_c != -1 and (i_c != -1 or o_c != -1 or s_c != -1):
                            type_col, ir_col, or_col, single_rpb_col = t_c, i_c, o_c, s_c
                            break
                            
                    if type_col != -1:
                        for idx in range(r_idx + 1, len(df_fb)):
                            row_vals = list(df_fb.iloc[idx])
                            fam_raw = str(row_vals[type_col]).strip()
                            fam = parse_family(fam_raw)
                            if fam:
                                if fam not in box_matrix: box_matrix[fam] = {}
                                
                                if 'IR' not in box_matrix[fam] or box_matrix[fam]['IR'] <= 0:
                                    if ir_col != -1: box_matrix[fam]['IR'] = safe_float(row_vals[ir_col])
                                    elif single_rpb_col != -1: box_matrix[fam]['IR'] = safe_float(row_vals[single_rpb_col])
                                
                                if 'OR' not in box_matrix[fam] or box_matrix[fam]['OR'] <= 0:
                                    if or_col != -1: box_matrix[fam]['OR'] = safe_float(row_vals[or_col])
                                    elif single_rpb_col != -1: box_matrix[fam]['OR'] = safe_float(row_vals[single_rpb_col])
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

        face_req, od_req, ht_req = {}, {}, {} # CORRECTED TUPLE ASSIGNMENT
        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            if rpb_ir <= 0: rpb_ir = 100.0
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            if rpb_or <= 0: rpb_or = 100.0
            
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

        # 4. PRODUCTION RATES
        weight_matrix, furnace_map, machines_data = {}, {}, {'FACE': {}, 'OD': {}}

        sheets_prod, logs3 = load_excel_all_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS'].fillna('')
                header_idx = -1
                for r_idx in range(min(10, len(df_w))):
                    h_row = [str(x).strip().upper() for x in df_w.iloc[r_idx].values]
                    if any('TYPE' in h for h in h_row) and any('IR/OR' in h or 'WEIGHT' in h or 'IR' in h for h in h_row):
                        header_idx = r_idx
                        break
                
                if header_idx != -1:
                    headers = [str(x).strip().upper() for x in df_w.iloc[header_idx].values]
                    norm_w_headers = [re.sub(r'[\s./]', '', h) for h in headers]
                    type_idx = next((j for j, h in enumerate(norm_w_headers) if 'TYPE' in h), -1)
                    ir_or_idx = next((j for j, h in enumerate(norm_w_headers) if 'IROR' in h or 'IR' in h), -1)
                    wt_idx = next((j for j, h in enumerate(norm_w_headers) if 'WEIGHT' in h), -1)

                    if type_idx != -1:
                        for offset in range(1, len(df_w) - header_idx):
                            row_vals = df_w.iloc[header_idx + offset].values
                            raw_type = str(row_vals[type_idx]).strip()
                            if not raw_type or raw_type == 'NAN': continue
                            
                            fam = parse_family(raw_type)
                            if not fam: continue

                            ir_or_val = str(row_vals[ir_or_idx]).strip() if ir_or_idx != -1 else ""
                            part_code = None
                            if '100' in ir_or_val: part_code = 'OR'
                            elif '120' in ir_or_val: part_code = 'IR'
                            
                            if part_code and wt_idx != -1:
                                wt_val = safe_float(row_vals[wt_idx])
                                if wt_val > 0:
                                    weight_matrix[f"{fam}_{part_code}"] = wt_val

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
                str_matrix = df_m.fillna('').astype(str).values
                
                for r in range(str_matrix.shape[0]):
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text or 'M/C' in row_text:
                        cells = [c.strip() for c in str_matrix[r] if c.strip()]
                        m_num = cells[1] if len(cells) > 1 else f"MC_{r}"
                        
                        m_type = "UNKNOWN"
                        if "FACE" in row_text or "DDS" in m_num.upper() or "BG" in m_num.upper(): m_type = "FACE"
                        elif "OD" in row_text or "CL" in m_num.upper() or "CELL" in m_num.upper() or "+" in m_num: m_type = "OD"
                        
                        if m_type in ['FACE', 'OD']:
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                            
                            header_idx = -1
                            for offset in range(1, 15):
                                if r + offset >= str_matrix.shape[0]: break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                if any('TYPE' in h or 'PART' in h for h in h_row):
                                    header_idx = r + offset
                                    break
                            
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in df_m.iloc[header_idx].values]
                                norm_headers = [re.sub(r'[\s./]', '', h) for h in headers]
                                
                                std_hr_idx = next((j for j, h in enumerate(norm_headers) if 'STDHR' in h), -1)
                                box_hr_idx = next((j for j, h in enumerate(norm_headers) if 'BOXHR' in h or 'BOXESHR' in h), -1)
                                ring_hr_idx = next((j for j, h in enumerate(norm_headers) if 'RINGHR' in h or 'RINGSHR' in h), -1)
                                rpb_idx = next((j for j, h in enumerate(norm_headers) if 'RING' in h and 'BOX' in h and 'HR' not in h), -1)
                                type_idx = next((j for j, h in enumerate(norm_headers) if 'TYPE' in h or 'BEARING' in h), -1)
                                part_idx = next((j for j, h in enumerate(norm_headers) if 'PART' in h and 'NO' not in h), -1)
                                
                                for offset2 in range(1, 60):
                                    if header_idx + offset2 >= str_matrix.shape[0]: break
                                    row_vals = df_m.iloc[header_idx + offset2].values
                                    
                                    raw_type = str(row_vals[type_idx]).strip() if type_idx != -1 else ""
                                    if not raw_type or raw_type.upper() in ['NAN', 'NONE']: continue
                                    
                                    fam = parse_family(raw_type)
                                    if not fam: continue
                                    
                                    part_val = str(row_vals[part_idx]).strip().upper() if part_idx != -1 else ""
                                    p_codes = []
                                    if '100' in part_val or 'OR' in part_val: p_codes.append('OR')
                                    if '120' in part_val or 'IR' in part_val or '010' in part_val: p_codes.append('IR')
                                    if not p_codes: p_codes = ['IR', 'OR']
                                    
                                    for pc in p_codes:
                                        rate_hr = 0.0
                                        rpb = safe_float(row_vals[rpb_idx]) if rpb_idx != -1 else 0.0
                                        if rpb <= 0: rpb = box_matrix.get(fam, {}).get(pc, 0.0)
                                        if rpb <= 0: rpb = 100.0
                                        
                                        if box_hr_idx != -1:
                                            val = safe_float(row_vals[box_hr_idx])
                                            if val > 0: rate_hr = val
                                            
                                        if rate_hr == 0.0 and ring_hr_idx != -1:
                                            val = safe_float(row_vals[ring_hr_idx])
                                            if val > 0: rate_hr = val / rpb
                                            
                                        if rate_hr == 0.0 and std_hr_idx != -1:
                                            val = safe_float(row_vals[std_hr_idx])
                                            if val > 0: rate_hr = val / rpb
                                            
                                        if rate_hr > 0:
                                            machines_data[m_type][m_num]['rates'][f"{fam}_{pc}"] = rate_hr
            del sheets_prod
            gc.collect()

        # 5. OPTIMIZED GRINDING SCHEDULER
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
                    
                    def get_sort_key(m, r):
                        hrs_left = machine_clocks[m]
                        current_fam = machine_last_fam[m]
                        setup_cost = 2.0 if (current_fam and current_fam != fam) else 0.0
                        eff_hrs = hrs_left - setup_cost
                        if eff_hrs <= 0: return (3, 0, 0)
                        
                        time_req = boxes_needed / r
                        can_finish = time_req <= eff_hrs
                        unused = eff_hrs - time_req if can_finish else 0
                        
                        return (0 if can_finish else 1, unused if can_finish else -eff_hrs, -r)
                    
                    candidates.sort(key=lambda x: get_sort_key(x[0], x[1]))
                    
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
                        reason = "Capacity Exhausted" if placed else "Missing Machine Rate (0.0)"
                        unscheduled.append({ "stage": m_type, "part": f"{fam} {p_code}", "missed_boxes": f"{round(boxes_needed, 1)} boxes - {reason}" })

            return list(allocated_result.values())

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # 6. DYNAMIC HEAT TREATMENT
        furnace_clocks = {f: {"avail_hours": 24.0, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}

        for fam, data in sorted(ht_req.items(), key=lambda x: x[1]['rings']['IR'] + x[1]['rings']['OR'], reverse=True):
            for p_code, qty in [('IR', data['rings']['IR']), ('OR', data['rings']['OR'])]:
                if qty <= 0: continue
                
                search_key = f"{extract_num(fam)}_{p_code}"
                preferred_furnaces = furnace_map.get(search_key, [])
                if not preferred_furnaces:
                    preferred_furnaces = list(FURNACE_SPECS.keys())
                
                # Fetch weight dynamically. 0.25 fallback when entirely missing.
                unit_weight = weight_matrix.get(f"{fam}_{p_code}")
                is_assumed = False
                
                if unit_weight is None or unit_weight <= 0:
                    unit_weight = 0.25
                    is_assumed = True
                    # Output log for missing weights that required assumption
                    debug_logs.append(f"HT Skipped: Missing weight for {fam} {p_code} - Assumed 0.25kg")
                
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
                        
                        # Show raw pcs if weight was missing/assumed, otherwise display kg
                        display_rate = f"{int(qty)} pcs" if is_assumed else f"{round(total_weight_kg, 1)} kg"
                        
                        ctx["rows"].append({
                            "part": f"{fam}-{p_code}", 
                            "qty": str(int(qty)), 
                            "cha": data['channel'],
                            "rate": display_rate, 
                            "alert": False 
                        })
                        scheduled_flag = True
                        break
                        
                if not scheduled_flag:
                    unscheduled.append({ "stage": "HT", "part": f"{fam} {p_code}", "missed_boxes": "Capacity Exceeded" })

        # All 7 furnaces are mapped, keeping them visible
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
