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

# --- 1. PERFORMANCE CACHE ---
EXCEL_CACHE = {}
CACHE_TTL = 600

# Cache for parsed lookup dictionaries to prevent redundant O(N) worksheet scans
PARSED_MASTER_DATA = {
    "box_matrix": ({}, 0),  # (box_matrix_dict, cache_timestamp)
    "production": ({}, {}, {}, {}, 0) # (weight_matrix, furnace_map, machines_data, channel_flex, cache_timestamp)
}

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
    ch = ch.replace("CH", "").replace("CHANNEL", "").replace(" ", "").strip()
    return ch

# Validate rows to prevent scheduling headers/summaries
def is_invalid_part(raw_text):
    if pd.isna(raw_text) or not raw_text: return True
    t = str(raw_text).upper()
    invalid_keywords = [
        "PROJECTED", "PLAN", "QTY", "HRS", "DAY", "NAN", "NONE", "UNKNOWN", "TYPE",
        "WIP", "MTD", "ASKING", "TOTAL"
    ]
    for k in invalid_keywords:
        if k in t: return True
    return False

def get_lookup_variants(raw_text):
    """
    Strict normalization logic. Only removes spaces, formatting, 
    and suffixes, keeping the absolute base numeric family bounded.
    """
    if is_invalid_part(raw_text): return []
    t = str(raw_text).upper().strip()
    
    if "INDUSTRILA" in t: t = t.replace("INDUSTRILA", "INDUSTRIAL")
    if t.startswith("MF"): t = t[2:].strip()
    
    # Safely handle "/" when not suffix
    if '/' in t:
        parts = t.split('/')
        if not any(x in parts[1] for x in ['Q', 'X']):
            t = parts[0].strip()

    # Safely strip manufacturing suffixes from the end of the string
    suffixes = ['VK210', 'X/Q', '/Q', 'J2', 'AE', 'AB', 'A', 'B', 'E', 'J', 'X', 'Q']
    t_nosuff = t
    changed = True
    while changed:
        changed = False
        for suff in suffixes:
            pattern = r'[\s\-_/]*' + re.escape(suff) + r'$'
            new_t = re.sub(pattern, '', t_nosuff)
            if new_t != t_nosuff:
                t_nosuff = new_t
                changed = True
                
    t_nosuff = t_nosuff.strip()
    
    # Strip all remaining formatting characters
    t_clean = re.sub(r'[\s\-_/.]', '', t_nosuff)
    
    prefixes_to_strip = ['BAH', 'BTH', 'BAR', 'BB1B', 'BB1', 'BB', 'BT1', 'BT', 'UC']
    t_nopfx = t_clean
    found_prefix = ""
    for pfx in prefixes_to_strip:
        if t_clean.startswith(pfx):
            t_nopfx = t_clean[len(pfx):]
            found_prefix = pfx
            break

    # STRICT ORDER: Exact -> Normalized -> Prefixed -> Base Family
    variants = []
    if t and t not in variants: variants.append(t)
    if t_clean and t_clean not in variants: variants.append(t_clean)
    if found_prefix and t_nopfx:
        pf_val = f"{found_prefix}{t_nopfx}"
        if pf_val not in variants: variants.append(pf_val)
    if t_nopfx and t_nopfx not in variants: variants.append(t_nopfx)
    
    return variants

def get_display_name(raw_text):
    if pd.isna(raw_text): return ""
    t = str(raw_text).strip().upper()
    if t.startswith("MF"): t = t[2:].strip()
    return t

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
    if not url or url.strip() == "": return None, logs
    now = time.time()
    if url in EXCEL_CACHE:
        cache_time, df_dict = EXCEL_CACHE[url]
        if now - cache_time < CACHE_TTL:
            return df_dict, [f"Loaded {file_label} from ultra-fast cache."]
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None, logs
        content = io.BytesIO(resp.content)
        df_dict = pd.read_excel(content, sheet_name=None, header=None)
        EXCEL_CACHE[url] = (now, df_dict)
        return df_dict, logs
    except Exception as e:
        return None, [f"[{file_label}] ERR: {str(e)}"]

# Lookups now perform strict O(1) dictionary matching. NO FALLBACK LOOPS.
def get_rate_for_part(display_name, p_code, rates):
    variants = get_lookup_variants(display_name)
    for var in variants:
        if f"{var}_{p_code}" in rates: 
            return rates[f"{var}_{p_code}"]
    return 0.0

def get_weight_for_part(display_name, p_code, weights):
    variants = get_lookup_variants(display_name)
    for var in variants:
        if f"{var}_{p_code}" in weights: 
            return weights[f"{var}_{p_code}"]
    return None

def get_box_for_part_detailed(display_name, p_code, box_matrix):
    variants = get_lookup_variants(display_name)
    for var in variants:
        if var in box_matrix and p_code in box_matrix[var]: 
            return box_matrix[var][p_code]['qty'], box_matrix[var][p_code]['source'], var
    return 0.0, "NONE", variants[0] if variants else display_name

def get_box_for_part(display_name, p_code, box_matrix):
    qty, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix)
    return qty

def get_furnaces_for_part(display_name, p_code, furnace_map):
    variants = get_lookup_variants(display_name)
    for var in variants:
        if f"{var}_{p_code}" in furnace_map: 
            return furnace_map[f"{var}_{p_code}"]
    return list(FURNACE_SPECS.keys())

def format_time(rel_hrs):
    total_minutes = int(round(rel_hrs * 60))
    base_hour = 10 
    h = (base_hour + (total_minutes // 60)) % 24
    m = total_minutes % 60
    days_added = (base_hour + (total_minutes // 60)) // 24
    
    day_plus = f" (+{days_added})" if days_added > 0 else ""
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
                r_idx, type_col_idx, mv_col_idx = None, None, None
                c1_col, c2_col = None, None
                monthly_cols = []
                
                for i in range(min(25, len(df_zero))):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[i].values]
                    row_joined = " ".join(row_strs)
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF", "PART NO", "BRG NO"] or "TYPE" in val: type_col_idx = j
                            if val in ["MV", "FV", "VAR", "VARIANT"]: mv_col_idx = j
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
                    last_mf = ""
                    for idx in range(r_idx + 1, len(df_zero)):
                        mf_val = str(df_zero.iloc[idx, type_col_idx]).strip() if type_col_idx is not None else ""
                        if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                        
                        mv_val = str(df_zero.iloc[idx, mv_col_idx]).strip() if mv_col_idx is not None else ""
                        raw_t = mv_val if mv_val and mv_val not in ["NAN", "NONE"] else last_mf
                        
                        if is_invalid_part(raw_t): continue
                        display_name = get_display_name(raw_t)

                        if display_name not in monthly_data[month_str]:
                            monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": str(sheet_name).strip()}
                        
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0:
                            monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2_col]) if c2_col is not None else 0.0
                        
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1: 
                                channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)
                            
                        if r2 > 0:
                            if display_name not in channel_demands_day2: 
                                channel_demands_day2[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day2[display_name]['IR'] = max(channel_demands_day2[display_name]['IR'], r2)
                            channel_demands_day2[display_name]['OR'] = max(channel_demands_day2[display_name]['OR'], r2)
        del sheets_zero

        # 2. BOX MATRIX (Cached Master Parsing)
        box_matrix = {}
        sheets_box, _ = get_cached_excel_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        box_cache_ts = EXCEL_CACHE.get(BOX_RING_DATA_URL, (0, None))[0]
        
        if PARSED_MASTER_DATA["box_matrix"][1] == box_cache_ts:
            box_matrix = PARSED_MASTER_DATA["box_matrix"][0]
        elif sheets_box:
            if 'RING PER BOX.' in sheets_box:
                df_box = sheets_box['RING PER BOX.'].fillna('')
                for idx in range(2, len(df_box)):
                    row_vals = list(df_box.iloc[idx])
                    for i in range(0, len(row_vals) - 2, 3):
                        fam_raw = str(row_vals[i]).strip()
                        if is_invalid_part(fam_raw): continue
                        fams_to_process = fam_raw.split("/") if "/" in fam_raw else [fam_raw]
                        for f_raw in fams_to_process:
                            clean_keys = get_lookup_variants(f_raw)
                            for ck in clean_keys:
                                or_qty = safe_float(row_vals[i+1])
                                ir_qty = safe_float(row_vals[i+2])
                                if ck not in box_matrix: box_matrix[ck] = {}
                                if or_qty > 0: box_matrix[ck]['OR'] = {'qty': or_qty, 'source': 'RING PER BOX.'}
                                if ir_qty > 0: box_matrix[ck]['IR'] = {'qty': ir_qty, 'source': 'RING PER BOX.'}
            
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
                            raw_t = str(row_vals[type_col]).strip()
                            if is_invalid_part(raw_t): continue
                            
                            clean_keys = get_lookup_variants(raw_t)
                            for ck in clean_keys:
                                if ck not in box_matrix: box_matrix[ck] = {}
                                if 'IR' not in box_matrix[ck] or box_matrix[ck]['IR']['qty'] <= 0:
                                    fq = 0.0
                                    if ir_col != -1: fq = safe_float(row_vals[ir_col])
                                    elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                    if fq > 0: box_matrix[ck]['IR'] = {'qty': fq, 'source': fb_sheet}
                                if 'OR' not in box_matrix[ck] or box_matrix[ck]['OR']['qty'] <= 0:
                                    fq = 0.0
                                    if or_col != -1: fq = safe_float(row_vals[or_col])
                                    elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                    if fq > 0: box_matrix[ck]['OR'] = {'qty': fq, 'source': fb_sheet}
            
            PARSED_MASTER_DATA["box_matrix"] = (box_matrix, box_cache_ts)
        del sheets_box

        # 4. PRODUCTION RATES & WEIGHTS & FLEXIBILITY (Cached Master Parsing)
        sheets_prod, logs3 = get_cached_excel_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        prod_cache_ts = EXCEL_CACHE.get(SHO_PRODUCTION_URL, (0, None))[0]

        if PARSED_MASTER_DATA["production"][4] == prod_cache_ts:
            weight_matrix, furnace_map, machines_data, channel_flex_map, _ = PARSED_MASTER_DATA["production"]
        elif sheets_prod:
            weight_matrix = {}
            furnace_map = {}
            machines_data = {'FACE': {}, 'OD': {}}
            channel_flex_map = {} # {'CH1': {'IR': {'FACE': True, 'OD': True}, ...}}

            # Channel Process Flexibility
            flex_sheet_key = next((k for k in sheets_prod.keys() if 'PROCESS' in str(k).upper() and 'FLEX' in str(k).upper()), None)
            if flex_sheet_key:
                df_flex = sheets_prod[flex_sheet_key].fillna('')
                # Auto-detect columns
                header_idx = -1
                for i in range(min(10, len(df_flex))):
                    row_strs = [str(x).upper().strip() for x in df_flex.iloc[i].values]
                    if any("CH" in x or "CHANNEL" in x for x in row_strs) and any("FACE" in x for x in row_strs):
                        header_idx = i
                        break
                if header_idx != -1:
                    headers = [str(x).upper().strip() for x in df_flex.iloc[header_idx].values]
                    ch_col = next((j for j, h in enumerate(headers) if 'CH' in h or 'CHANNEL' in h), -1)
                    ring_col = next((j for j, h in enumerate(headers) if 'RING' in h or 'IR/OR' in h), -1)
                    face_col = next((j for j, h in enumerate(headers) if 'FACE' in h), -1)
                    od_col = next((j for j, h in enumerate(headers) if 'OD' in h), -1)
                    
                    if ch_col != -1 and ring_col != -1:
                        for idx in range(header_idx + 1, len(df_flex)):
                            ch_raw = str(df_flex.iloc[idx, ch_col]).strip()
                            if not ch_raw or is_invalid_part(ch_raw): continue
                            c_norm = normalize_channel(ch_raw)
                            r_raw = str(df_flex.iloc[idx, ring_col]).strip().upper()
                            p_code = 'OR' if 'OR' in r_raw or '100' in r_raw else ('IR' if 'IR' in r_raw or '010' in r_raw or '120' in r_raw else None)
                            
                            face_req = True
                            od_req = True
                            if face_col != -1:
                                face_val = str(df_flex.iloc[idx, face_col]).strip().upper()
                                if face_val == "NO": face_req = False
                            if od_col != -1:
                                od_val = str(df_flex.iloc[idx, od_col]).strip().upper()
                                if od_val == "NO": od_req = False
                                
                            if p_code:
                                if c_norm not in channel_flex_map: channel_flex_map[c_norm] = {}
                                channel_flex_map[c_norm][p_code] = {'FACE': face_req, 'OD': od_req}


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
                            raw_fam = str(row_vals[type_idx]).strip()
                            if is_invalid_part(raw_fam): continue
                            
                            clean_keys = get_lookup_variants(raw_fam)
                            if not clean_keys: continue
                            
                            ir_or_val = str(row_vals[ir_or_idx]).strip() if ir_or_idx != -1 else ""
                            part_code = 'OR' if '100' in ir_or_val else ('IR' if ('120' in ir_or_val or '010' in ir_or_val) else None)
                            if part_code and wt_idx != -1:
                                wt_val = safe_float(row_vals[wt_idx])
                                if wt_val > 0: 
                                    for ck in clean_keys:
                                        weight_matrix[f"{ck}_{part_code}"] = wt_val

            fur_sheet_key = next((k for k in sheets_prod.keys() if 'FURNACE' in str(k).upper() and 'FLEX' in str(k).upper()), None)
            if fur_sheet_key:
                df_f = sheets_prod[fur_sheet_key]
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for idx, r in df_f.iloc[1:].iterrows():
                    comp_level = str(r.get('COMP LEVEL 1', r.iloc[0] if len(r) > 0 else '')).strip()
                    if is_invalid_part(comp_level): continue
                    
                    p_code = 'IR' if comp_level.startswith('IM') else ('OR' if comp_level.startswith('OM') else None)
                    clean_keys = get_lookup_variants(comp_level)
                    if clean_keys and p_code:
                        valid_furnaces = []
                        for fn_key in ['PRIMARY FURNA', 'PRIMARY FURNACE', 'ALTERNATIVE 1', 'ALTERNATIVE 2']:
                            fn = str(r.get(fn_key, '')).strip().upper()
                            if not fn or fn == 'NAN': continue
                            
                            # Fixed AU vs AICHELIN mapping
                            matched_fn = None
                            if fn == "AU" or "UNITHERM" in fn:
                                matched_fn = "AICHELIN UNITHERM ( 2033 )"
                            elif "AICHELIN" in fn:
                                matched_fn = "AICHELIN.(896)"
                            else:
                                matched_fn = next((k for k in FURNACE_SPECS.keys() if fn[:4] in k.upper()), None)
                                
                            if matched_fn and matched_fn not in valid_furnaces: 
                                valid_furnaces.append(matched_fn)
                        if valid_furnaces: 
                            for ck in clean_keys:
                                furnace_map[f"{ck}_{p_code}"] = valid_furnaces
            
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.', 'Channel Process Flexibility']: continue
                str_matrix = df_m.fillna('').astype(str).values
                
                # Multi-table parsing support for full machine discovery
                current_m_num = None
                current_m_type = "UNKNOWN"
                header_idx = -1
                
                # Pre-find all header rows in sheet
                for r in range(str_matrix.shape[0]):
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text or 'M/C' in row_text:
                        cells = [c.strip() for c in str_matrix[r] if c.strip()]
                        m_cand = cells[1] if len(cells) > 1 else f"MC_{r}"
                        if m_cand and m_cand != "MACHINE" and m_cand != "M/C":
                            current_m_num = m_cand
                            if "FACE" in row_text or "DDS" in current_m_num.upper() or "BG" in current_m_num.upper(): current_m_type = "FACE"
                            elif "OD" in row_text or "CL" in current_m_num.upper() or "CELL" in current_m_num.upper() or "+" in current_m_num: current_m_type = "OD"
                    
                    if current_m_num and current_m_type in ['FACE', 'OD']:
                        h_row = [c.strip().upper() for c in str_matrix[r]]
                        if any('TYPE' in h or 'PART' in h for h in h_row) and any('HR' in h for h in h_row):
                            if current_m_num not in machines_data[current_m_type]:
                                machines_data[current_m_type][current_m_num] = {'name': current_m_num, 'rates': {}, 'ready_time': 0.0}
                                
                            norm_headers = [re.sub(r'[\s./_\-]', '', h) for h in h_row]
                            std_hr_idx = next((j for j, h in enumerate(norm_headers) if 'STDHR' in h), -1)
                            box_hr_idx = next((j for j, h in enumerate(norm_headers) if 'BOXHR' in h or 'BOXESHR' in h or 'BOXPERHR' in h or 'BOXESPERHR' in h), -1)
                            ring_hr_idx = next((j for j, h in enumerate(norm_headers) if 'RINGHR' in h or 'RINGSHR' in h or 'RINGPERHR' in h or 'RINGSPERHR' in h), -1)
                            rpb_idx = next((j for j, h in enumerate(norm_headers) if 'RING' in h and 'BOX' in h and 'HR' not in h), -1)
                            type_idx = next((j for j, h in enumerate(norm_headers) if 'TYPE' in h or 'BEARING' in h), -1)
                            part_idx = next((j for j, h in enumerate(norm_headers) if 'PART' in h and 'NO' not in h), -1)
                            comb_idx = next((j for j, h in enumerate(norm_headers) if 'COMBINED' in h), -1)
                            
                            for offset2 in range(1, 100):
                                if r + offset2 >= str_matrix.shape[0]: break
                                row_vals = str_matrix[r + offset2]
                                if "MACHINE" in " ".join(row_vals).upper() or "M/C" in " ".join(row_vals).upper(): break # Next machine
                                
                                raw_t = str(row_vals[type_idx]).strip() if type_idx != -1 else ""
                                if is_invalid_part(raw_t): continue
                                
                                clean_keys = get_lookup_variants(raw_t)
                                
                                # Use combined if exists, but still map to TYPE
                                comb_val = str(row_vals[comb_idx]).strip() if comb_idx != -1 else ""
                                if comb_val and not is_invalid_part(comb_val):
                                    clean_keys.extend(get_lookup_variants(comb_val))
                                    
                                if not clean_keys: continue
                                
                                part_val = str(row_vals[part_idx]).strip().upper() if part_idx != -1 else ""
                                p_codes = []
                                if '100' in part_val or 'OR' in part_val: p_codes.append('OR')
                                if '120' in part_val or 'IR' in part_val or '010' in part_val: p_codes.append('IR')
                                if not p_codes: p_codes = ['IR', 'OR']
                                
                                for pc in p_codes:
                                    rate_rings = 0.0
                                    rpb = safe_float(row_vals[rpb_idx]) if rpb_idx != -1 else 0.0
                                    if rpb <= 0: rpb = get_box_for_part(clean_keys[0], pc, box_matrix)
                                    
                                    if ring_hr_idx != -1 and safe_float(row_vals[ring_hr_idx]) > 0:
                                        rate_rings = safe_float(row_vals[ring_hr_idx])
                                    elif box_hr_idx != -1 and safe_float(row_vals[box_hr_idx]) > 0 and rpb > 0:
                                        rate_rings = safe_float(row_vals[box_hr_idx]) * rpb
                                    elif std_hr_idx != -1 and safe_float(row_vals[std_hr_idx]) > 0 and rpb > 0:
                                        rate_rings = safe_float(row_vals[std_hr_idx]) * rpb
                                        
                                    if rate_rings > 0:
                                        for ck in set(clean_keys):
                                            machines_data[current_m_type][current_m_num]['rates'][f"{ck}_{pc}"] = rate_rings
                                            
            PARSED_MASTER_DATA["production"] = (weight_matrix, furnace_map, machines_data, channel_flex_map, prod_cache_ts)
        del sheets_prod

        # 3. BUFFERS & REQUIREMENTS PERCOLATION
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
                    
                    display_name = get_display_name(val)
                    if is_invalid_part(display_name): continue
                    
                    buf_val = safe_float(payload.entries.get(f"{buf_prefix}_{col_channel}_{sub_ring_type}", 0))
                    if buf_val <= 0: continue
                    
                    if display_name not in buffers_by_fam:
                        buffers_by_fam[display_name] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[display_name][stage][sub_ring_type] += buf_val

        def process_requirements_for_day(demands, in_out_buffers):
            f_req, o_req, h_req = {}, {}, {}
            for display_name, data in demands.items():
                ch_norm = normalize_channel(data['channel'])
                for side in ['IR', 'OR']:
                    req_rings = data[side]
                    if req_rings <= 0: continue
                    
                    rpb = get_box_for_part(display_name, side, box_matrix)
                    flex = channel_flex_map.get(ch_norm, {}).get(side, {'FACE': True, 'OD': True})
                    req_face = flex['FACE']
                    req_od = flex['OD']
                    
                    def apply_buf(stage, base_rings, rpb_rate):
                        raw_buf = in_out_buffers.get(display_name, {}).get(stage, {}).get(side, 0)
                        if payload.unit_mode == 'Days': avail_buf_rings = raw_buf * base_rings
                        elif payload.unit_mode == 'Boxes': avail_buf_rings = raw_buf * (rpb_rate if rpb_rate > 0 else 100)
                        else: avail_buf_rings = raw_buf 
                        
                        if avail_buf_rings >= base_rings:
                            used_rings, rem_rings = base_rings, avail_buf_rings - base_rings
                        else:
                            used_rings, rem_rings = avail_buf_rings, 0.0
                            
                        if display_name in in_out_buffers:
                            if payload.unit_mode == 'Days': new_raw = (rem_rings / base_rings) if base_rings > 0 else 0
                            elif payload.unit_mode == 'Boxes': new_raw = rem_rings / (rpb_rate if rpb_rate > 0 else 100)
                            else: new_raw = rem_rings
                            in_out_buffers[display_name][stage][side] = new_raw
                        return used_rings

                    current_req = req_rings
                    
                    # Sequence: HT -> Face -> OD -> Channel
                    # If OD is required, subtract OD buffer to find OD requirement
                    if req_od:
                        used_buf = apply_buf('OD', current_req, rpb)
                        current_req = max(0.0, current_req - used_buf)
                        if current_req > 0:
                            if display_name not in o_req: o_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            o_req[display_name][side] += current_req
                    
                    # Face is required, pull from face buffer based on current required (either from OD or direct from CH)
                    if req_face:
                        used_buf = apply_buf('FACE', current_req, rpb)
                        current_req = max(0.0, current_req - used_buf)
                        if current_req > 0:
                            if display_name not in f_req: f_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            f_req[display_name][side] += current_req
                    
                    # HT requirement
                    used_buf = apply_buf('CH', current_req, rpb)
                    current_req = max(0.0, current_req - used_buf)
                    if current_req > 0:
                        if display_name not in h_req: h_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                        h_req[display_name][side] += current_req

            return f_req, o_req, h_req

        face_req_d1, od_req_d1, ht_req_d1 = process_requirements_for_day(channel_demands_day1, buffers_by_fam)
        face_req_d2, od_req_d2, ht_req_d2 = process_requirements_for_day(channel_demands_day2, buffers_by_fam)

        # ==========================================
        # 5. GLOBAL OPTIMIZATION SCHEDULING (Load Balancing)
        # ==========================================

        def allocate_grinding(m_type, dict_d1, dict_d2):
            m_state_dict = machines_data.get(m_type, {})
            allocated_result = {m_num: {"machine": m_num, "rows": []} for m_num in m_state_dict}
            machine_ready_time = {m_num: m_info.get('ready_time', 0.0) for m_num, m_info in m_state_dict.items()}
            machine_last_fam = {m_num: None for m_num in m_state_dict}
            
            def process_priority_pass(demands_dict, is_day_2=False):
                part_options = {}
                for display_name, data in demands_dict.items():
                    ch_normalized = normalize_channel(data['channel'])
                    for p_code in ['IR', 'OR']:
                        rings_needed = data[p_code]
                        if rings_needed <= 0: continue
                        
                        # Process flexibility enforced during requirements, but double check here
                        flex = channel_flex_map.get(ch_normalized, {}).get(p_code, {'FACE': True, 'OD': True})
                        if not flex.get(m_type, True): 
                            continue # Operation bypassed, skip scheduling completely
                        
                        compatible_machines = []
                        for m_num, m_info in m_state_dict.items():
                            rate = get_rate_for_part(display_name, p_code, m_info.get('rates', {}))
                            if rate > 0: compatible_machines.append((m_num, rate))
                        
                        if compatible_machines:
                            part_options[(display_name, p_code)] = {
                                'needed': rings_needed,
                                'channel': data['channel'],
                                'machines': compatible_machines
                            }
                        else:
                            day_label = "Day 2" if is_day_2 else "Day 1"
                            rpb = get_box_for_part(display_name, p_code, box_matrix)
                            missed_val = f"{int(rings_needed)} rings" if rpb <= 0 else f"{math.ceil(rings_needed / rpb)} Box"
                            unscheduled.append({ 
                                "stage": m_type, 
                                "part": f"{display_name} {p_code} ({day_label})", 
                                "missed_boxes": f"{missed_val} - Missing Machine Rate" 
                            })

                sorted_parts = sorted(part_options.keys(), key=lambda k: (len(part_options[k]['machines']), -part_options[k]['needed']))
                
                machine_versatility = {m: 0 for m in m_state_dict}
                for pk in sorted_parts:
                    for m_num, _ in part_options[pk]['machines']:
                        machine_versatility[m_num] += 1

                for pk in sorted_parts:
                    display_name, p_code = pk
                    rings_needed = part_options[pk]['needed']
                    candidates = part_options[pk]['machines']
                    
                    def get_machine_score(m_key, rate, qty):
                        ready_time = machine_ready_time[m_key]
                        setup = 2.0 if machine_last_fam[m_key] and machine_last_fam[m_key] != display_name else 0.0
                        end_time = ready_time + setup + (qty / rate)
                        versatility_penalty = machine_versatility.get(m_key, 0) * 1.5
                        return end_time + versatility_penalty

                    while rings_needed > 0:
                        best_cands = sorted(candidates, key=lambda x: get_machine_score(x[0], x[1], rings_needed))
                        best_m, best_rate = best_cands[0]
                        
                        max_chunk_hours = 8.0
                        chunk_qty = min(rings_needed, best_rate * max_chunk_hours)
                        if len(best_cands) == 1: 
                            chunk_qty = rings_needed
                            
                        setup_cost = 2.0 if machine_last_fam[best_m] and machine_last_fam[best_m] != display_name else 0.0
                        time_required = chunk_qty / best_rate
                        
                        start_rel = machine_ready_time[best_m] + setup_cost
                        end_rel = start_rel + time_required
                        
                        timing_display = f"{format_time(start_rel)}-{format_time(end_rel)}"

                        machine_ready_time[best_m] = end_rel
                        machine_last_fam[best_m] = display_name
                        rings_needed -= chunk_qty
                        
                        rpb, source, lookup_key = get_box_for_part_detailed(display_name, p_code, box_matrix)
                        
                        if rpb > 0:
                            calculated_boxes = math.ceil(chunk_qty / rpb)
                            display_val = f"{calculated_boxes} Boxes"
                        else:
                            display_val = f"{int(chunk_qty)} Rings"
                        
                        if display_name in monthly_data.get(month_str, {}):
                            monthly_data[month_str][display_name]["produced"] += chunk_qty
                        
                        allocated_result[best_m]["rows"].append({
                            "part": f"{display_name} {p_code}" + (" (D2)" if is_day_2 else ""),
                            "qty": str(int(chunk_qty)),
                            "std_box": display_val,
                            "timing": timing_display,
                            "p_2nd": "1" if len(allocated_result[best_m]["rows"]) == 0 else "",
                            "p_3rd": "1" if len(allocated_result[best_m]["rows"]) == 1 else "",
                            "alert": False,
                            "p_label": f"P{len(allocated_result[best_m]['rows']) + 1}"
                        })
                        
                        machine_versatility[best_m] = max(0, machine_versatility[best_m] - 1)

            process_priority_pass(dict_d1, False)
            process_priority_pass(dict_d2, True)
            return list(allocated_result.values())


        def schedule_ht_pass(demands, furnace_clocks, is_day_2=False):
            for display_name, data in sorted(demands.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True):
                for p_code in ['IR', 'OR']:
                    qty_rings = data[p_code]
                    if qty_rings <= 0: continue
                    
                    preferred_furnaces = get_furnaces_for_part(display_name, p_code, furnace_map)
                    unit_weight = get_weight_for_part(display_name, p_code, weight_matrix)
                    
                    if unit_weight is None or unit_weight <= 0:
                        rpb = get_box_for_part(display_name, p_code, box_matrix)
                        missed_val = f"{int(qty_rings)} rings" if rpb <= 0 else f"{math.ceil(qty_rings / rpb)} Box"
                        unscheduled.append({ 
                            "stage": "HT", 
                            "part": f"{display_name} {p_code} ({'Day 2' if is_day_2 else 'Day 1'})", 
                            "missed_boxes": f"{missed_val} - Missing Weight" 
                        })
                        continue
                    
                    total_weight_kg = qty_rings * unit_weight
                    
                    best_f = None
                    best_score = float('inf')
                    best_time_needed = 0.0
                    
                    for f_name in preferred_furnaces:
                        if f_name not in furnace_clocks: continue
                        
                        kg_per_hr = FURNACE_SPECS[f_name]
                        time_needed = total_weight_kg / kg_per_hr
                        ctx = furnace_clocks[f_name]
                        
                        setup_penalty = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != display_name) else 0.0
                        end_time = ctx["ready_time"] + setup_penalty + time_needed
                        
                        if end_time < best_score:
                            best_score = end_time
                            best_f = f_name
                            best_time_needed = time_needed
                            
                    if best_f:
                        ctx = furnace_clocks[best_f]
                        setup_penalty = 0.5 if (ctx["current_fam"] and ctx["current_fam"] != display_name) else 0.0
                        
                        start_rel = ctx["ready_time"] + setup_penalty
                        end_rel = start_rel + best_time_needed
                        timing_display = f"{format_time(start_rel)}-{format_time(end_rel)}"

                        ctx["ready_time"] = end_rel
                        ctx["current_fam"] = display_name
                        display_rate = f"{round(total_weight_kg, 1)} kg"
                        
                        ctx["rows"].append({
                            "part": f"{display_name}-{p_code}" + (" (D2)" if is_day_2 else ""), 
                            "qty": str(int(qty_rings)), 
                            "cha": data['channel'],
                            "rate": display_rate, 
                            "timing": timing_display,
                            "alert": False 
                        })
                    else:
                        rpb = get_box_for_part(display_name, p_code, box_matrix)
                        missed_val = f"{int(qty_rings)} rings" if rpb <= 0 else f"{math.ceil(qty_rings / rpb)} Box"
                        unscheduled.append({ "stage": "HT", "part": f"{display_name} {p_code}", "missed_boxes": f"{missed_val} - Capacity Error" })

        final_face = allocate_grinding('FACE', face_req_d1, face_req_d2)
        final_od = allocate_grinding('OD', od_req_d1, od_req_d2)
        
        furnaces_state = {f: {"ready_time": 0.0, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}
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
