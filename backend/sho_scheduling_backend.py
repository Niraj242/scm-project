import os
import re
import math
import pandas as pd
import requests
import io
import gc
import json
import time
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

FAM_REGEX = re.compile(r'(\d{3,5})')

# --- 1. PERFORMANCE CACHE ---
EXCEL_CACHE = {}
CACHE_TTL = 600

# --- 2. MONTHLY TRACKING STORAGE ---
MONTHLY_FILE = "monthly_tracking.json"

def load_monthly_tracking():
    if os.path.exists(MONTHLY_FILE):
        try:
            with open(MONTHLY_FILE, 'r') as f: 
                return json.load(f)
        except: 
            return {}
    return {}

def save_monthly_tracking(data):
    try:
        with open(MONTHLY_FILE, 'w') as f: 
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving monthly tracking: {e}")

# Matrix exact matches from user image
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

@router.get("/api/monthly_tracking")
def get_monthly_tracking():
    return load_monthly_tracking()

def normalize_channel(ch_str):
    ch = str(ch_str).strip().upper()
    ch = ch.replace("CH", "").replace("CHANNEL", "").strip()
    if ch.isdigit(): 
        return str(int(ch))
    return ch

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if "INDUSTRILA" in text: 
        text = text.replace("INDUSTRILA", "INDUSTRIAL")
    if "AUTOMOTIVE" in text: 
        return None
    if not text or text in ["NAN", "NONE", "", "UNKNOWN", "TYPE"]: 
        return None
    
    # Highly robust normalization to base numerical family (resolves Change 4)
    if "HUB" in text:
        match_hub = re.search(r'(T?\s*HUB\s*\d+\.?\d*)', text)
        if match_hub: return match_hub.group(1).replace(" ", "")
        return "HUB"
        
    if text.startswith("T ") or re.match(r'^T\d+', text):
        match_t = re.search(r'(T\s*\d+)', text)
        if match_t: return match_t.group(1).replace(" ", "")
        return "T"
        
    if "UC" in text or "BB1B" in text:
        match_uc = re.search(r'(\d{3,5})', text)
        if match_uc: return match_uc.group(1)

    # Extract base number from everything else (BB-6205, BT-6205, 6205A -> 6205)
    match = FAM_REGEX.search(text)
    if match:
        return match.group(1)
        
    return text.split()[0].split('-')[0] if text.split() else text

def extract_num(text):
    match = re.search(r'(\d{3,5})', str(text))
    if match: 
        return match.group(1)
    match_hub = re.search(r'HUB\s*(\d+\.?\d*)', str(text).upper())
    if match_hub: 
        return "HUB" + match_hub.group(1).replace(" ", "")
    return str(text)

def safe_float(val):
    if pd.isna(val) or val is None: 
        return 0.0
    try:
        s_val = str(val).replace(',', '').strip().lower()
        if s_val in ['nan', 'none', '', 'null']: 
            return 0.0
        return float(s_val)
    except Exception:
        return 0.0

def is_target_date(val, target_date):
    if val is None or pd.isna(val): 
        return False
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.day == target_date.day and val.month == target_date.month
        
    v_str = str(val).strip().upper()
    for symbol in ['-', '/', '.', '_', ':', ' ']: 
        v_str = v_str.replace(symbol, ' ')
    tokens = v_str.split()
    
    day_str = str(target_date.day)
    day_padded = f"{target_date.day:02d}"
    
    if day_str in tokens or day_padded in tokens:
        month_str = target_date.strftime("%b").upper()
        if any(m in v_str for m in ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]):
            return month_str in v_str
        return True
    return False

def get_cached_excel_sheets(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "": 
        return None, logs
    now = time.time()
    if url in EXCEL_CACHE:
        cache_time, df_dict = EXCEL_CACHE[url]
        if now - cache_time < CACHE_TTL:
            return df_dict, [f"Loaded {file_label} from ultra-fast cache."]
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: 
            return None, logs
        content = io.BytesIO(resp.content)
        df_dict = pd.read_excel(content, sheet_name=None, header=None)
        EXCEL_CACHE[url] = (now, df_dict)
        return df_dict, logs
    except Exception as e:
        return None, [f"[{file_label}] ERR: {str(e)}"]

def get_rate_for_part(fam, p_code, rates):
    exact_key = f"{fam}_{p_code}"
    if exact_key in rates: 
        return rates[exact_key]
    num1 = extract_num(fam)
    for k, v in rates.items():
        if not k.endswith(f"_{p_code}"): 
            continue
        k_fam = k.split('_')[0]
        num2 = extract_num(k_fam)
        if (num1 and num1 != fam and num1 == num2) or (num1 in k_fam) or (k_fam in num1):
            return v
    return 0.0 

def format_time(rel_hrs):
    total_minutes = int(round(rel_hrs * 60))
    base_hour = 7
    h = (base_hour + (total_minutes // 60)) % 24
    m = total_minutes % 60
    day_plus = " (+1)" if (base_hour + (total_minutes // 60)) >= 24 else ""
    return f"{h:02d}:{m:02d}{day_plus}"

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day_1 = req_date + timedelta(days=1)
        day_2 = req_date + timedelta(days=2)
        month_str = req_date.strftime("%Y-%m")
        
        monthly_data = load_monthly_tracking()
        if month_str not in monthly_data:
            monthly_data[month_str] = {}

        # 1. PARSE ZEROSET
        channel_demands_day1 = {} 
        channel_demands_day2 = {}
        
        sheets_zero, logs1 = get_cached_excel_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                r_idx, type_col_idx = None, None
                c1_col, c2_col = None, None
                monthly_cols = []
                
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
                            if is_target_date(val, day_1): c1_col = j
                            if is_target_date(val, day_2): c2_col = j
                            if pd.notna(val):
                                if isinstance(val, (datetime, pd.Timestamp)) and val.month == req_date.month:
                                    monthly_cols.append(j)
                                elif str(val).strip().isdigit() and 1 <= int(str(val).strip()) <= 31:
                                    monthly_cols.append(j)
                    if r_idx is not None and type_col_idx is not None: 
                        break
                        
                if r_idx is not None and type_col_idx is not None:
                    for idx in range(r_idx + 1, len(df_zero)):
                        active_raw_type = str(df_zero.iloc[idx, type_col_idx]).strip()
                        if not active_raw_type: 
                            continue
                        fam = parse_family(active_raw_type)
                        if not fam: 
                            continue

                        if fam not in monthly_data[month_str]:
                            monthly_data[month_str][fam] = {"total_req": 0, "produced": 0, "channel": str(sheet_name).strip()}
                        
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0:
                            monthly_data[month_str][fam]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2_col]) if c2_col is not None else 0.0
                        
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0:
                            if fam not in channel_demands_day1: 
                                channel_demands_day1[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[fam]['IR'] = max(channel_demands_day1[fam]['IR'], r1)
                            channel_demands_day1[fam]['OR'] = max(channel_demands_day1[fam]['OR'], r1)
                            
                        if r2 > 0:
                            if fam not in channel_demands_day2: 
                                channel_demands_day2[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day2[fam]['IR'] = max(channel_demands_day2[fam]['IR'], r2)
                            channel_demands_day2[fam]['OR'] = max(channel_demands_day2[fam]['OR'], r2)
        del sheets_zero

        # 2. BOX MATRIX
        box_matrix = {}
        sheets_box, _ = get_cached_excel_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box:
            # Change 5: Highest Priority is RING PER BOX sheet
            if 'RING PER BOX.' in sheets_box:
                df_box = sheets_box['RING PER BOX.'].fillna('')
                for idx in range(2, len(df_box)):
                    row_vals = list(df_box.iloc[idx])
                    for i in range(0, len(row_vals) - 2, 3):
                        fam_raw = str(row_vals[i]).strip()
                        if not fam_raw or fam_raw.upper() in ["TYPE", "TRB", "DGBB", "HUB"]: 
                            continue
                        fams_to_process = fam_raw.split("/") if "/" in fam_raw else [fam_raw]
                        for f_raw in fams_to_process:
                            fam = parse_family(f_raw)
                            if fam:
                                or_qty = safe_float(row_vals[i+1])
                                ir_qty = safe_float(row_vals[i+2])
                                if fam not in box_matrix: 
                                    box_matrix[fam] = {}
                                if or_qty > 0: 
                                    box_matrix[fam]['OR'] = or_qty
                                if ir_qty > 0: 
                                    box_matrix[fam]['IR'] = ir_qty
            
            # Lower priority fallbacks for boxes
            for fb_sheet in ['BOX PER DAY DGBB', 'BOX PER DAY TRB']:
                if fb_sheet in sheets_box:
                    df_fb = sheets_box[fb_sheet].fillna('')
                    type_col, ir_col, or_col, single_rpb_col = -1, -1, -1, -1
                    for r_idx in range(min(20, len(df_fb))):
                        norm_strs = [re.sub(r'[\s./_\-]', '', str(x).strip().upper()) for x in df_fb.iloc[r_idx]]
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
                            fam = parse_family(str(row_vals[type_col]).strip())
                            if fam:
                                if fam not in box_matrix: 
                                    box_matrix[fam] = {}
                                # Only add if not already extracted from primary 'RING PER BOX.' sheet
                                if 'IR' not in box_matrix[fam] or box_matrix[fam]['IR'] <= 0:
                                    if ir_col != -1: box_matrix[fam]['IR'] = safe_float(row_vals[ir_col])
                                    elif single_rpb_col != -1: box_matrix[fam]['IR'] = safe_float(row_vals[single_rpb_col])
                                if 'OR' not in box_matrix[fam] or box_matrix[fam]['OR'] <= 0:
                                    if or_col != -1: box_matrix[fam]['OR'] = safe_float(row_vals[or_col])
                                    elif single_rpb_col != -1: box_matrix[fam]['OR'] = safe_float(row_vals[single_rpb_col])
        del sheets_box

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
                    if len(parts) < 3: 
                        continue
                    col_channel, sub_ring_type = parts[-2], parts[-1]
                    
                    fam = parse_family(val)
                    if not fam: 
                        continue
                    buf_val = safe_float(payload.entries.get(f"{buf_prefix}_{col_channel}_{sub_ring_type}", 0))
                    if buf_val <= 0: 
                        continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[fam][stage][sub_ring_type] += buf_val

        # Process Requirement logic implements Pull-System Process Sequence (HT -> Face -> OD)
        # Avoids unnecessary production (WIP) by explicitly netting against buffers
        def process_requirements_for_day(demands, in_out_buffers):
            f_req = {}
            o_req = {}
            h_req = {}
            for fam, data in demands.items():
                rpb_ir = box_matrix.get(fam, {}).get('IR', 0)
                rpb_or = box_matrix.get(fam, {}).get('OR', 0)
                req_rings_ir = data['IR']
                req_rings_or = data['OR']
                
                def apply_buf(stage, side, base_rings, rpb_rate):
                    raw_buf = in_out_buffers.get(fam, {}).get(stage, {}).get(side, 0)
                    if payload.unit_mode == 'Days':
                        avail_buf_rings = raw_buf * base_rings
                    elif payload.unit_mode == 'Boxes':
                        avail_buf_rings = raw_buf * (rpb_rate if rpb_rate > 0 else 100)
                    else:
                        avail_buf_rings = raw_buf 
                    
                    if avail_buf_rings >= base_rings:
                        used_rings = base_rings
                        rem_rings = avail_buf_rings - base_rings
                    else:
                        used_rings = avail_buf_rings
                        rem_rings = 0.0
                        
                    if fam in in_out_buffers:
                        if payload.unit_mode == 'Days':
                            new_raw = (rem_rings / base_rings) if base_rings > 0 else 0
                        elif payload.unit_mode == 'Boxes':
                            new_raw = rem_rings / (rpb_rate if rpb_rate > 0 else 100)
                        else:
                            new_raw = rem_rings
                        in_out_buffers[fam][stage][side] = new_raw
                    return used_rings
                    
                net_od_ir = max(0.0, req_rings_ir - apply_buf('OD', 'IR', req_rings_ir, rpb_ir))
                net_od_or = max(0.0, req_rings_or - apply_buf('OD', 'OR', req_rings_or, rpb_or))
                
                net_face_ir = max(0.0, net_od_ir - apply_buf('FACE', 'IR', net_od_ir, rpb_ir))
                net_face_or = max(0.0, net_od_or - apply_buf('FACE', 'OR', net_od_or, rpb_or))
                
                net_ht_ir = max(0.0, net_face_ir - apply_buf('CH', 'IR', net_face_ir, rpb_ir))
                net_ht_or = max(0.0, net_face_or - apply_buf('CH', 'OR', net_face_or, rpb_or))

                if net_face_ir > 0 or net_face_or > 0: 
                    f_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': data['channel']}
                if net_od_ir > 0 or net_od_or > 0: 
                    o_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': data['channel']}
                if net_ht_ir > 0 or net_ht_or > 0: 
                    h_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'channel': data['channel']}
            return f_req, o_req, h_req

        face_req_d1, od_req_d1, ht_req_d1 = process_requirements_for_day(channel_demands_day1, buffers_by_fam)
        face_req_d2, od_req_d2, ht_req_d2 = process_requirements_for_day(channel_demands_day2, buffers_by_fam)

        # 4. PRODUCTION RATES & WEIGHTS
        weight_matrix = {}
        furnace_map = {}
        machines_data = {'FACE': {}, 'OD': {}}

        sheets_prod, logs3 = get_cached_excel_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
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
                    norm_w_headers = [re.sub(r'[\s./_\-]', '', str(x).strip().upper()) for x in df_w.iloc[header_idx].values]
                    type_idx = next((j for j, h in enumerate(norm_w_headers) if 'TYPE' in h), -1)
                    ir_or_idx = next((j for j, h in enumerate(norm_w_headers) if 'IROR' in h or 'IR' in h), -1)
                    wt_idx = next((j for j, h in enumerate(norm_w_headers) if 'WEIGHT' in h), -1)

                    if type_idx != -1:
                        for offset in range(1, len(df_w) - header_idx):
                            row_vals = df_w.iloc[header_idx + offset].values
                            fam = parse_family(str(row_vals[type_idx]).strip())
                            if not fam: 
                                continue
                            
                            ir_or_val = str(row_vals[ir_or_idx]).strip() if ir_or_idx != -1 else ""
                            # Change 2: Specific weight parsing based on 100/120 code
                            part_code = 'OR' if '100' in ir_or_val else ('IR' if ('120' in ir_or_val or '010' in ir_or_val) else None)
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
                    if not comp_level: 
                        continue
                    p_code = 'IR' if comp_level.startswith('IM') else ('OR' if comp_level.startswith('OM') else None)
                    fam = extract_num(comp_level) 
                    if fam and p_code:
                        valid_furnaces = []
                        for fn in [str(r.get('PRIMARY FURNA', r.get('PRIMARY FURNACE', ''))), str(r.get('ALTERNATIVE 1', '')), str(r.get('ALTERNATIVE 2', ''))]:
                            matched_fn = next((k for k in FURNACE_SPECS.keys() if fn.strip().upper()[:4] in k.upper()), None)
                            if matched_fn and matched_fn not in valid_furnaces: 
                                valid_furnaces.append(matched_fn)
                        if valid_furnaces: 
                            furnace_map[f"{fam}_{p_code}"] = valid_furnaces
            
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: 
                    continue
                str_matrix = df_m.fillna('').astype(str).values
                for r in range(str_matrix.shape[0]):
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text or 'M/C' in row_text:
                        cells = [c.strip() for c in str_matrix[r] if c.strip()]
                        m_num = cells[1] if len(cells) > 1 else f"MC_{r}"
                        
                        m_type = "UNKNOWN"
                        if "FACE" in row_text or "DDS" in m_num.upper() or "BG" in m_num.upper(): 
                            m_type = "FACE"
                        elif "OD" in row_text or "CL" in m_num.upper() or "CELL" in m_num.upper() or "+" in m_num: 
                            m_type = "OD"
                        
                        if m_type in ['FACE', 'OD']:
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                            
                            header_idx = -1
                            for offset in range(1, 15):
                                if r + offset >= str_matrix.shape[0]: 
                                    break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                if any('TYPE' in h or 'PART' in h for h in h_row):
                                    header_idx = r + offset
                                    break
                            
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in df_m.iloc[header_idx].values]
                                # Change 3: Enhanced header detection handling variants
                                norm_headers = [re.sub(r'[\s./_\-]', '', h) for h in headers]
                                
                                std_hr_idx = next((j for j, h in enumerate(norm_headers) if 'STDHR' in h), -1)
                                box_hr_idx = next((j for j, h in enumerate(norm_headers) if 'BOXHR' in h or 'BOXESHR' in h or 'BOXPERHR' in h or 'BOXESPERHR' in h), -1)
                                ring_hr_idx = next((j for j, h in enumerate(norm_headers) if 'RINGHR' in h or 'RINGSHR' in h or 'RINGPERHR' in h or 'RINGSPERHR' in h), -1)
                                rpb_idx = next((j for j, h in enumerate(norm_headers) if 'RING' in h and 'BOX' in h and 'HR' not in h), -1)
                                type_idx = next((j for j, h in enumerate(norm_headers) if 'TYPE' in h or 'BEARING' in h), -1)
                                part_idx = next((j for j, h in enumerate(norm_headers) if 'PART' in h and 'NO' not in h), -1)
                                
                                for offset2 in range(1, 60):
                                    if header_idx + offset2 >= str_matrix.shape[0]: 
                                        break
                                    row_vals = df_m.iloc[header_idx + offset2].values
                                    fam = parse_family(str(row_vals[type_idx]).strip() if type_idx != -1 else "")
                                    if not fam: 
                                        continue
                                    
                                    part_val = str(row_vals[part_idx]).strip().upper() if part_idx != -1 else ""
                                    p_codes = []
                                    if '100' in part_val or 'OR' in part_val: p_codes.append('OR')
                                    if '120' in part_val or 'IR' in part_val or '010' in part_val: p_codes.append('IR')
                                    if not p_codes: p_codes = ['IR', 'OR']
                                    
                                    for pc in p_codes:
                                        rate_rings = 0.0
                                        rpb = safe_float(row_vals[rpb_idx]) if rpb_idx != -1 else 0.0
                                        if rpb <= 0: 
                                            rpb = box_matrix.get(fam, {}).get(pc, 0.0)
                                        
                                        # Conversion: Priority to Rings/Hr based capacities (Change 5)
                                        if ring_hr_idx != -1 and safe_float(row_vals[ring_hr_idx]) > 0:
                                            rate_rings = safe_float(row_vals[ring_hr_idx])
                                        elif box_hr_idx != -1 and safe_float(row_vals[box_hr_idx]) > 0 and rpb > 0:
                                            rate_rings = safe_float(row_vals[box_hr_idx]) * rpb
                                        elif std_hr_idx != -1 and safe_float(row_vals[std_hr_idx]) > 0 and rpb > 0:
                                            rate_rings = safe_float(row_vals[std_hr_idx]) * rpb
                                            
                                        if rate_rings > 0:
                                            machines_data[m_type][m_num]['rates'][f"{fam}_{pc}"] = rate_rings

        # ==========================================
        # 5. ISOLATED SCHEDULING SECTIONS (Balanced & Timed)
        # ==========================================

        def allocate_grinding(m_type, dict_d1, dict_d2):
            allocated_result = {m_num: {"machine": m_num, "rows": []} for m_num in machines_data.get(m_type, {})}
            machine_clocks = {m_num: m_info['avail_hours'] for m_num, m_info in machines_data.get(m_type, {}).items()}
            machine_last_fam = {m_num: None for m_num in machines_data.get(m_type, {})}
            
            # Pre-calculate machine versatility for smarter allocation (Change 7)
            machine_versatility = {m: 0 for m in machines_data.get(m_type, {})}
            for d in [dict_d1, dict_d2]:
                for f_cand, req_cand in d.items():
                    for p_cand in ['IR', 'OR']:
                        if req_cand[p_cand] > 0:
                            for m in machine_versatility:
                                if get_rate_for_part(f_cand, p_cand, machines_data[m_type][m].get('rates', {})) > 0:
                                    machine_versatility[m] += 1

            def process_priority_pass(demands_dict, is_day_2=False):
                sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
                for fam, data in sorted_fams:
                    ch_normalized = normalize_channel(data['channel'])
                    for p_code in ['IR', 'OR']:
                        if ch_normalized in OPERATION_EXCLUSIONS and p_code in OPERATION_EXCLUSIONS[ch_normalized].get(m_type, []):
                            continue
                                
                        rings_needed = data[p_code]
                        if rings_needed <= 0: 
                            continue
                        
                        candidates = []
                        for m_num, m_info in machines_data.get(m_type, {}).items():
                            rate_rings = get_rate_for_part(fam, p_code, m_info.get('rates', {}))
                            if rate_rings > 0 and machine_clocks[m_num] > 0:
                                candidates.append((m_num, rate_rings))
                        
                        # LOAD BALANCING (Change 6 & 7): Maximize global throughput, save versatile machines
                        def get_machine_score(m_key, rate):
                            hrs = machine_clocks[m_key]
                            if hrs <= 0: return 99999.0
                            setup = 2.0 if machine_last_fam[m_key] and machine_last_fam[m_key] != fam else 0.0
                            if hrs <= setup: return 99999.0
                            
                            start_t = 24.0 - hrs + setup
                            end_time = start_t + (rings_needed / rate)
                            # Add minor penalty for versatile machines to encourage using dedicated machines first
                            penalty = machine_versatility.get(m_key, 0) * 0.1 
                            return end_time + penalty

                        candidates.sort(key=lambda x: get_machine_score(x[0], x[1]))
                        
                        placed = False
                        # Change 1: Loop has no artificial 3-job limit
                        for m_num, rate_rings in candidates:
                            if rings_needed <= 0: break
                            if machine_clocks[m_num] <= 0: continue
                            
                            hrs_left = machine_clocks[m_num]
                            setup_cost = 2.0 if machine_last_fam[m_num] and machine_last_fam[m_num] != fam else 0.0
                            
                            if hrs_left <= setup_cost:
                                machine_clocks[m_num] = 0.0
                                continue
                                
                            hrs_left -= setup_cost
                            time_required = rings_needed / rate_rings
                            
                            produced_rings = rings_needed
                            if time_required <= hrs_left:
                                rings_needed = 0.0
                                hrs_left -= time_required
                            else:
                                produced_rings = hrs_left * rate_rings
                                rings_needed -= produced_rings
                                time_required = hrs_left
                                hrs_left = 0.0
                                
                            start_rel = 24.0 - machine_clocks[m_num]
                            if setup_cost > 0:
                                start_rel += setup_cost
                            
                            end_rel = start_rel + time_required
                            timing_display = f"{format_time(start_rel)}-{format_time(end_rel)}"

                            machine_clocks[m_num] = hrs_left
                            machine_last_fam[m_num] = fam
                            placed = True
                            
                            rpb = box_matrix.get(fam, {}).get(p_code, 0)
                            # Change 5: Round UP to the nearest whole box
                            display_val = f"{math.ceil(produced_rings / rpb)}" if rpb > 0 else f"{int(produced_rings)} (Q)"
                            
                            if fam in monthly_data[month_str]:
                                monthly_data[month_str][fam]["produced"] += produced_rings
                            
                            allocated_result[m_num]["rows"].append({
                                "part": f"{fam} {p_code}" + (" (D2)" if is_day_2 else ""),
                                "qty": str(int(produced_rings)),
                                "std_box": display_val,
                                "timing": timing_display,
                                "p_2nd": "1" if len(allocated_result[m_num]["rows"]) == 0 else "",
                                "p_3rd": "1" if len(allocated_result[m_num]["rows"]) == 1 else "",
                                "alert": False,
                                "p_label": f"P{len(allocated_result[m_num]['rows']) + 1}"
                            })
                        
                        if rings_needed > 0.5:
                            day_label = "Day 2" if is_day_2 else "Day 1"
                            reason = "Capacity Exhausted" if placed else "Missing Machine Rate"
                            
                            rpb = box_matrix.get(fam, {}).get(p_code, 0)
                            missed_val = f"{int(rings_needed)} rings" if rpb <= 0 else f"{math.ceil(rings_needed / rpb)} box"
                            
                            unscheduled.append({ 
                                "stage": m_type, 
                                "part": f"{fam} {p_code} ({day_label})", 
                                "missed_boxes": f"{missed_val} - {reason}" 
                            })

            process_priority_pass(dict_d1, False)
            process_priority_pass(dict_d2, True)
            return list(allocated_result.values())


        def schedule_ht_pass(demands, furnace_clocks, is_day_2=False):
            for fam, data in sorted(demands.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True):
                for p_code in ['IR', 'OR']:
                    qty_rings = data[p_code]
                    if qty_rings <= 0: 
                        continue
                    
                    search_key = f"{extract_num(fam)}_{p_code}"
                    preferred_furnaces = furnace_map.get(search_key, [])
                    if not preferred_furnaces: 
                        preferred_furnaces = list(FURNACE_SPECS.keys())
                    
                    # Change 2: Strict Weight Check without assumed weight
                    unit_weight = weight_matrix.get(f"{fam}_{p_code}")
                    if unit_weight is None or unit_weight <= 0:
                        unscheduled.append({ 
                            "stage": "HT", 
                            "part": f"{fam} {p_code} ({'Day 2' if is_day_2 else 'Day 1'})", 
                            "missed_boxes": "Missing Weight - Part skipped" 
                        })
                        continue
                    
                    total_weight_kg = qty_rings * unit_weight
                    scheduled_flag = False
                    
                    for f_name in preferred_furnaces:
                        if f_name not in furnace_clocks: 
                            continue
                        
                        kg_per_hr = FURNACE_SPECS[f_name]
                        time_needed = total_weight_kg / kg_per_hr
                        ctx = furnace_clocks[f_name]
                        
                        setup_penalty = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                        
                        if (ctx["avail_hours"] - setup_penalty) >= time_needed:
                            start_rel = 24.0 - ctx["avail_hours"] + setup_penalty
                            end_rel = start_rel + time_needed
                            timing_display = f"{format_time(start_rel)}-{format_time(end_rel)}"

                            ctx["avail_hours"] -= (time_needed + setup_penalty)
                            ctx["current_fam"] = fam
                            
                            display_rate = f"{round(total_weight_kg, 1)} kg"
                            
                            ctx["rows"].append({
                                "part": f"{fam}-{p_code}" + (" (D2)" if is_day_2 else ""), 
                                "qty": str(int(qty_rings)), 
                                "cha": data['channel'],
                                "rate": display_rate, 
                                "timing": timing_display,
                                "alert": False 
                            })
                            scheduled_flag = True
                            break
                            
                    if not scheduled_flag:
                        day_lbl = "Day 2" if is_day_2 else "Day 1"
                        unscheduled.append({ "stage": "HT", "part": f"{fam} {p_code} ({day_lbl})", "missed_boxes": "Capacity Exceeded" })

        final_face = allocate_grinding('FACE', face_req_d1, face_req_d2)
        final_od = allocate_grinding('OD', od_req_d1, od_req_d2)
        
        furnaces_state = {f: {"avail_hours": 24.0, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}
        schedule_ht_pass(ht_req_d1, furnaces_state, False)
        schedule_ht_pass(ht_req_d2, furnaces_state, True)
        
        save_monthly_tracking(monthly_data)

        ht_formatted = [
            {"furnace": fur, "capacity": f"Total Cap: {int(f_data['capacity'])} kg/hr", "rows": f_data["rows"]}
            for fur, f_data in furnaces_state.items()
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
