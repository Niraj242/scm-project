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
    "box_matrix": ({}, 0),  
    "production": ({}, {}, {}, {}, 0) 
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

def get_lookup_variants(raw_text, p_code=None):
    if is_invalid_part(raw_text): return []
    t = str(raw_text).upper().strip()
    
    if "INDUSTRILA" in t: t = t.replace("INDUSTRILA", "INDUSTRIAL")
    if t.startswith("MF"): t = t[2:].strip()
    
    parts = [p.strip() for p in t.split('/') if p.strip()]
    numeric_parts = [p for p in parts if any(c.isdigit() for c in p) and len(re.sub(r'\D', '', p)) >= 3]
    
    if len(numeric_parts) >= 2 and p_code:
        if p_code == 'IR':
            t = parts[0]
        elif p_code == 'OR':
            t = numeric_parts[1]
    elif '/' in t:
        if not any(x in parts[1] for x in ['Q', 'X']):
            t = parts[0].strip()

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
    t_clean = re.sub(r'[\s\-_/.]', '', t_nosuff)
    
    prefixes_to_strip = ['BAH', 'BTH', 'BAR', 'BB1B', 'BB1', 'BB', 'BT1', 'BT', 'UC']
    t_nopfx = t_clean
    found_prefix = ""
    for pfx in prefixes_to_strip:
        if t_clean.startswith(pfx):
            t_nopfx = t_clean[len(pfx):]
            found_prefix = pfx
            break

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

def get_rate_for_part(display_name, p_code, rates):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in rates: 
            return rates[f"{var}_{p_code}"]
    return 0.0

def get_weight_for_part(display_name, p_code, weights):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in weights: 
            return weights[f"{var}_{p_code}"]
    return None

def get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs=None, logged_set=None):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if var in box_matrix and p_code in box_matrix[var]: 
            qty = box_matrix[var][p_code]['qty']
            source = box_matrix[var][p_code]['source']
            if debug_logs is not None and logged_set is not None:
                if (display_name, p_code) not in logged_set:
                    debug_logs.append(f"Bearing : {display_name} {p_code}\nVariants Checked :\n" + "\n".join(variants) + f"\nMatched :\n{var}\nSource :\n{source}\nRings/Box :\n{qty}")
                    logged_set.add((display_name, p_code))
            return qty, source, var
            
    if debug_logs is not None and logged_set is not None:
        if (display_name, p_code) not in logged_set:
            debug_logs.append(f"Bearing : {display_name} {p_code}\nVariants Checked :\n" + "\n".join(variants) + f"\nResult :\nNo Rings Per Box Found\nDisplaying:\nXXXX Rings (Q)")
            logged_set.add((display_name, p_code))
            
    return 0.0, "NONE", variants[0] if variants else display_name

def get_box_for_part(display_name, p_code, box_matrix, debug_logs=None, logged_set=None):
    qty, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs, logged_set)
    return qty

def get_furnaces_for_part(display_name, p_code, furnace_map):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in furnace_map: 
            return furnace_map[f"{var}_{p_code}"]
    return list(FURNACE_SPECS.keys())

def format_time(rel_hrs):
    rel_hrs = max(0.0, rel_hrs)
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
    logged_rpb = set()
    
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

        # 2. BOX MATRIX
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
                            for p_c in ['IR', 'OR']:
                                clean_keys = get_lookup_variants(f_raw, p_c)
                                for ck in clean_keys:
                                    or_qty = safe_float(row_vals[i+1])
                                    ir_qty = safe_float(row_vals[i+2])
                                    if ck not in box_matrix: box_matrix[ck] = {}
                                    if or_qty > 0 and p_c == 'OR': box_matrix[ck]['OR'] = {'qty': or_qty, 'source': 'RING PER BOX.'}
                                    if ir_qty > 0 and p_c == 'IR': box_matrix[ck]['IR'] = {'qty': ir_qty, 'source': 'RING PER BOX.'}
            
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
                            
                            for p_c in ['IR', 'OR']:
                                clean_keys = get_lookup_variants(raw_t, p_c)
                                for ck in clean_keys:
                                    if ck not in box_matrix: box_matrix[ck] = {}
                                    if p_c == 'IR' and ('IR' not in box_matrix[ck] or box_matrix[ck]['IR']['qty'] <= 0):
                                        fq = 0.0
                                        if ir_col != -1: fq = safe_float(row_vals[ir_col])
                                        elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                        if fq > 0: box_matrix[ck]['IR'] = {'qty': fq, 'source': fb_sheet}
                                    if p_c == 'OR' and ('OR' not in box_matrix[ck] or box_matrix[ck]['OR']['qty'] <= 0):
                                        fq = 0.0
                                        if or_col != -1: fq = safe_float(row_vals[or_col])
                                        elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                        if fq > 0: box_matrix[ck]['OR'] = {'qty': fq, 'source': fb_sheet}
            
            PARSED_MASTER_DATA["box_matrix"] = (box_matrix, box_cache_ts)
        del sheets_box

        # 4. PRODUCTION RATES & FLEXIBILITY 
        sheets_prod, logs3 = get_cached_excel_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        prod_cache_ts = EXCEL_CACHE.get(SHO_PRODUCTION_URL, (0, None))[0]

        if PARSED_MASTER_DATA["production"][4] == prod_cache_ts:
            weight_matrix, furnace_map, machines_data, channel_flex_map, _ = PARSED_MASTER_DATA["production"]
        elif sheets_prod:
            weight_matrix = {}
            furnace_map = {}
            machines_data = {'FACE': {}, 'OD': {}}
            channel_flex_map = {} 

            flex_sheet_key = next((k for k in sheets_prod.keys() if 'PROCESS' in str(k).upper() and 'FLEX' in str(k).upper()), None)
            if flex_sheet_key:
                df_flex = sheets_prod[flex_sheet_key].fillna('')
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
                            
                            ir_or_val = str(row_vals[ir_or_idx]).strip() if ir_or_idx != -1 else ""
                            part_code = 'OR' if '100' in ir_or_val else ('IR' if ('120' in ir_or_val or '010' in ir_or_val) else None)
                            if part_code and wt_idx != -1:
                                wt_val = safe_float(row_vals[wt_idx])
                                if wt_val > 0:
                                    clean_keys = get_lookup_variants(raw_fam, part_code)
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
                    if p_code:
                        clean_keys = get_lookup_variants(comp_level, p_code)
                        valid_furnaces = []
                        for fn_key in ['PRIMARY FURNA', 'PRIMARY FURNACE', 'ALTERNATIVE 1', 'ALTERNATIVE 2']:
                            fn = str(r.get(fn_key, '')).strip().upper()
                            if not fn or fn == 'NAN': continue
                            
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
                
                current_m_num = None
                current_m_type = "UNKNOWN"
                header_idx = -1
                
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
                            
                            for offset2 in range(1, 200):
                                if r + offset2 >= str_matrix.shape[0]: break
                                row_vals = str_matrix[r + offset2]
                                inner_row_text = " ".join(row_vals).upper()
                                if "MACHINE" in inner_row_text or "M/C" in inner_row_text: break 
                                
                                raw_t = str(row_vals[type_idx]).strip() if type_idx != -1 else ""
                                if is_invalid_part(raw_t): continue
                                
                                part_val = str(row_vals[part_idx]).strip().upper() if part_idx != -1 else ""
                                p_codes = []
                                if '100' in part_val or 'OR' in part_val: p_codes.append('OR')
                                if '120' in part_val or 'IR' in part_val or '010' in part_val: p_codes.append('IR')
                                if not p_codes: p_codes = ['IR', 'OR']
                                
                                for pc in p_codes:
                                    clean_keys = get_lookup_variants(raw_t, pc)
                                    comb_val = str(row_vals[comb_idx]).strip() if comb_idx != -1 else ""
                                    if comb_val and not is_invalid_part(comb_val):
                                        clean_keys.extend(get_lookup_variants(comb_val, pc))
                                        
                                    if not clean_keys: continue
                                        
                                    rate_rings = 0.0
                                    rpb = get_box_for_part(raw_t, pc, box_matrix, None, None)
                                    if rpb_idx != -1 and safe_float(row_vals[rpb_idx]) > 0:
                                        rpb = safe_float(row_vals[rpb_idx])
                                    
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

        # BUILD GLOBAL PRIORITY SCORING METRICS
        ch_stats = {}
        for d_dict in [channel_demands_day1, channel_demands_day2]:
            for fam, data in d_dict.items():
                ch = normalize_channel(data['channel'])
                if ch not in ch_stats: ch_stats[ch] = {'demand': 0.0, 'buffer': 0.0}
                ch_stats[ch]['demand'] += data.get('IR', 0) + data.get('OR', 0)
                
        fam_to_ch = {}
        for d_dict in [channel_demands_day1, channel_demands_day2]:
            for fam, data in d_dict.items():
                fam_to_ch[fam] = normalize_channel(data['channel'])
                
        for fam, stg_data in buffers_by_fam.items():
            ch = fam_to_ch.get(fam, "UNKNOWN")
            if ch not in ch_stats: ch_stats[ch] = {'demand': 0.0, 'buffer': 0.0}
            for stg, side_data in stg_data.items():
                ch_stats[ch]['buffer'] += side_data.get('IR', 0) + side_data.get('OR', 0)
                
        for ch, stats in ch_stats.items():
            stats['score'] = (stats['demand'] + 1.0) / (stats['buffer'] + 1.0)

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
                    
                    if req_od:
                        used_buf = apply_buf('OD', current_req, rpb)
                        current_req = max(0.0, current_req - used_buf)
                        if current_req > 0:
                            if display_name not in o_req: o_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            o_req[display_name][side] += current_req
                    
                    if req_face:
                        used_buf = apply_buf('FACE', current_req, rpb)
                        current_req = max(0.0, current_req - used_buf)
                        if current_req > 0:
                            if display_name not in f_req: f_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            f_req[display_name][side] += current_req
                    
                    used_buf = apply_buf('CH', current_req, rpb)
                    current_req = max(0.0, current_req - used_buf)
                    if current_req > 0:
                        if display_name not in h_req: h_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                        h_req[display_name][side] += current_req

            return f_req, o_req, h_req

        face_req_d1, od_req_d1, ht_req_d1 = process_requirements_for_day(channel_demands_day1, buffers_by_fam)
        face_req_d2, od_req_d2, ht_req_d2 = process_requirements_for_day(channel_demands_day2, buffers_by_fam)

        # ==========================================
        # 5. GLOBAL OPTIMIZATION SCHEDULING
        # Hybrid Demand-Driven & Resource-Centric Dispatch
        # ==========================================

        def allocate_ht(dict_d1, dict_d2, furnace_clocks, ht_out_time):
            tasks = []
            for day_idx, d_dict in [(0, dict_d1), (1, dict_d2)]:
                for display_name, data in d_dict.items():
                    for p_code in ['IR', 'OR']:
                        qty = data.get(p_code, 0)
                        if qty > 0:
                            weight = get_weight_for_part(display_name, p_code, weight_matrix)
                            if not weight:
                                ht_out_time[(display_name, p_code, day_idx)] = float('inf')
                                rpb, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs, logged_rpb)
                                missed_val = f"{int(qty)} Rings (Q)" if rpb <= 0 else f"{math.ceil(qty / rpb)} Boxes"
                                unscheduled.append({ 
                                    "stage": "HT", 
                                    "part": f"{display_name} {p_code} ({'Day 2' if day_idx==1 else 'Day 1'})", 
                                    "missed_boxes": f"{missed_val} - Missing Weight" 
                                })
                                continue
                                
                            channel = normalize_channel(data['channel'])
                            tasks.append({
                                'display_name': display_name,
                                'p_code': p_code,
                                'day_idx': day_idx,
                                'channel': channel,
                                'needed': qty,
                                'weight': weight,
                                'furnaces': get_furnaces_for_part(display_name, p_code, furnace_map)
                            })
            
            # Priority: Channel demand vs buffer, Flexibility, Due Day, Quantity
            tasks.sort(key=lambda t: (
                t['day_idx'],
                -ch_stats.get(t['channel'], {}).get('score', 0),
                len(t['furnaces']),
                -t['needed']
            ))
            
            furnace_blocked = {f: False for f in furnace_clocks}
            
            while True:
                active_fs = [f for f, blocked in furnace_blocked.items() if not blocked]
                if not active_fs: break
                
                earliest_f = min(active_fs, key=lambda f: furnace_clocks[f]['ready_time'])
                f_ready = furnace_clocks[earliest_f]['ready_time']
                
                best_task_idx = -1
                for i, t in enumerate(tasks):
                    if t['needed'] <= 0: continue
                    if earliest_f not in t['furnaces']: continue
                    best_task_idx = i
                    break
                    
                if best_task_idx == -1:
                    furnace_blocked[earliest_f] = True
                    continue
                    
                t = tasks[best_task_idx]
                disp, pc, d_idx = t['display_name'], t['p_code'], t['day_idx']
                qty = t['needed']
                total_weight = qty * t['weight']
                kg_per_hr = FURNACE_SPECS[earliest_f]
                
                ctx = furnace_clocks[earliest_f]
                setup = 0.5 if ctx['current_fam'] and ctx['current_fam'] != disp else 0.0
                start_rel = max(f_ready, 0.0) + setup
                
                if start_rel >= 24.0:
                    furnace_blocked[earliest_f] = True
                    continue
                
                max_time = 24.0 - start_rel
                time_needed = total_weight / kg_per_hr
                
                if time_needed > max_time:
                    actual_time = max_time
                    actual_weight = actual_time * kg_per_hr
                    actual_qty = actual_weight / t['weight']
                    furnace_blocked[earliest_f] = True
                else:
                    actual_time = time_needed
                    actual_weight = total_weight
                    actual_qty = qty
                    
                # Furnace batch timing rules: free to load next after loading finishes + 0.5
                f_free_time = start_rel + actual_time + 0.5
                # Part available for downstream Face Grinding after full 3.5h cycle
                part_ready_time = start_rel + actual_time + 3.5
                
                ctx['ready_time'] = f_free_time
                ctx['current_fam'] = disp
                
                # Keep track of max output time for precedence propagation in cases of multiple chunks
                current_out = ht_out_time.get((disp, pc, d_idx), 0.0)
                ht_out_time[(disp, pc, d_idx)] = max(current_out, part_ready_time)
                
                if f_free_time >= 24.0:
                    furnace_blocked[earliest_f] = True
                    
                t['needed'] -= actual_qty
                
                if disp in monthly_data.get(month_str, {}):
                    monthly_data[month_str][disp]["produced"] += actual_qty
                    
                timing_display = f"{format_time(start_rel)}-{format_time(part_ready_time)}"
                ctx["rows"].append({
                    "part": f"{disp}-{pc}" + (" (D2)" if d_idx==1 else ""),
                    "qty": str(int(actual_qty)),
                    "cha": t['channel'],
                    "rate": f"{round(actual_weight, 1)} kg",
                    "timing": timing_display,
                    "alert": False
                })

            for t in tasks:
                if t['needed'] > 0:
                    disp, pc, d_idx = t['display_name'], t['p_code'], t['day_idx']
                    ht_out_time[(disp, pc, d_idx)] = float('inf')
                    rpb, _, _ = get_box_for_part_detailed(disp, pc, box_matrix, debug_logs, logged_rpb)
                    missed_val = f"{int(t['needed'])} Rings (Q)" if rpb <= 0 else f"{math.ceil(t['needed'] / rpb)} Boxes"
                    
                    reason = "Furnace Capacity Exceeded"
                    if t['furnaces'] and all(furnace_blocked.get(f) or furnace_clocks.get(f, {}).get('ready_time', 24.0) >= 24.0 for f in t['furnaces']):
                        reason = "Exceeds Planning Window"
                        
                    unscheduled.append({ "stage": "HT", "part": f"{disp} {pc}", "missed_boxes": f"{missed_val} - {reason}" })


        def allocate_grinding(m_type, dict_d1, dict_d2, input_times, output_times):
            m_state_dict = machines_data.get(m_type, {})
            allocated_result = {m_num: {"machine": m_num, "rows": []} for m_num in m_state_dict}
            machine_ready_time = {m_num: m_info.get('ready_time', 0.0) for m_num, m_info in m_state_dict.items()}
            machine_last_fam = {m_num: None for m_num in m_state_dict}
            machine_blocked = {m: False for m in m_state_dict}
            
            tasks = []
            for day_idx, d_dict in [(0, dict_d1), (1, dict_d2)]:
                for display_name, data in d_dict.items():
                    ch_normalized = normalize_channel(data['channel'])
                    for p_code in ['IR', 'OR']:
                        rings_needed = data.get(p_code, 0)
                        if rings_needed <= 0: continue
                        
                        flex = channel_flex_map.get(ch_normalized, {}).get(p_code, {'FACE': True, 'OD': True})
                        if not flex.get(m_type, True): 
                            continue 
                        
                        compatible_machines = []
                        for m_num, m_info in m_state_dict.items():
                            rate = get_rate_for_part(display_name, p_code, m_info.get('rates', {}))
                            if rate > 0: compatible_machines.append((m_num, rate))
                                
                        if compatible_machines:
                            tasks.append({
                                'display_name': display_name,
                                'p_code': p_code,
                                'needed': rings_needed,
                                'channel': data['channel'],
                                'day_idx': day_idx,
                                'machines': compatible_machines
                            })
                        else:
                            output_times[(display_name, p_code, day_idx)] = float('inf')
                            day_label = "Day 2" if day_idx==1 else "Day 1"
                            rpb, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs, logged_rpb)
                            missed_val = f"{int(rings_needed)} Rings (Q)" if rpb <= 0 else f"{math.ceil(rings_needed / rpb)} Boxes"
                            unscheduled.append({ 
                                "stage": m_type, 
                                "part": f"{display_name} {p_code} ({day_label})", 
                                "missed_boxes": f"{missed_val} - Missing Machine Rate" 
                            })

            tasks.sort(key=lambda t: (
                t['day_idx'],
                -ch_stats.get(normalize_channel(t['channel']), {}).get('score', 0),
                len(t['machines']),
                -t['needed']
            ))

            while True:
                active_machines = [m for m, blocked in machine_blocked.items() if not blocked]
                if not active_machines: break
                
                earliest_m = min(active_machines, key=lambda m: machine_ready_time[m])
                m_ready = machine_ready_time[earliest_m]
                
                best_task_idx = -1
                
                # First pass: look for a task that is strictly available at or before this machine's ready time
                for i, t in enumerate(tasks):
                    if t['needed'] <= 0: continue
                    if earliest_m not in [m[0] for m in t['machines']]: continue
                    
                    inp_time = input_times.get((t['display_name'], t['p_code'], t['day_idx']), 0.0)
                    if inp_time <= m_ready:
                        best_task_idx = i
                        break
                
                # If no task is ready now, advance machine's clock to the earliest future available task
                if best_task_idx == -1:
                    earliest_future_inp = float('inf')
                    for i, t in enumerate(tasks):
                        if t['needed'] <= 0: continue
                        if earliest_m not in [m[0] for m in t['machines']]: continue
                        
                        inp_time = input_times.get((t['display_name'], t['p_code'], t['day_idx']), 0.0)
                        if inp_time < earliest_future_inp:
                            earliest_future_inp = inp_time
                            best_task_idx = i
                            
                    if best_task_idx != -1 and earliest_future_inp < 24.0:
                        machine_ready_time[earliest_m] = earliest_future_inp
                        m_ready = earliest_future_inp
                    else:
                        machine_blocked[earliest_m] = True
                        continue
                        
                if best_task_idx == -1:
                    machine_blocked[earliest_m] = True
                    continue
                    
                t = tasks[best_task_idx]
                disp, pc, d_idx = t['display_name'], t['p_code'], t['day_idx']
                
                rate = next(r for m, r in t['machines'] if m == earliest_m)
                setup = 2.0 if machine_last_fam[earliest_m] and machine_last_fam[earliest_m] != disp else 0.0
                
                start_rel = m_ready + setup
                if start_rel >= 24.0:
                    machine_blocked[earliest_m] = True
                    continue 
                    
                # Interleaved chunking for steady flow downstream
                max_chunk_hours = 8.0
                time_limit = min(24.0 - start_rel, max_chunk_hours)
                
                # If this is the last/only machine available, we can let it run out to the 24h limit
                if len(t['machines']) == 1:
                    time_limit = 24.0 - start_rel
                    
                chunk_qty = min(t['needed'], rate * time_limit)
                
                if chunk_qty <= 0:
                    machine_blocked[earliest_m] = True
                    continue
                    
                time_req = chunk_qty / rate
                end_rel = start_rel + time_req
                
                if end_rel >= 24.0:
                    machine_blocked[earliest_m] = True
                    
                machine_ready_time[earliest_m] = end_rel
                machine_last_fam[earliest_m] = disp
                
                current_out = output_times.get((disp, pc, d_idx), 0.0)
                output_times[(disp, pc, d_idx)] = max(current_out, end_rel)
                
                t['needed'] -= chunk_qty
                
                rpb, source, lookup_key = get_box_for_part_detailed(disp, pc, box_matrix, debug_logs, logged_rpb)
                if rpb > 0:
                    calculated_boxes = math.ceil(chunk_qty / rpb)
                    display_val = f"{calculated_boxes} Boxes"
                else:
                    display_val = f"{int(chunk_qty)} Rings (Q)"
                
                timing_display = f"{format_time(start_rel)}-{format_time(end_rel)}"
                
                allocated_result[earliest_m]["rows"].append({
                    "part": f"{disp} {pc}" + (" (D2)" if d_idx==1 else ""),
                    "qty": str(int(chunk_qty)),
                    "std_box": display_val,
                    "timing": timing_display,
                    "p_2nd": "1" if len(allocated_result[earliest_m]["rows"]) == 0 else "",
                    "p_3rd": "1" if len(allocated_result[earliest_m]["rows"]) == 1 else "",
                    "alert": False,
                    "p_label": f"P{len(allocated_result[earliest_m]['rows']) + 1}"
                })

            for t in tasks:
                if t['needed'] > 0:
                    disp, pc, d_idx = t['display_name'], t['p_code'], t['day_idx']
                    rpb, _, _ = get_box_for_part_detailed(disp, pc, box_matrix, debug_logs, logged_rpb)
                    missed_val = f"{int(t['needed'])} Rings (Q)" if rpb <= 0 else f"{math.ceil(t['needed'] / rpb)} Boxes"
                    
                    reason = "Machine Capacity Exceeded"
                    if t['machines'] and all(machine_blocked.get(m[0]) or machine_ready_time[m[0]] >= 24.0 for m in t['machines']):
                        reason = "Exceeds Planning Window"
                        
                    output_times[(disp, pc, d_idx)] = float('inf')
                    
                    unscheduled.append({
                        "stage": m_type,
                        "part": f"{disp} {pc}" + (" (D2)" if d_idx==1 else ""),
                        "missed_boxes": f"{missed_val} - {reason}"
                    })
                
            for m_num, m_info in m_state_dict.items():
                m_info['ready_time'] = machine_ready_time[m_num]
                
            return list(allocated_result.values())

        furnaces_state = {f: {"ready_time": 0.0, "current_fam": None, "rows": [], "capacity": cap} for f, cap in FURNACE_SPECS.items()}
        
        ht_out_time = {}
        allocate_ht(ht_req_d1, ht_req_d2, furnaces_state, ht_out_time)

        face_out_time = ht_out_time.copy()
        final_face = allocate_grinding('FACE', face_req_d1, face_req_d2, ht_out_time, face_out_time)
        
        od_out_time = face_out_time.copy()
        final_od = allocate_grinding('OD', od_req_d1, od_req_d2, face_out_time, od_out_time)
        
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
