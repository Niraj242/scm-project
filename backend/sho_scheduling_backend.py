import os
import re
import math
import pandas as pd
import requests
import io
import json
import time
import sqlite3
import pickle
from datetime import datetime, timedelta
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List

# ==========================================
# APP INITIALIZATION & CORS
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

EXCEL_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache

PARSED_MASTER_DATA = {
    "box_matrix": ({}, 0),  
    "production": ({}, {}, {}, {}, 0) 
}

RATE_CACHE = {}
WEIGHT_CACHE = {}
FURNACE_CACHE = {}

DEFAULT_FURNACES = {
    "AICHELIN.(896)": 350.0, "CASTLINK FURNACE( 1018 )": 250.0,
    "ROLLER FURNACE ( 148 )": 250.0, "SIMPLICITY FURNACE(1238)": 180.0,
    "BIRLEC FURNACE   ( 1158 )": 170.0, "SHOEI FURNACE    ( 1062 )": 350.0,
    "AICHELIN UNITHERM ( 2033 )": 250.0
}

# ==========================================
# DATABASE & PERSISTENCE
# ==========================================
DB_PATH = "sho_data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS daily_state (date TEXT PRIMARY KEY, state_json TEXT)')
        conn.commit()

init_db()

def get_setting(key, default=None):
    if default is None: default = {}
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key=?', (key,))
        row = c.fetchone()
        return json.loads(row[0]) if row else default

def save_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, json.dumps(value)))
        conn.commit()

def get_previous_day_state(target_date_str):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT state_json FROM daily_state WHERE date < ? ORDER BY date DESC LIMIT 1', (target_date_str,))
        row = c.fetchone()
        if row: return json.loads(row[0])
        return {"machines": {}, "wip": {}}

def save_daily_state(date_str, state_data):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('REPLACE INTO daily_state (date, state_json) VALUES (?, ?)', (date_str, json.dumps(state_data)))
        conn.commit()

def load_monthly_tracking(): return get_setting('monthly_tracking', {})
def save_monthly_tracking(data): save_setting('monthly_tracking', data)
def load_saved_plan(): return get_setting('saved_plan', {})

# ==========================================
# ROUTING CONFIGURATION
# ==========================================
PROCESS_FLOW = {
    ("CH1", "IR"): ["HT", "CHANNEL"], ("CH1", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("CH2", "IR"): ["HT", "CHANNEL"], ("CH2", "OR"): ["HT", "CHANNEL"],
    ("CH3", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("CH3", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("CH4", "IR"): ["HT", "CHANNEL"], ("CH4", "OR"): ["HT", "CHANNEL"],
    ("CH5", "IR"): ["HT", "FACE", "CHANNEL"], ("CH5", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("SABB", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("SABB", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("CH7", "IR"): ["CHANNEL"], ("CH7", "OR"): ["CHANNEL"],
    ("CH8", "IR"): ["HT", "FACE", "CHANNEL"], ("CH8", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("CH11", "IR"): ["HT", "FACE", "CHANNEL"], ("CH11", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("CH12", "IR"): ["CHANNEL"], ("CH12", "OR"): ["CHANNEL"],
    ("CH13", "IR"): ["CHANNEL"], ("CH13", "OR"): ["CHANNEL"],
    ("T1", "IR"): ["HT", "FACE", "CHANNEL"], ("T1", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T2", "IR"): ["HT", "FACE", "CHANNEL"], ("T2", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T3", "IR"): ["HT", "FACE", "CHANNEL"], ("T3", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T4", "IR"): ["HT", "FACE", "CHANNEL"], ("T4", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T5", "IR"): ["HT", "FACE", "CHANNEL"], ("T5", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T6", "IR"): ["HT", "FACE", "CHANNEL"], ("T6", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T7", "IR"): ["HT", "FACE", "CHANNEL"], ("T7", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T8", "IR"): ["HT", "CHANNEL"], ("T8", "OR"): ["HT", "CHANNEL"],
    ("T9", "IR"): ["HT", "CHANNEL"], ("T9", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T10", "IR"): ["HT", "FACE", "CHANNEL"], ("T10", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("T11", "IR"): ["CHANNEL"], ("T11", "OR"): ["CHANNEL"],
    ("HUB 1.1", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("HUB 1.1", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("HUB 1.2", "IR"): ["HT", "FACE", "CHANNEL"], ("HUB 1.2", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("HUB 1.3", "IR"): ["HT", "FACE", "CHANNEL"], ("HUB 1.3", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("HUB 1.4", "IR"): ["HT", "FACE", "CHANNEL"], ("HUB 1.4", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("HUB 3", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("HUB 3", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("THUB 1.1", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("THUB 1.1", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("THUB 1.2", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("THUB 1.2", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
    ("THUB 1.3", "IR"): ["HT", "FACE", "OD", "CHANNEL"], ("THUB 1.3", "OR"): ["HT", "FACE", "OD", "CHANNEL"],
}
DEFAULT_ROUTING = ["HT", "FACE", "OD", "CHANNEL"]

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any] = {}
    unlocked_blocks: List[str] = []
    machine_availability: Dict[str, Any] = {}

class SavePlanRequest(BaseModel):
    date: str
    plan: Dict[str, Any]

# ==========================================
# CORE UTILITIES & PARSERS
# ==========================================
def normalize_channel(ch_str):
    ch = str(ch_str).strip().upper()
    ch = ch.replace("CH", "").replace("CHANNEL", "").replace(" ", "").strip()
    if ch.isdigit(): return f"CH{int(ch)}"
    return ch

def normalize_resource_name(name):
    return re.sub(r'[\s().\-_]', '', str(name).upper())

def get_routing_for_part(channel_norm, p_code):
    return PROCESS_FLOW.get((channel_norm, p_code), DEFAULT_ROUTING)

def get_first_required_stage(routing):
    if not routing: return None
    first = routing[0]
    return first if first != "CHANNEL" else None

def get_next_required_stage(current_stage, routing):
    if current_stage in routing:
        idx = routing.index(current_stage)
        if idx + 1 < len(routing):
            next_st = routing[idx+1]
            if next_st == "CHANNEL": return None
            return next_st
    return None

def is_invalid_part(raw_text):
    if pd.isna(raw_text) or not raw_text: return True
    t = str(raw_text).upper()
    invalid_keywords = ["PROJECTED", "PLAN", "QTY", "HRS", "DAY", "NAN", "NONE", "UNKNOWN", "TYPE", "WIP", "MTD", "ASKING", "TOTAL"]
    for k in invalid_keywords:
        if k in t: return True
    return False

def get_lookup_variants(raw_text, p_code=None):
    if is_invalid_part(raw_text): return []
    t = str(raw_text).upper().strip()
    t = re.sub(r'[\u200b\u200c\u200d\uFEFF]', '', t)
    
    if "INDUSTRILA" in t: t = t.replace("INDUSTRILA", "INDUSTRIAL")
    if t.startswith("MF"): t = t[2:].strip()
    
    parts = [p.strip() for p in t.split('/') if p.strip()]
    numeric_parts = [p for p in parts if any(c.isdigit() for c in p) and len(re.sub(r'\D', '', p)) >= 3]
    
    if len(numeric_parts) >= 2 and p_code:
        if p_code == 'IR': t = parts[0]
        elif p_code == 'OR': t = numeric_parts[1]
    elif '/' in t:
        if not any(x in parts[1] for x in ['Q', 'X']): t = parts[0].strip()

    suffixes = ['VK210', 'X/Q', '/Q', 'J2', 'AE', 'AB', 'A', 'B', 'E', 'J', 'X', 'Q', 'LM', 'M']
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
    
    prefixes_to_strip = ['BAH', 'BTH', 'BAR', 'BB1B', 'BB1', 'BB', 'BT1', 'BT', 'UC', 'LM', 'FACE ', 'OD ', 'HT ', 'FACE', 'OD', 'HT']
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
    for pfx in ['FACE ', 'OD ', 'HT ', 'FACE', 'OD', 'HT']:
        if t.startswith(pfx): t = t[len(pfx):].strip()
    return t

def safe_float(val):
    if pd.isna(val) or val is None: return 0.0
    try:
        s_val = str(val).replace(',', '').strip().lower()
        if s_val in ['nan', 'none', '', 'null']: return 0.0
        return float(s_val)
    except Exception:
        return 0.0

def time_str_to_float(t_str):
    if not t_str: return 0.0
    try:
        if ':' in str(t_str):
            h, m = str(t_str).replace('(+1)', '').replace('(+2)', '').strip().split(':')
            abs_h = int(h) + int(m) / 60.0
            rel_h = abs_h - 10.0
            if rel_h < 0: rel_h += 24.0
            return float(rel_h)
        return float(t_str)
    except:
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
            return df_dict, [f"Loaded {file_label} from Memory Cache."]
            
    cache_file = f"cache_{file_label}.pkl"
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if now - mtime < CACHE_TTL:
            try:
                with open(cache_file, "rb") as f:
                    df_dict = pickle.load(f)
                EXCEL_CACHE[url] = (mtime, df_dict)
                return df_dict, [f"Loaded {file_label} from Disk Cache."]
            except Exception:
                pass 

    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200: 
            raise Exception(f"HTTP {resp.status_code}")
        content = io.BytesIO(resp.content)
        df_dict = pd.read_excel(content, sheet_name=None, header=None)
        
        with open(cache_file, "wb") as f:
            pickle.dump(df_dict, f)
            
        EXCEL_CACHE[url] = (now, df_dict)
        return df_dict, [f"Downloaded {file_label} from Network."]
    except Exception as e:
        raise Exception(f"Failed to load {file_label} Excel sheet: {str(e)}")

def load_box_matrix_data():
    global PARSED_MASTER_DATA
    sheets_box, _ = get_cached_excel_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
    box_cache_ts = EXCEL_CACHE.get(BOX_RING_DATA_URL, (0, None))[0]
    
    if PARSED_MASTER_DATA["box_matrix"][1] == box_cache_ts and box_cache_ts != 0:
        return PARSED_MASTER_DATA["box_matrix"][0]
        
    box_matrix = {}
    if sheets_box:
        for s_name, df_b in sheets_box.items():
            s_name_up = str(s_name).upper().strip()
            if 'RING' in s_name_up and 'BOX' in s_name_up:
                df_box = df_b.fillna('')
                for idx in range(1, len(df_box)):
                    row_vals = list(df_box.iloc[idx])
                    for i in range(0, len(row_vals) - 2, 3):
                        fam_raw = str(row_vals[i]).strip()
                        if not fam_raw or is_invalid_part(fam_raw): continue
                        fams_to_process = fam_raw.split("/") if "/" in fam_raw else [fam_raw]
                        for f_raw in fams_to_process:
                            for p_c in ['IR', 'OR']:
                                clean_keys = get_lookup_variants(f_raw, p_c)
                                for ck in clean_keys:
                                    or_qty = safe_float(row_vals[i+1])
                                    ir_qty = safe_float(row_vals[i+2])
                                    if ck not in box_matrix: box_matrix[ck] = {}
                                    if or_qty > 0 and p_c == 'OR': box_matrix[ck]['OR'] = {'qty': or_qty, 'source': s_name}
                                    if ir_qty > 0 and p_c == 'IR': box_matrix[ck]['IR'] = {'qty': ir_qty, 'source': s_name}
            elif 'BOX' in s_name_up and 'DAY' in s_name_up:
                df_fb = df_b.fillna('')
                type_col, ir_col, or_col, single_rpb_col = -1, -1, -1, -1
                for r_idx in range(min(20, len(df_fb))):
                    norm_strs = [re.sub(r'[\s./_\-]', '', str(x).strip().upper()) for x in df_fb.iloc[r_idx]]
                    t_c = next((j for j, h in enumerate(norm_strs) if 'TYPE' in h or 'BEARING' in h), -1)
                    i_c = next((j for j, h in enumerate(norm_strs) if 'IR' in h and 'BOX' in h), -1)
                    o_c = next((j for j, h in enumerate(norm_strs) if 'OR' in h and 'BOX' in h), -1)
                    s_c = next((j for j, h in enumerate(norm_strs) if 'RING' in h and 'BOX' in h and 'IR' not in h and 'OR' not in h), -1)
                    if t_c != -1 and (i_c != -1 or o_c != -1 or s_c != -1):
                        type_col, ir_col, or_col, single_rpb_col = t_c, i_c, o_c, s_c; break
                if type_col != -1:
                    for idx in range(r_idx + 1, len(df_fb)):
                        row_vals = list(df_fb.iloc[idx])
                        raw_t = str(row_vals[type_col]).strip()
                        if not raw_t or is_invalid_part(raw_t): continue
                        for p_c in ['IR', 'OR']:
                            clean_keys = get_lookup_variants(raw_t, p_c)
                            for ck in clean_keys:
                                if ck not in box_matrix: box_matrix[ck] = {}
                                if p_c == 'IR' and ('IR' not in box_matrix[ck] or box_matrix[ck]['IR']['qty'] <= 0):
                                    fq = safe_float(row_vals[ir_col]) if ir_col != -1 else (safe_float(row_vals[single_rpb_col]) if single_rpb_col != -1 else 0.0)
                                    if fq > 0: box_matrix[ck]['IR'] = {'qty': fq, 'source': s_name}
                                if p_c == 'OR' and ('OR' not in box_matrix[ck] or box_matrix[ck]['OR']['qty'] <= 0):
                                    fq = safe_float(row_vals[or_col]) if or_col != -1 else (safe_float(row_vals[single_rpb_col]) if single_rpb_col != -1 else 0.0)
                                    if fq > 0: box_matrix[ck]['OR'] = {'qty': fq, 'source': s_name}
        PARSED_MASTER_DATA["box_matrix"] = (box_matrix, box_cache_ts)
    return box_matrix

def load_production_data():
    global PARSED_MASTER_DATA
    prod_cache_ts = EXCEL_CACHE.get(SHO_PRODUCTION_URL, (0, None))[0]
    
    if PARSED_MASTER_DATA["production"][4] == prod_cache_ts and prod_cache_ts != 0:
        return PARSED_MASTER_DATA["production"]
        
    sheets_prod, _ = get_cached_excel_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
    weight_matrix = {}
    furnace_map = {}
    machines_data = {'FACE': {}, 'OD': {}}
    furnace_specs_local = DEFAULT_FURNACES.copy()
    box_matrix = load_box_matrix_data()

    if sheets_prod:
        for sheet_name, df_m in sheets_prod.items():
            if 'FURNACE' in str(sheet_name).upper() or 'AICHELIN' in str(sheet_name).upper():
                for r in range(len(df_m)):
                    row = df_m.iloc[r].values
                    f_name = str(row[0]).strip().upper() if len(row) > 0 else ""
                    cap = safe_float(row[1]) if len(row) > 1 else 0.0
                    if f_name and cap > 0 and ('FURNACE' in f_name or 'AICHELIN' in f_name or 'UNITHERM' in f_name):
                        furnace_specs_local[f_name] = cap
                        
        if 'WEIGHTS' in sheets_prod:
            df_w = sheets_prod['WEIGHTS'].fillna('')
            header_idx = -1
            for r_idx in range(min(10, len(df_w))):
                h_row = [str(x).strip().upper() for x in df_w.iloc[r_idx].values]
                if any('TYPE' in h for h in h_row) and any('IR/OR' in h or 'WEIGHT' in h or 'IR' in h for h in h_row):
                    header_idx = r_idx; break
            
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
                                for ck in clean_keys: weight_matrix[f"{ck}_{part_code}"] = wt_val

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
                        if fn == "AU" or "UNITHERM" in fn: matched_fn = "AICHELIN UNITHERM ( 2033 )"
                        elif "AICHELIN" in fn: matched_fn = "AICHELIN.(896)"
                        else: matched_fn = next((k for k in furnace_specs_local.keys() if fn[:4] in k.upper()), None)
                        if matched_fn and matched_fn not in valid_furnaces: valid_furnaces.append(matched_fn)
                    if valid_furnaces: 
                        for ck in clean_keys: furnace_map[f"{ck}_{p_code}"] = valid_furnaces
        
        for sheet_name, df_m in sheets_prod.items():
            if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.', 'Channel Process Flexibility']: continue
            str_matrix = df_m.fillna('').astype(str).values
            current_m_num = None
            current_m_type = "UNKNOWN"
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
                        box_hr_idx = next((j for j, h in enumerate(norm_headers) if 'BOX' in h and 'HR' in h), -1)
                        ring_hr_idx = next((j for j, h in enumerate(norm_headers) if ('RING' in h and 'HR' in h) or ('QTY' in h and 'HR' in h) or 'RATE' in h), -1)
                        rpb_idx = next((j for j, h in enumerate(norm_headers) if 'RING' in h and 'BOX' in h and 'HR' not in h), -1)
                        type_idx = next((j for j, h in enumerate(norm_headers) if 'TYPE' in h or 'BEARING' in h or 'PART' in h), -1)
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
                                if comb_val and not is_invalid_part(comb_val): clean_keys.extend(get_lookup_variants(comb_val, pc))
                                if not clean_keys: continue
                                    
                                rate_rings = 0.0
                                rpb = get_box_for_part(raw_t, pc, box_matrix)
                                if rpb_idx != -1 and safe_float(row_vals[rpb_idx]) > 0: rpb = safe_float(row_vals[rpb_idx])
                                if ring_hr_idx != -1 and safe_float(row_vals[ring_hr_idx]) > 0: rate_rings = safe_float(row_vals[ring_hr_idx])
                                elif box_hr_idx != -1 and safe_float(row_vals[box_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[box_hr_idx]) * rpb
                                elif std_hr_idx != -1 and safe_float(row_vals[std_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[std_hr_idx]) * rpb
                                    
                                if rate_rings > 0:
                                    for ck in set(clean_keys): machines_data[current_m_type][current_m_num]['rates'][f"{ck}_{pc}"] = rate_rings
                                        
        PARSED_MASTER_DATA["production"] = (weight_matrix, furnace_map, machines_data, furnace_specs_local, prod_cache_ts)
    return PARSED_MASTER_DATA["production"]

def get_rate_for_part(display_name, p_code, rates, res_id=""):
    key = (display_name, p_code, res_id)
    if key in RATE_CACHE: return RATE_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    robust_rates = {str(k).replace(" ", "").upper(): v for k, v in rates.items()}
    
    for var in variants:
        exact_key = f"{var}_{p_code}"
        if exact_key in rates:
            RATE_CACHE[key] = rates[exact_key]
            return RATE_CACHE[key]
            
        robust_key = exact_key.replace(" ", "").upper()
        if robust_key in robust_rates:
            RATE_CACHE[key] = robust_rates[robust_key]
            return RATE_CACHE[key]
            
    for var in variants:
        for rk, rv in robust_rates.items():
            if var in rk and p_code in rk:
                RATE_CACHE[key] = rv
                return rv
                
    RATE_CACHE[key] = 0.0
    return 0.0

def get_weight_for_part(display_name, p_code, weights):
    key = (display_name, p_code)
    if key in WEIGHT_CACHE: return WEIGHT_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in weights: 
            WEIGHT_CACHE[key] = weights[f"{var}_{p_code}"]
            return WEIGHT_CACHE[key]
            
    WEIGHT_CACHE[key] = None
    return None

def get_furnaces_for_part(display_name, p_code, furnace_map, furnace_specs):
    key = (display_name, p_code)
    if key in FURNACE_CACHE: return FURNACE_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in furnace_map: 
            FURNACE_CACHE[key] = furnace_map[f"{var}_{p_code}"]
            return FURNACE_CACHE[key]
            
    default_f = list(furnace_specs.keys())
    FURNACE_CACHE[key] = default_f
    return default_f

def get_box_for_part_detailed(display_name, p_code, box_matrix):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if var in box_matrix and p_code in box_matrix[var]: 
            qty = box_matrix[var][p_code]['qty']
            source = box_matrix[var][p_code]['source']
            return qty, source, var
            
    norm_disp = re.sub(r'[\s./_\-]', '', str(display_name).upper())
    for b_key, b_val in box_matrix.items():
        norm_bkey = re.sub(r'[\s./_\-]', '', str(b_key).upper())
        if norm_bkey in norm_disp or norm_disp in norm_bkey:
            if p_code in b_val:
                return b_val[p_code]['qty'], b_val[p_code]['source'], b_key
                
    return 0.0, "NONE", variants[0] if variants else display_name

def get_box_for_part(display_name, p_code, box_matrix):
    qty, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix)
    return qty

def format_time(rel_hrs):
    rel_hrs = max(0.0, rel_hrs)
    total_minutes = int(round(rel_hrs * 60))
    base_hour = 10 
    h = (base_hour + (total_minutes // 60)) % 24
    m = total_minutes % 60
    days_added = (base_hour + (total_minutes // 60)) // 24
    day_plus = f" (+{days_added})" if days_added > 0 else ""
    return f"{h:02d}:{m:02d}{day_plus}"

class WorkItem:
    def __init__(self, stage, disp, pc, day_idx, channel, qty, ready_time, priority, routing):
        self.stage = stage
        self.disp = disp
        self.pc = pc
        self.day_idx = day_idx
        self.channel = channel
        self.qty = qty
        self.ready_time = ready_time
        self.priority = priority
        self.routing = routing
        self.rates = {}
        self.valid_resources = []
        self.missing_reason = "Capacity Exceeded"

def init_item_resources(item, resources, furnace_map, weight_matrix, furnace_specs):
    item.rates = {}
    item.valid_resources = []
    item.missing_reason = "Capacity Exceeded"
    
    found_stage_machines = False
    missing_rate_flag = False
    missing_weight_flag = False
    
    for res in resources:
        if res.type != item.stage: continue
        found_stage_machines = True
        
        if res.type == 'HT':
            valid_furnaces = get_furnaces_for_part(item.disp, item.pc, furnace_map, furnace_specs)
            if res.id not in valid_furnaces: continue
            weight = get_weight_for_part(item.disp, item.pc, weight_matrix)
            if not weight: 
                missing_weight_flag = True
                continue 
            item.rates[res.id] = (res.capacity_info, weight)
            item.valid_resources.append(res)
        else:
            rate = get_rate_for_part(item.disp, item.pc, res.capacity_info, res.id)
            if rate > 0:
                item.rates[res.id] = rate
                item.valid_resources.append(res)
            else:
                missing_rate_flag = True
                
    if not found_stage_machines:
        item.missing_reason = f"No active machines for {item.stage}"
    elif len(item.valid_resources) == 0:
        if item.stage == 'HT' and missing_weight_flag:
            item.missing_reason = "Missing Part Weight"
        elif missing_rate_flag:
            item.missing_reason = "Missing Machine Rate"
        else:
            item.missing_reason = "No Valid Routing Found"

class Resource:
    def __init__(self, r_id, r_type, capacity_info):
        self.id = r_id
        self.type = r_type
        self.ready_time = 0.0
        self.max_time = 24.0
        self.last_fam = None
        self.last_pc = None  
        self.blocked = False
        self.has_bd = False
        self.bd_start = 0.0
        self.bd_end = 0.0
        self.capacity_info = capacity_info 
        self.rows = []

# ==========================================
# NEWLY IMPLEMENTED APIS (FIXES THE 404s)
# ==========================================
@router.get("/api/health")
def health_check():
    return {"status": "ok"}

@router.get("/api/machines")
def get_machines_list():
    """Dynamically parses and builds a non-redundant list of all operational machine IDs for the UI configuration."""
    weight_matrix, furnace_map, machines_data, furnace_specs_local, _ = load_production_data()
    
    unique_machines = set()
    unique_machines.update(furnace_specs_local.keys())
    unique_machines.update(machines_data.get('FACE', {}).keys())
    unique_machines.update(machines_data.get('OD', {}).keys())
    
    return sorted(list(unique_machines))

@router.get("/api/get_plan")
def get_saved_plan_by_date(date: str):
    """Retrieves the exact saved schedule array structure for a specific calendar target date."""
    plans = load_saved_plan()
    return plans.get(date, {})

@router.get("/api/monthly_tracking")
def get_monthly_tracking_api():
    return load_monthly_tracking()

@router.post("/api/save_plan")
def save_plan(payload: SavePlanRequest):
    try:
        plans = load_saved_plan()
        plans[payload.date] = payload.plan
        save_setting('saved_plan', plans)

        pending = get_setting('pending_state', {})
        if pending:
            if "monthly_data" in pending:
                month_str = payload.date[:7]
                monthly_all = load_monthly_tracking()
                monthly_all[month_str] = pending["monthly_data"]
                save_monthly_tracking(monthly_all)
            if "plant_state" in pending:
                save_daily_state(payload.date, pending["plant_state"])
            save_setting('pending_state', {})
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# ==========================================
# SCHEDULER SIMULATION ENGINE
# ==========================================
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = []
    
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day_1 = req_date  
        day_2 = req_date + timedelta(days=1)
        month_str = req_date.strftime("%Y-%m")
        
        monthly_data = load_monthly_tracking()
        if month_str not in monthly_data:
            monthly_data[month_str] = {}

        channel_demands_day1 = {} 
        channel_demands_day2 = {}
        
        sheets_zero, logs1 = get_cached_excel_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                sheet_str_upper = str(sheet_name).strip().upper()
                if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                    ch_name = f"CH{sheet_str_upper.zfill(2)}"
                elif sheet_str_upper == "SABB": ch_name = "SABB"
                elif sheet_str_upper.startswith("T ") or sheet_str_upper.startswith("T1") or sheet_str_upper.startswith("T2") or sheet_str_upper.startswith("T3") or sheet_str_upper.startswith("T4") or sheet_str_upper.startswith("T5") or sheet_str_upper.startswith("T6") or sheet_str_upper.startswith("T7") or sheet_str_upper.startswith("T8") or sheet_str_upper.startswith("T9"):
                    ch_name = sheet_str_upper
                elif "HUB" in sheet_str_upper: ch_name = sheet_str_upper
                else: ch_name = sheet_str_upper

                ir_multiplier = 2 if any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB"]) else 1
                
                r_idx, type_col_idx, mv_col_idx = None, None, None
                c1_col, c2_col = None, None
                monthly_cols = []
                
                for i in range(min(25, len(df_zero))):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[i].values]
                    row_joined = " ".join(row_strs)
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val == "TYPE" or "TYPE " in val or " TYPE" in val:
                                type_col_idx = j; break
                        if type_col_idx is None:
                            for j, val in enumerate(row_strs):
                                if val in ["MF", "PART NO", "BRG NO"]: type_col_idx = j; break
                    if mv_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["MV", "FV", "VAR", "VARIANT"]: mv_col_idx = j; break
                            
                    if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                        r_idx = i
                        for j, val in enumerate(df_zero.iloc[i].values):
                            if is_target_date(val, day_1): c1_col = j
                            if is_target_date(val, day_2): c2_col = j
                            s_val = str(val).strip()
                            if s_val.isdigit() and 1 <= int(s_val) <= 31: monthly_cols.append(j)
                    if r_idx is not None and type_col_idx is not None and c1_col is not None: break

                col_to_use = type_col_idx if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "SABB"] else mv_col_idx
                if col_to_use is None: col_to_use = mv_col_idx if mv_col_idx is not None else type_col_idx

                if r_idx is not None and type_col_idx is not None:
                    last_mf = ""
                    for idx in range(r_idx + 1, len(df_zero)):
                        mf_val = str(df_zero.iloc[idx, type_col_idx]).strip() if type_col_idx is not None else ""
                        if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                        raw_t = str(df_zero.iloc[idx, col_to_use]).strip() if col_to_use is not None else ""
                        if not raw_t or raw_t in ["NAN", "NONE"]: raw_t = last_mf
                        if is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        if display_name not in monthly_data[month_str]:
                            monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": ch_name}
                        
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0: monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2_col]) if c2_col is not None else 0.0
                        
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1: channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': ch_name}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1 * ir_multiplier)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)
                            
                        if r2 > 0:
                            if display_name not in channel_demands_day2: channel_demands_day2[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': ch_name}
                            channel_demands_day2[display_name]['IR'] = max(channel_demands_day2[display_name]['IR'], r2 * ir_multiplier)
                            channel_demands_day2[display_name]['OR'] = max(channel_demands_day2[display_name]['OR'], r2)

        del sheets_zero

        box_matrix = load_box_matrix_data()
        weight_matrix, furnace_map, machines_data, furnace_specs_local, _ = load_production_data()

        current_state = get_previous_day_state(payload.date)
        work_items = []
        resources = []
        
        for f_name, cap in furnace_specs_local.items(): resources.append(Resource(f_name, 'HT', cap))
        for m_num, m_info in machines_data.get('FACE', {}).items(): resources.append(Resource(m_num, 'FACE', m_info.get('rates', {})))
        for m_num, m_info in machines_data.get('OD', {}).items(): resources.append(Resource(m_num, 'OD', m_info.get('rates', {})))

        for res in resources:
            norm_res_id = normalize_resource_name(res.id)
            matched_state = None
            for sm_id, sm_data in current_state.get("machines", {}).items():
                if normalize_resource_name(sm_id) == norm_res_id:
                    matched_state = sm_data
                    break
            if matched_state:
                res.ready_time = float(matched_state.get("ready_time", 0.0))
                res.last_fam = matched_state.get("last_fam")
                res.last_pc = matched_state.get("last_pc")

        # STRICT WIP DEDUCTION LOGIC
        wip_deductions = {}
        for w_key, w_data in current_state.get("wip", {}).items():
            if "|" not in w_key: continue
            disp, pc = w_key.split('|')
            ch_norm = w_data.get("channel", "UNKNOWN")
            routing = get_routing_for_part(ch_norm, pc)
            
            for stage in ['HT', 'FACE', 'OD']:
                if stage not in routing: continue
                stage_data = w_data.get(stage, {})
                qty = float(stage_data.get("qty", 0.0))
                rt = float(stage_data.get("rt", 0.0))
                
                if qty > 0:
                    first_stage = get_first_required_stage(routing)
                    if stage != first_stage:
                        wip_deductions[(disp, pc)] = wip_deductions.get((disp, pc), 0.0) + qty
                        work_items.append(WorkItem(stage, disp, pc, -1, ch_norm, qty, rt, 10000.0, routing))

        ch_stats = {}
        for day_idx, demands in [(0, channel_demands_day1), (1, channel_demands_day2)]:
            for display_name, data in demands.items():
                ch_norm = normalize_channel(data['channel'])
                if ch_norm not in ch_stats: ch_stats[ch_norm] = {'demand': 0.0, 'buffer': 0.0, 'score': 1.0}
                ch_stats[ch_norm]['demand'] += data.get('IR', 0) + data.get('OR', 0)
                
                for p_code in ['IR', 'OR']:
                    req = float(data.get(p_code, 0.0))
                    if req <= 0: continue
                    routing = get_routing_for_part(ch_norm, p_code)
                    first_stage = get_first_required_stage(routing)
                    
                    if first_stage:
                        deduct = min(req, wip_deductions.get((display_name, p_code), 0.0))
                        if deduct > 0:
                            wip_deductions[(display_name, p_code)] -= deduct
                            req -= deduct

                    if req > 0 and first_stage:
                        work_items.append(WorkItem(first_stage, display_name, p_code, day_idx, data['channel'], req, 0.0, ch_stats[ch_norm]['score'], routing))

        avail_dict = payload.machine_availability if hasattr(payload, 'machine_availability') else {}
        for res in resources:
            conf = avail_dict.get(res.id, {})
            if conf:
                if not conf.get('enabled', True) or conf.get('off_whole_day', False): 
                    res.blocked = True
                else:
                    st_str = conf.get('start_time', '')
                    et_str = conf.get('end_time', '')
                    if st_str and et_str:
                        res.has_bd = True
                        res.bd_start = time_str_to_float(st_str)
                        res.bd_end = time_str_to_float(et_str)

        for item in work_items:
            init_item_resources(item, resources, furnace_map, weight_matrix, furnace_specs_local)

        # SIMULATION LOOP
        for target_day in [-1, 0, 1]:
            current_max_time = 24.0 
            
            for r in resources:
                r.max_time = current_max_time
                if r.ready_time < current_max_time:
                    r.blocked = False
                    
            while True:
                active_items = [i for i in work_items if i.qty > 0.01 and i.ready_time < current_max_time and i.day_idx == target_day]
                if not active_items: 
                    break 
                    
                best_pair = None
                best_key = (float('inf'), float('inf'), float('inf'), float('-inf'))
                
                for item in active_items:
                    for res in item.valid_resources:
                        if res.blocked or res.ready_time >= res.max_time: continue
                        
                        rate_or_cap = item.rates[res.id][0] if res.type == 'HT' else item.rates[res.id]
                        setup = 0.5 if res.type == 'HT' else 2.0
                        if res.last_fam == item.disp: setup = 0.0 if res.last_pc == item.pc else 2.0 
                        
                        start_time = max(res.ready_time + setup, item.ready_time)
                        if start_time >= res.max_time: continue
                        
                        is_continuation = (res.last_fam == item.disp and res.last_pc == item.pc and start_time <= res.ready_time + 0.01)
                        gap = max(0.0, item.ready_time - (res.ready_time + setup))
                        
                        key = (start_time, item.day_idx, gap, -item.priority)
                        
                        if key < best_key:
                            best_key = key
                            best_pair = (res, item, start_time, setup, rate_or_cap, is_continuation)
                            
                if not best_pair: 
                    break
                    
                res, item, start_time, setup, rate_or_cap, is_continuation = best_pair
                
                if res.type == 'HT':
                    weight = item.rates[res.id][1]
                    est_runtime = (item.qty * weight) / rate_or_cap
                    merge_threshold = 1.0
                else:
                    est_runtime = item.qty / rate_or_cap
                    merge_threshold = 2.0
                    
                if item.day_idx in [-1, 0] and est_runtime < merge_threshold:
                    for tomorrow_item in work_items:
                        if (tomorrow_item.day_idx == 1 and 
                            tomorrow_item.disp == item.disp and 
                            tomorrow_item.pc == item.pc and 
                            tomorrow_item.stage == item.stage and 
                            tomorrow_item.channel == item.channel and 
                            tomorrow_item.qty > 0.01):
                            
                            item.qty += tomorrow_item.qty
                            tomorrow_item.qty = 0.0 
                            break
                
                chunk_qty = item.qty
                
                if res.type == 'HT':
                    weight = item.rates[res.id][1]
                    actual_time = (chunk_qty * weight) / rate_or_cap
                    if res.has_bd and start_time < res.bd_end and (start_time + actual_time) > res.bd_start:
                        actual_time += (res.bd_end - max(start_time, res.bd_start))
                    res_ready_time = start_time + actual_time + 0.5
                    out_time = start_time + actual_time + 3.5
                    display_rate = f"{round((chunk_qty * weight), 1)} kg"
                    if item.disp in monthly_data.get(month_str, {}): monthly_data[month_str][item.disp]["produced"] += chunk_qty
                else:
                    actual_time = chunk_qty / rate_or_cap
                    if res.has_bd and start_time < res.bd_end and (start_time + actual_time) > res.bd_start:
                        actual_time += (res.bd_end - max(start_time, res.bd_start))
                    res_ready_time = start_time + actual_time
                    out_time = res_ready_time
                    display_rate = rate_or_cap
                    
                is_same_item = (res.last_fam == item.disp and res.last_pc == item.pc)
                res.ready_time = res_ready_time
                res.last_fam = item.disp
                res.last_pc = item.pc
                
                if res.ready_time >= res.max_time: res.blocked = True
                item.qty -= chunk_qty
                
                next_stage = get_next_required_stage(res.type, item.routing)
                if next_stage: 
                    new_item = WorkItem(next_stage, item.disp, item.pc, item.day_idx, item.channel, chunk_qty, out_time, item.priority, item.routing)
                    init_item_resources(new_item, resources, furnace_map, weight_matrix, furnace_specs_local)
                    work_items.append(new_item)

                rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix)
                can_merge = (res.type != 'HT' and res.rows and is_same_item and is_continuation)
                
                if item.day_idx == -1: day_label = " (WIP)"
                else: day_label = " (D2)" if item.day_idx == 1 else " (D1)"

                if can_merge:
                    last_row = res.rows[-1]
                    old_qty = int(float(last_row["qty"]))
                    new_qty = old_qty + int(chunk_qty)
                    last_row["qty"] = str(new_qty)
                    
                    old_start = last_row["timing"].split('-')[0]
                    new_end = format_time(out_time if res.type == 'HT' else res_ready_time)
                    last_row["timing"] = f"{old_start}-{new_end}"
                    
                    display_val = f"{int(new_qty)} Rings ({math.ceil(new_qty / rpb)} Boxes)" if rpb > 0 else f"{int(new_qty)} Rings"
                    if res.type != 'HT': last_row["std_box"] = display_val
                else:
                    display_val = f"{int(chunk_qty)} Rings ({math.ceil(chunk_qty / rpb)} Boxes)" if rpb > 0 else f"{int(chunk_qty)} Rings"
                    timing_display = f"{format_time(start_time)}-{format_time(out_time if res.type == 'HT' else res_ready_time)}"
                    is_terminal = (next_stage is None)
                    
                    if res.type == 'HT': res.rows.append({"part": f"{item.disp}-{item.pc}{day_label}", "qty": str(int(chunk_qty)), "cha": item.channel, "rate": display_rate, "timing": timing_display, "alert": False, "is_terminal": is_terminal})
                    else: res.rows.append({"part": f"{item.disp} {item.pc}{day_label}", "qty": str(int(chunk_qty)), "std_box": display_val, "timing": timing_display, "p_2nd": "1" if len(res.rows) == 0 else "", "p_3rd": "1" if len(res.rows) == 1 else "", "alert": False, "p_label": f"P{len(res.rows) + 1}", "is_terminal": is_terminal})

        end_state = { "machines": {}, "wip": {} }

        for r in resources:
            end_state["machines"][r.id] = {
                "ready_time": max(0.0, r.ready_time - 24.0),
                "last_fam": r.last_fam,
                "last_pc": r.last_pc
            }

        for item in work_items:
            if item.qty <= 0.01: continue
            
            if len(item.valid_resources) > 0 and item.missing_reason == "Capacity Exceeded":
                item.missing_reason = "Exceeds Production Window"

            if item.stage != get_first_required_stage(item.routing):
                w_key = f"{item.disp}|{item.pc}"
                if w_key not in end_state["wip"]: 
                    end_state["wip"][w_key] = {"channel": item.channel}
                
                if item.stage not in end_state["wip"][w_key]:
                    end_state["wip"][w_key][item.stage] = {"qty": 0.0, "rt": 0.0}
                end_state["wip"][w_key][item.stage]["qty"] += item.qty
                end_state["wip"][w_key][item.stage]["rt"] = max(0.0, item.ready_time - 24.0)

            rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix)
            unscheduled.append({
                "part": f"{item.disp} {item.pc}",
                "channel": item.channel,
                "missing": item.stage,
                "qty": str(int(item.qty)),
                "boxes": str(math.ceil(item.qty / rpb)) if rpb > 0 else "0",
                "reason": item.missing_reason,
                "alert": True
            })

        save_setting('pending_state', {
            "monthly_data": monthly_data.get(month_str, {}),
            "plant_state": end_state
        })

        schedule = {}
        for r in resources:
            if not r.rows: continue
            block = f"{r.type}_block"
            if block not in schedule: schedule[block] = []
            
            mc_name = str(r.id)
            if mc_name.startswith("MC_"): mc_name = mc_name[3:]
            
            if r.type == 'HT':
                for i, row in enumerate(r.rows):
                    schedule[block].append({
                        "mc_no": mc_name if i == 0 else "",
                        "part": row["part"],
                        "qty": row["qty"],
                        "cha": row["cha"],
                        "rate": row["rate"],
                        "timing": row["timing"],
                        "alert": row["alert"],
                        "is_terminal": row["is_terminal"]
                    })
            else:
                formatted_rows = {}
                for i, row in enumerate(r.rows):
                    if i >= 3: break
                    col_key = f"p_1st" if i == 0 else f"p_{i+1}th" if i > 2 else f"p_{i+1}nd" if i == 1 else f"p_{i+1}rd"
                    formatted_rows[f"{col_key}_part"] = row["part"]
                    formatted_rows[f"{col_key}_std_box"] = row["std_box"]
                    formatted_rows[f"{col_key}_timing"] = row["timing"]
                    formatted_rows[f"{col_key}_alert"] = row["alert"]
                    formatted_rows[f"{col_key}_is_terminal"] = row.get("is_terminal", False)
                if formatted_rows:
                    formatted_rows["mc_no"] = mc_name
                    schedule[block].append(formatted_rows)
                    
        return {
            "status": "success",
            "schedule": schedule,
            "unscheduled": unscheduled,
            "debug": debug_logs
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e), "debug": debug_logs}

# ==========================================
# MOUNT ROUTER AT THE BOTTOM
# ==========================================
app.include_router(router)
