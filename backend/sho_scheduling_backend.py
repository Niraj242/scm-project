import os
import re
import math
import pandas as pd
import requests
import io
import json
import time
import sqlite3
import gc
import threading
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List
import psycopg2

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "") # Standard Neon connection string

# Cache tables limited to the lifecycle of a single request
RATE_CACHE = {}
WEIGHT_CACHE = {}
FURNACE_CACHE = {}
VARIANTS_CACHE = {}  # OPTIMIZATION: Cache variants to prevent heavy nested regex operations

DEFAULT_FURNACES = {
    "AICHELIN.(896)": 350.0, 
    "CASTLINK FURNACE( 1018 )": 250.0,
    "ROLLER FURNACE ( 148 )": 250.0, 
    "SIMPLICITY FURNACE(1238)": 180.0,
    "BIRLEC FURNACE   ( 1158 )": 170.0, 
    "SHOEI FURNACE    ( 1062 )": 350.0,
    "AICHELIN UNITHERM ( 2033 )": 250.0
}

# ==========================================
# IN-MEMORY CACHE FOR STATIC MASTER DATA
# ==========================================
GLOBAL_PART_TO_CHANNEL = {}

MASTER_DATA_CACHE = {
    "weights": {},
    "furnace_type_flexibility": {},
    "face_machine_compatibility": {},
    "od_machine_compatibility": {},
    "ring_per_box": {},
    "box_per_day_dgbb": {},
    "box_per_day_trb": {},
    "setup_chart": {},
    "machine_master": {},
    "channels": [],
    "furnaces_specs": DEFAULT_FURNACES.copy(),
    "box_matrix": {}
}

# ==========================================
# CACHING & MEMORY OPTIMIZATION (RENDER FIX)
# ==========================================
GLOBAL_EXCEL_CACHE = {}
CACHE_TTL = 180  # 3 minutes

def zeroset_sheet_filter(sheet_name: str) -> bool:
    s = str(sheet_name).strip().upper()
    if s in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
        return True
    if s == "SABB":
        return True
    if s.startswith("T") or "HUB" in s:
        return True
    return False

def box_ring_sheet_filter(sheet_name: str) -> bool:
    s = str(sheet_name).strip().upper()
    return "RING" in s or "BOX" in s or "SETUP" in s or "CHART" in s

def prod_master_sheet_filter(sheet_name: str) -> bool:
    s = str(sheet_name).strip().upper()
    if any(k in s for k in ["INDEX", "README", "INSTRUCTION", "DASHBOARD", "SUMMARY", "TEMPLATE"]):
        return False
    return True

def get_excel_sheets_cached(url: str, sheet_filter_fn=None):
    if not url or url.strip() == "": 
        return
    now = time.time()
    
    if url in GLOBAL_EXCEL_CACHE:
        cache_entry = GLOBAL_EXCEL_CACHE[url]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            for sheet, data in cache_entry["sheets"].items():
                if sheet_filter_fn and not sheet_filter_fn(sheet):
                    continue
                yield sheet, pd.DataFrame(data)
            return

    sheets_data = {}
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            with io.BytesIO(resp.content) as file_buffer:
                try:
                    xls = pd.ExcelFile(file_buffer, engine='calamine')
                except Exception:
                    xls = pd.ExcelFile(file_buffer, engine='openpyxl')
                    
                for sheet in xls.sheet_names:
                    if sheet_filter_fn and not sheet_filter_fn(sheet):
                        continue
                    df = pd.read_excel(xls, sheet_name=sheet, header=None)
                    df_clean = df.fillna('')
                    sheets_data[sheet] = df_clean.values.tolist()
                    del df
                    del df_clean
                    gc.collect()
                del xls
            
            GLOBAL_EXCEL_CACHE[url] = {
                "timestamp": now,
                "sheets": sheets_data
            }
        del resp
        gc.collect()
    except Exception as e:
        print(f"Error caching excel from {url}: {e}")
        
    if url in GLOBAL_EXCEL_CACHE:
        for sheet, data in GLOBAL_EXCEL_CACHE[url]["sheets"].items():
            if sheet_filter_fn and not sheet_filter_fn(sheet):
                continue
            yield sheet, pd.DataFrame(data)

# ==========================================
# NEON POSTGRESQL & LOCAL SQLITE PERSISTENCE
# ==========================================
DB_PATH = "sho_data.db"

def get_neon_conn():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set! Please configure Neon database connection.")
    return psycopg2.connect(DATABASE_URL)

def init_neon_tables():
    conn = None
    try:
        conn = get_neon_conn()
        with conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS weights (
                part_type TEXT,
                part_code TEXT,
                weight NUMERIC,
                PRIMARY KEY (part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS furnace_type_flexibility (
                comp_level TEXT,
                part_code TEXT,
                furnaces TEXT,
                PRIMARY KEY (comp_level, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS face_machine_compatibility (
                machine_name TEXT,
                part_type TEXT,
                part_code TEXT,
                rate NUMERIC,
                PRIMARY KEY (machine_name, part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS od_machine_compatibility (
                machine_name TEXT,
                part_type TEXT,
                part_code TEXT,
                rate NUMERIC,
                PRIMARY KEY (machine_name, part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ring_per_box (
                part_type TEXT,
                part_code TEXT,
                qty NUMERIC,
                source TEXT,
                PRIMARY KEY (part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS box_per_day_dgbb (
                part_type TEXT,
                part_code TEXT,
                qty NUMERIC,
                source TEXT,
                PRIMARY KEY (part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS box_per_day_trb (
                part_type TEXT,
                part_code TEXT,
                qty NUMERIC,
                source TEXT,
                PRIMARY KEY (part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS setup_chart (
                part_type TEXT,
                part_code TEXT,
                temp NUMERIC,
                PRIMARY KEY (part_type, part_code)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS machine_master (
                machine_name TEXT PRIMARY KEY,
                machine_type TEXT
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_master (
                channel_name TEXT PRIMARY KEY
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS breakdowns (
                date TEXT,
                resource TEXT,
                status TEXT,
                start_time TEXT,
                end_time TEXT,
                PRIMARY KEY (date, resource)
            );
            """)
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error initializing Neon tables: {e}")
        raise e
    finally:
        if conn:
            conn.close()

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
# NEON IN-MEMORY CACHE LOADING ENGINE
# ==========================================
def load_master_data_from_neon():
    conn = None
    try:
        conn = get_neon_conn()
        with conn.cursor() as cursor:
            # 1. Weights
            cursor.execute("SELECT part_type, part_code, weight FROM weights")
            weights = {}
            for r in cursor.fetchall():
                weights[f"{r[0]}_{r[1]}"] = float(r[2])
            MASTER_DATA_CACHE["weights"] = weights
            
            # 2. Furnace flexibility
            cursor.execute("SELECT comp_level, part_code, furnaces FROM furnace_type_flexibility")
            furnace_map = {}
            for r in cursor.fetchall():
                furnaces_list = [f.strip() for f in r[2].split(",") if f.strip()]
                furnace_map[f"{r[0]}_{r[1]}"] = furnaces_list
            MASTER_DATA_CACHE["furnace_type_flexibility"] = furnace_map
            
            # 3. Face Grinding compatibilities
            cursor.execute("SELECT machine_name, part_type, part_code, rate FROM face_machine_compatibility")
            face_rates = {}
            for r in cursor.fetchall():
                m_name, part, pc, rate = r[0], r[1], r[2], float(r[3])
                if m_name not in face_rates:
                    face_rates[m_name] = {}
                face_rates[m_name][f"{part}_{pc}"] = rate
            MASTER_DATA_CACHE["face_machine_compatibility"] = face_rates
            
            # 4. OD Grinding compatibilities
            cursor.execute("SELECT machine_name, part_type, part_code, rate FROM od_machine_compatibility")
            od_rates = {}
            for r in cursor.fetchall():
                m_name, part, pc, rate = r[0], r[1], r[2], float(r[3])
                if m_name not in od_rates:
                    od_rates[m_name] = {}
                od_rates[m_name][f"{part}_{pc}"] = rate
            MASTER_DATA_CACHE["od_machine_compatibility"] = od_rates
            
            # 5. Ring per box
            cursor.execute("SELECT part_type, part_code, qty, source FROM ring_per_box")
            rpb_data = {}
            for r in cursor.fetchall():
                part, pc, qty, src = r[0], r[1], float(r[2]), r[3]
                if part not in rpb_data: rpb_data[part] = {}
                rpb_data[part][pc] = {'qty': qty, 'source': src}
            MASTER_DATA_CACHE["ring_per_box"] = rpb_data
            
            # 6. Box per day DGBB
            cursor.execute("SELECT part_type, part_code, qty, source FROM box_per_day_dgbb")
            dgbb_data = {}
            for r in cursor.fetchall():
                part, pc, qty, src = r[0], r[1], float(r[2]), r[3]
                if part not in dgbb_data: dgbb_data[part] = {}
                dgbb_data[part][pc] = {'qty': qty, 'source': src}
            MASTER_DATA_CACHE["box_per_day_dgbb"] = dgbb_data
            
            # 7. Box per day TRB
            cursor.execute("SELECT part_type, part_code, qty, source FROM box_per_day_trb")
            trb_data = {}
            for r in cursor.fetchall():
                part, pc, qty, src = r[0], r[1], float(r[2]), r[3]
                if part not in trb_data: trb_data[part] = {}
                trb_data[part][pc] = {'qty': qty, 'source': src}
            MASTER_DATA_CACHE["box_per_day_trb"] = trb_data
            
            # Compile box matrix matching order
            box_matrix = {}
            for data_dict in [rpb_data, dgbb_data, trb_data]:
                for part_key, part_data in data_dict.items():
                    if part_key not in box_matrix: box_matrix[part_key] = {}
                    for p_code, details in part_data.items():
                        if details.get('qty', 0.0) > 0:
                            box_matrix[part_key][p_code] = details
            MASTER_DATA_CACHE["box_matrix"] = box_matrix
            
            # 8. Setup chart
            cursor.execute("SELECT part_type, part_code, temp FROM setup_chart")
            setup_chart = {}
            for r in cursor.fetchall():
                setup_chart[(r[0], r[1])] = float(r[2])
            MASTER_DATA_CACHE["setup_chart"] = setup_chart
            
            # 9. Machine master
            cursor.execute("SELECT machine_name, machine_type FROM machine_master")
            machines = {}
            for r in cursor.fetchall():
                machines[r[0]] = r[1]
            MASTER_DATA_CACHE["machine_master"] = machines
            
            # 10. Channel master
            cursor.execute("SELECT channel_name FROM channel_master")
            channels = [r[0] for r in cursor.fetchall()]
            MASTER_DATA_CACHE["channels"] = channels
            
            # Furnace specification capacities
            furnaces_specs = DEFAULT_FURNACES.copy()
            for m_name, m_type in machines.items():
                if m_type == "HT":
                    if m_name in DEFAULT_FURNACES:
                        furnaces_specs[m_name] = DEFAULT_FURNACES[m_name]
                    else:
                        furnaces_specs[m_name] = 250.0
            MASTER_DATA_CACHE["furnaces_specs"] = furnaces_specs
            
        print("Successfully loaded master data cache from Neon!")
    except Exception as e:
        print(f"Error loading master data cache from Neon: {e}")
    finally:
        if conn:
            conn.close()

# ==========================================
# BACKGROUND SYNCHRONIZER (HOURLY)
# ==========================================
def upsert_rows(conn, table_name, columns, conflict_cols, rows):
    if not rows: return
    col_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_str = ", ".join(conflict_cols)
    update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict_cols])
    
    if update_str:
        query = f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str};"
    else:
        query = f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_str}) DO NOTHING;"
        
    with conn.cursor() as cursor:
        cursor.executemany(query, rows)

def parse_weights_sheet(df_m):
    rows = []
    df_w = df_m.fillna('')
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
                row_vals = list(df_w.iloc[header_idx + offset].values)
                raw_fam = str(row_vals[type_idx]).strip() if (type_idx != -1 and type_idx < len(row_vals)) else ""
                if is_invalid_part(raw_fam): continue
                ir_or_val = str(row_vals[ir_or_idx]).strip() if (ir_or_idx != -1 and ir_or_idx < len(row_vals)) else ""
                part_code = 'OR' if '100' in ir_or_val else ('IR' if ('120' in ir_or_val or '010' in ir_or_val) else None)
                if part_code and wt_idx != -1 and wt_idx < len(row_vals):
                    wt_val = safe_float(row_vals[wt_idx])
                    if wt_val > 0:
                        clean_keys = get_lookup_variants(raw_fam, part_code)
                        for ck in clean_keys:
                            rows.append((ck, part_code, wt_val))
    return rows

def parse_furnace_flex_sheet(df_f, furnace_specs_local):
    rows = []
    if len(df_f) > 0:
        headers = [str(x).strip().upper() for x in df_f.iloc[0]]
        for idx, r_row in df_f.iloc[1:].iterrows():
            r = pd.Series(r_row.values, index=headers)
            comp_level = str(r_row.iloc[0]).strip() if len(r_row) > 0 else ""
            if is_invalid_part(comp_level): continue
            p_code = 'IR' if comp_level.startswith('IM') else ('OR' if comp_level.startswith('OM') else None)
            if p_code:
                clean_keys = get_lookup_variants(comp_level, p_code)
                valid_furnaces = []
                for fn_key in ['PRIMARY FURNA', 'PRIMARY FURNACE', 'ALTERNATIVE 1', 'ALTERNATIVE 2']:
                    fn = str(r.get(fn_key, '')).strip().upper() if fn_key in r else ""
                    if not fn or fn == 'NAN': continue
                    matched_fn = None
                    if fn == "AU" or "UNITHERM" in fn: matched_fn = "AICHELIN UNITHERM ( 2033 )"
                    elif "AICHELIN" in fn: matched_fn = "AICHELIN.(896)"
                    else: matched_fn = next((k for k in furnace_specs_local.keys() if fn[:4] in k.upper()), None)
                    if matched_fn and matched_fn not in valid_furnaces: valid_furnaces.append(matched_fn)
                if valid_furnaces:
                    furnaces_str = ",".join(valid_furnaces)
                    for ck in clean_keys:
                        rows.append((ck, p_code, furnaces_str))
    return rows

def parse_machine_comp_sheets(sheet_name, df_m, box_matrix):
    face_rows, od_rows, machine_master_rows = [], [], []
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
                
                if current_m_num:
                    machine_master_rows.append((current_m_num, current_m_type))
        
        if current_m_num and current_m_type in ['FACE', 'OD']:
            h_row = [c.strip().upper() for c in str_matrix[r]]
            if any('TYPE' in h or 'PART' in h for h in h_row) and any('HR' in h for h in h_row):
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
                    raw_t = str(row_vals[type_idx]).strip() if (type_idx != -1 and type_idx < len(row_vals)) else ""
                    if is_invalid_part(raw_t): continue
                    part_val = str(row_vals[part_idx]).strip().upper() if (part_idx != -1 and part_idx < len(row_vals)) else ""
                    p_codes = []
                    if '100' in part_val or 'OR' in part_val: p_codes.append('OR')
                    if '120' in part_val or 'IR' in part_val or '010' in part_val: p_codes.append('IR')
                    if not p_codes: p_codes = ['IR', 'OR']
                    for pc in p_codes:
                        clean_keys = get_lookup_variants(raw_t, pc)
                        comb_val = str(row_vals[comb_idx]).strip() if (comb_idx != -1 and comb_idx < len(row_vals)) else ""
                        if comb_val and not is_invalid_part(comb_val): clean_keys.extend(get_lookup_variants(comb_val, pc))
                        if not clean_keys: continue
                            
                        rate_rings = 0.0
                        rpb = get_box_for_part(raw_t, pc, box_matrix)
                        if rpb_idx != -1 and rpb_idx < len(row_vals) and safe_float(row_vals[rpb_idx]) > 0: rpb = safe_float(row_vals[rpb_idx])
                        if ring_hr_idx != -1 and ring_hr_idx < len(row_vals) and safe_float(row_vals[ring_hr_idx]) > 0: rate_rings = safe_float(row_vals[ring_hr_idx])
                        elif box_hr_idx != -1 and box_hr_idx < len(row_vals) and safe_float(row_vals[box_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[box_hr_idx]) * rpb
                        elif std_hr_idx != -1 and std_hr_idx < len(row_vals) and safe_float(row_vals[std_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[std_hr_idx]) * rpb
                            
                        if rate_rings > 0:
                            for ck in set(clean_keys):
                                if current_m_type == "FACE": face_rows.append((current_m_num, ck, pc, rate_rings))
                                elif current_m_type == "OD": od_rows.append((current_m_num, ck, pc, rate_rings))
                                    
    return face_rows, od_rows, machine_master_rows

def parse_box_ring_sheets(s_name, df_b):
    s_name_up = str(s_name).upper().strip()
    df_box = df_b.fillna('')
    ring_per_box_rows, box_day_dgbb_rows, box_day_trb_rows, setup_chart_rows = [], [], [], []
    
    if 'SETUP' in s_name_up and 'CHART' in s_name_up:
        type_col, part_col, temp_col = -1, -1, -1
        for r_idx in range(min(5, len(df_box))):
            row_strs = [str(x).strip().upper() for x in df_box.iloc[r_idx].values]
            if any('TYPE' in x for x in row_strs) or any('PART' in x for x in row_strs):
                type_col = next((j for j, x in enumerate(row_strs) if 'TYPE' in x), -1)
                part_col = next((j for j, x in enumerate(row_strs) if 'PART' in x), -1)
                temp_col = next((j for j, x in enumerate(row_strs) if 'TEMP' in x or 'AVERAGE' in x), -1)
                break
        if type_col != -1 and part_col != -1 and temp_col != -1:
            for idx in range(r_idx + 1, len(df_box)):
                row_vals = list(df_box.iloc[idx].values)
                if type_col < len(row_vals) and part_col < len(row_vals) and temp_col < len(row_vals):
                    t_val = str(row_vals[type_col]).strip()
                    p_val = str(row_vals[part_col]).strip().upper()
                    temp_val = safe_float(row_vals[temp_col])
                    if not t_val or is_invalid_part(t_val) or not temp_val: continue
                    pc = 'IR' if 'IR' in p_val else ('OR' if 'OR' in p_val else None)
                    if pc:
                        variants = get_lookup_variants(t_val, pc)
                        for var in variants:
                            setup_chart_rows.append((var, pc, temp_val))

    elif 'RING' in s_name_up and 'BOX' in s_name_up:
        for idx in range(1, len(df_box)):
            row_vals = list(df_box.iloc[idx])
            for i in range(0, len(row_vals) - 2, 3):
                fam_raw = str(row_vals[i]).strip() if i < len(row_vals) else ""
                if not fam_raw or is_invalid_part(fam_raw): continue
                fams_to_process = fam_raw.split("/") if "/" in fam_raw else [fam_raw]
                for f_raw in fams_to_process:
                    for p_c in ['IR', 'OR']:
                        clean_keys = get_lookup_variants(f_raw, p_c)
                        for ck in clean_keys:
                            or_qty = safe_float(row_vals[i+1]) if (i+1 < len(row_vals)) else 0.0
                            ir_qty = safe_float(row_vals[i+2]) if (i+2 < len(row_vals)) else 0.0
                            if or_qty > 0 and p_c == 'OR': ring_per_box_rows.append((ck, 'OR', or_qty, s_name))
                            if ir_qty > 0 and p_c == 'IR': ring_per_box_rows.append((ck, 'IR', ir_qty, s_name))
                                    
    elif 'BOX' in s_name_up and 'DAY' in s_name_up:
        target_rows = box_day_dgbb_rows if "DGBB" in s_name_up else box_day_trb_rows
        if not ("DGBB" in s_name_up or "TRB" in s_name_up): target_rows = box_day_dgbb_rows
            
        for r_idx in range(len(df_box)):
            for c_idx in range(len(df_box.columns)):
                cell_val = str(df_box.iloc[r_idx, c_idx]).strip()
                match = re.search(r'([A-Z0-9/]+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)\s*(\d+)\s*K?', cell_val, re.IGNORECASE)
                if match:
                    part_type = match.group(1).strip()
                    ir_boxes, or_boxes = int(match.group(2)), int(match.group(3))
                    ref_qty = int(match.group(4)) * 1000 if 'K' in cell_val.upper() else int(match.group(4))
                    ir_rpb = ref_qty / ir_boxes if ir_boxes > 0 else 0
                    or_rpb = ref_qty / or_boxes if or_boxes > 0 else 0
                    for p_c in ['IR', 'OR']:
                        clean_keys = get_lookup_variants(part_type, p_c)
                        for ck in clean_keys:
                            if p_c == 'IR' and ir_rpb > 0: target_rows.append((ck, 'IR', ir_rpb, s_name))
                            if p_c == 'OR' and or_rpb > 0: target_rows.append((ck, 'OR', or_rpb, s_name))

        type_col, ir_col, or_col, single_rpb_col = -1, -1, -1, -1
        for r_idx in range(min(20, len(df_box))):
            norm_strs = [re.sub(r'[\s./_\-]', '', str(x).strip().upper()) for x in df_box.iloc[r_idx]]
            t_c = next((j for j, h in enumerate(norm_strs) if 'TYPE' in h or 'BEARING' in h), -1)
            i_c = next((j for j, h in enumerate(norm_strs) if 'IR' in h and 'BOX' in h), -1)
            o_c = next((j for j, h in enumerate(norm_strs) if 'OR' in h and 'BOX' in h), -1)
            s_c = next((j for j, h in enumerate(norm_strs) if 'RING' in h and 'BOX' in h and 'IR' not in h and 'OR' not in h), -1)
            if t_c != -1 and (i_c != -1 or o_c != -1 or s_c != -1):
                type_col, ir_col, or_col, single_rpb_col = t_c, i_c, o_c, s_c; break
        if type_col != -1:
            for idx in range(r_idx + 1, len(df_box)):
                row_vals = list(df_box.iloc[idx])
                raw_t = str(row_vals[type_col]).strip() if type_col < len(row_vals) else ""
                if not raw_t or is_invalid_part(raw_t): continue
                for p_c in ['IR', 'OR']:
                    clean_keys = get_lookup_variants(raw_t, p_c)
                    for ck in clean_keys:
                        if p_c == 'IR':
                            fq = safe_float(row_vals[ir_col]) if (ir_col != -1 and ir_col < len(row_vals)) else (safe_float(row_vals[single_rpb_col]) if (single_rpb_col != -1 and single_rpb_col < len(row_vals)) else 0.0)
                            if fq > 0: target_rows.append((ck, 'IR', fq, s_name))
                        if p_c == 'OR':
                            fq = safe_float(row_vals[or_col]) if (or_col != -1 and or_col < len(row_vals)) else (safe_float(row_vals[single_rpb_col]) if (single_rpb_col != -1 and single_rpb_col < len(row_vals)) else 0.0)
                            if fq > 0: target_rows.append((ck, 'OR', fq, s_name))
                            
    return ring_per_box_rows, box_day_dgbb_rows, box_day_trb_rows, setup_chart_rows

def sync_master_data():
    conn = None
    try:
        init_neon_tables()
        conn = get_neon_conn()
        
        # 1. Fetch Box Ring Matrix data first to build temp rate conversions
        temp_box_matrix = {}
        all_ring_box, all_box_dgbb, all_box_trb, all_setup_chart = [], [], [], []
        for s_name, df_b in get_excel_sheets_cached(BOX_RING_DATA_URL, box_ring_sheet_filter):
            r_rows, d_rows, t_rows, s_rows = parse_box_ring_sheets(s_name, df_b)
            all_ring_box.extend(r_rows)
            all_box_dgbb.extend(d_rows)
            all_box_trb.extend(t_rows)
            all_setup_chart.extend(s_rows)
            
        for ck, pc, qty, src in all_ring_box:
            if ck not in temp_box_matrix: temp_box_matrix[ck] = {}
            temp_box_matrix[ck][pc] = {'qty': qty, 'source': src}
        for ck, pc, qty, src in (all_box_dgbb + all_box_trb):
            if ck not in temp_box_matrix: temp_box_matrix[ck] = {}
            temp_box_matrix[ck][pc] = {'qty': qty, 'source': src}
            
        # 2. Parse Production Master Sheets
        all_weights, all_furnace_flex, all_face_comp, all_od_comp, all_machine_master = [], [], [], [], []
        furnace_specs_local = DEFAULT_FURNACES.copy()
        
        for s_name, df_m in get_excel_sheets_cached(SHO_PRODUCTION_URL, prod_master_sheet_filter):
            s_name_up = str(s_name).upper().strip()
            if 'FURNACE' in s_name_up or 'AICHELIN' in s_name_up:
                if 'FLEX' not in s_name_up:
                    for r in range(len(df_m)):
                        row = df_m.iloc[r].values
                        f_name = str(row[0]).strip().upper() if len(row) > 0 else ""
                        cap = safe_float(row[1]) if len(row) > 1 else 0.0
                        if f_name and cap > 0 and ('FURNACE' in f_name or 'AICHELIN' in f_name or 'UNITHERM' in f_name):
                            furnace_specs_local[f_name] = cap
                            all_machine_master.append((f_name, "HT"))

        for s_name, df_m in get_excel_sheets_cached(SHO_PRODUCTION_URL, prod_master_sheet_filter):
            s_name_up = str(s_name).upper().strip()
            if s_name_up == 'WEIGHTS': all_weights.extend(parse_weights_sheet(df_m))
            elif 'FURNACE' in s_name_up and 'FLEX' in s_name_up: all_furnace_flex.extend(parse_furnace_flex_sheet(df_m, furnace_specs_local))
            elif s_name_up not in ['WEIGHTS', 'FURNACE TYPE FLEXIBILITY', 'RING PER BOX.', 'CHANNEL PROCESS FLEXIBILITY']:
                face_rows, od_rows, m_rows = parse_machine_comp_sheets(s_name, df_m, temp_box_matrix)
                all_face_comp.extend(face_rows)
                all_od_comp.extend(od_rows)
                all_machine_master.extend(m_rows)

        static_channels = [
            "CH1", "CH2", "CH3", "CH4", "CH5", "SABB", "CH7", "CH8", "CH11", "CH12", "CH13",
            "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11",
            "HUB 1.1", "HUB 1.2", "HUB 1.3", "HUB 1.4", "HUB 3", "THUB 1.1", "THUB 1.2", "THUB 1.3"
        ]
        all_channel_master = [(ch,) for ch in static_channels]

        def dedup(rows, keys_count):
            seen = {}
            for row in rows:
                key = tuple(row[:keys_count])
                seen[key] = row[keys_count:]
            return [key + val for key, val in seen.items()]

        all_ring_box = dedup(all_ring_box, 2)
        all_box_dgbb = dedup(all_box_dgbb, 2)
        all_box_trb = dedup(all_box_trb, 2)
        all_setup_chart = dedup(all_setup_chart, 2)
        all_weights = dedup(all_weights, 2)
        all_furnace_flex = dedup(all_furnace_flex, 2)
        all_face_comp = dedup(all_face_comp, 3)
        all_od_comp = dedup(all_od_comp, 3)
        all_machine_master = dedup(all_machine_master, 1)
        
        # Bulk database inserts using Neon connection
        upsert_rows(conn, "weights", ["part_type", "part_code", "weight"], ["part_type", "part_code"], all_weights)
        upsert_rows(conn, "furnace_type_flexibility", ["comp_level", "part_code", "furnaces"], ["comp_level", "part_code"], all_furnace_flex)
        upsert_rows(conn, "face_machine_compatibility", ["machine_name", "part_type", "part_code", "rate"], ["machine_name", "part_type", "part_code"], all_face_comp)
        upsert_rows(conn, "od_machine_compatibility", ["machine_name", "part_type", "part_code", "rate"], ["machine_name", "part_type", "part_code"], all_od_comp)
        upsert_rows(conn, "ring_per_box", ["part_type", "part_code", "qty", "source"], ["part_type", "part_code"], all_ring_box)
        upsert_rows(conn, "box_per_day_dgbb", ["part_type", "part_code", "qty", "source"], ["part_type", "part_code"], all_box_dgbb)
        upsert_rows(conn, "box_per_day_trb", ["part_type", "part_code", "qty", "source"], ["part_type", "part_code"], all_box_trb)
        upsert_rows(conn, "setup_chart", ["part_type", "part_code", "temp"], ["part_type", "part_code"], all_setup_chart)
        upsert_rows(conn, "machine_master", ["machine_name", "machine_type"], ["machine_name"], all_machine_master)
        upsert_rows(conn, "channel_master", ["channel_name"], ["channel_name"], all_channel_master)
        
        # Populate GLOBAL_PART_TO_CHANNEL from Zeroset Demands
        for sheet_name, df_zero in get_excel_sheets_cached(ZEROSET_URL, zeroset_sheet_filter):
            sheet_str_upper = str(sheet_name).strip().upper()
            if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                ch_name = f"CH{sheet_str_upper.zfill(2)}"
            elif sheet_str_upper == "SABB": ch_name = "SABB"
            elif sheet_str_upper.startswith("T ") or any(sheet_str_upper.startswith(f"T{k}") for k in range(1, 12)):
                ch_name = sheet_str_upper
            elif "HUB" in sheet_str_upper: ch_name = sheet_str_upper
            else: ch_name = sheet_str_upper

            r_idx, type_col_idx, mv_col_idx = None, None, None
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
                if r_idx is not None and type_col_idx is not None: break

            col_to_use = type_col_idx if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "SABB"] else mv_col_idx
            if col_to_use is None: col_to_use = mv_col_idx if mv_col_idx is not None else type_col_idx

            if r_idx is not None and type_col_idx is not None:
                last_mf = ""
                for idx in range(r_idx + 1, len(df_zero)):
                    row_vals_zero = list(df_zero.iloc[idx].values)
                    mf_val = str(row_vals_zero[type_col_idx]).strip() if (type_col_idx is not None and type_col_idx < len(row_vals_zero)) else ""
                    if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                    raw_t = str(row_vals_zero[col_to_use]).strip() if (col_to_use is not None and col_to_use < len(row_vals_zero)) else ""
                    if not raw_t or raw_t in ["NAN", "NONE"]: raw_t = last_mf
                    if is_invalid_part(raw_t): continue
                    
                    display_name = get_display_name(raw_t)
                    GLOBAL_PART_TO_CHANNEL[display_name] = ch_name

        conn.commit()
        print("Master data synchronized to Neon successfully!")
        load_master_data_from_neon()
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error syncing master data to Neon: {e}")
    finally:
        if conn: conn.close()

def start_sync_thread():
    def run_sync():
        while True:
            time.sleep(3600)  # Sleep exactly 1 hour
            try:
                print("Starting hourly synchronization task...")
                sync_master_data()
            except Exception as e:
                print(f"Sync execution thread error: {e}")
    t = threading.Thread(target=run_sync, daemon=True)
    t.start()

@router.on_event("startup")
def startup_event():
    try:
        init_neon_tables()
        conn = get_neon_conn()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM machine_master")
            count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            print("Neon schema is empty. Starting background sync thread immediately...")
            threading.Thread(target=sync_master_data, daemon=True).start()
        else:
            load_master_data_from_neon()
        start_sync_thread()
    except Exception as e:
        print(f"Startup warning initialization: {e}")

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

class BreakdownItem(BaseModel):
    resource: str
    status: str
    start_time: str
    end_time: str

class SaveBreakdownsRequest(BaseModel):
    date: str
    entries: List[BreakdownItem]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

@router.get("/api/monthly_tracking")
def get_monthly_tracking_api():
    return load_monthly_tracking()

@router.get("/api/machines")
def get_machines():
    furnaces, face_mcs, od_mcs, channels = get_all_resources_dynamic()
    res = {}
    for f in furnaces: res[f] = {"type": "HT", "ready_time": 0.0, "last_fam": None, "last_pc": None}
    for m in face_mcs: res[m] = {"type": "FACE", "ready_time": 0.0, "last_fam": None, "last_pc": None}
    for m in od_mcs: res[m] = {"type": "OD", "ready_time": 0.0, "last_fam": None, "last_pc": None}
    for c in channels: res[c] = {"type": "Channel", "ready_time": 0.0, "last_fam": None, "last_pc": None}
    return res

@router.get("/api/get_plan")
def get_plan(date: str):
    try:
        plans = load_saved_plan()
        return plans.get(date, {})
    except Exception as e:
        return {"status": "error", "detail": str(e)}

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
# BREAKDOWN ENDPOINTS & RESOURCE MATCHING
# ==========================================
def get_all_resources_dynamic():
    """Returns dynamic furnaces, face grinding, OD grinding and channels exact names from cached master data."""
    furnaces = sorted([name for name, mtype in MASTER_DATA_CACHE.get("machine_master", {}).items() if mtype == "HT"])
    if not furnaces: furnaces = sorted(list(DEFAULT_FURNACES.keys()))
        
    face_mcs = sorted([name for name, mtype in MASTER_DATA_CACHE.get("machine_master", {}).items() if mtype == "FACE"])
    if not face_mcs: face_mcs = ["DDS 1", "DDS 2", "BG 1"]
        
    od_mcs = sorted([name for name, mtype in MASTER_DATA_CACHE.get("machine_master", {}).items() if mtype == "OD"])
    if not od_mcs: od_mcs = ["CL 1", "CL 2", "CELL 1"]
        
    channels = MASTER_DATA_CACHE.get("channels")
    if not channels:
        channels = [
            "CH1", "CH2", "CH3", "CH4", "CH5", "SABB", "CH7", "CH8", "CH11", "CH12", "CH13",
            "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11",
            "HUB 1.1", "HUB 1.2", "HUB 1.3", "HUB 1.4", "HUB 3", "THUB 1.1", "THUB 1.2", "THUB 1.3"
        ]
    return furnaces, face_mcs, od_mcs, channels

@router.get("/api/breakdowns")
def get_breakdowns(date: str):
    saved = {}
    conn = None
    try:
        conn = get_neon_conn()
        with conn.cursor() as cursor:
            cursor.execute("SELECT resource, status, start_time, end_time FROM breakdowns WHERE date=%s", (date,))
            for row in cursor.fetchall():
                saved[row[0]] = {"status": row[1], "start_time": row[2], "end_time": row[3]}
    except Exception as e:
        print(f"Error reading breakdowns from Neon: {e}")
    finally:
        if conn: conn.close()

    furnaces, face_mcs, od_mcs, channels = get_all_resources_dynamic()

    res_list = []
    for f in furnaces:
        res_list.append({"resource": f, "type": "Furnace", **saved.get(f, {"status": "Available", "start_time": "", "end_time": ""})})
    for m in face_mcs:
        res_list.append({"resource": m, "type": "Face Grinding", **saved.get(m, {"status": "Available", "start_time": "", "end_time": ""})})
    for m in od_mcs:
        res_list.append({"resource": m, "type": "OD Grinding", **saved.get(m, {"status": "Available", "start_time": "", "end_time": ""})})
    for c in channels:
        res_list.append({"resource": c, "type": "Channel", **saved.get(c, {"status": "Available", "start_time": "", "end_time": ""})})

    return {"status": "success", "data": res_list}

@router.post("/api/save_breakdowns")
def save_breakdowns(payload: SaveBreakdownsRequest):
    conn = None
    try:
        # Validate breakdown resource names
        furnaces, face_mcs, od_mcs, channels = get_all_resources_dynamic()
        valid_resources = set(furnaces + face_mcs + od_mcs + channels)
        for ent in payload.entries:
            if ent.resource not in valid_resources:
                return {"status": "error", "detail": f"Invalid resource name: '{ent.resource}' in breakdown entry."}

        conn = get_neon_conn()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM breakdowns WHERE date=%s", (payload.date,))
            for ent in payload.entries:
                cursor.execute("INSERT INTO breakdowns (date, resource, status, start_time, end_time) VALUES (%s, %s, %s, %s, %s)",
                              (payload.date, ent.resource, ent.status, ent.start_time, ent.end_time))
            conn.commit()
        return {"status": "success"}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        if conn: conn.close()

@router.post("/api/clear_cache")
def clear_cache():
    GLOBAL_EXCEL_CACHE.clear()
    RATE_CACHE.clear()
    WEIGHT_CACHE.clear()
    FURNACE_CACHE.clear()
    VARIANTS_CACHE.clear()
    GLOBAL_PART_TO_CHANNEL.clear()
    gc.collect()
    try:
        load_master_data_from_neon()
        return {"status": "success", "message": "All parsed excel and Neon cached databases reloaded successfully!"}
    except Exception as e:
        return {"status": "error", "message": f"Caches cleared, reload Neon configuration failing: {e}"}

# ==========================================
# UTIL FUNCTIONS
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
    cache_key = (raw_text, p_code)
    if cache_key in VARIANTS_CACHE:
        return VARIANTS_CACHE[cache_key]
        
    if is_invalid_part(raw_text): return []
    t = str(raw_text).upper().strip()
    t = re.sub(r'[\u200b\u200c\u200d\uFEFF]', '', t)
    
    if "INDUSTRILA" in t: t = t.replace("INDUSTRILA", "INDUSTRIAL")
    if t.startswith("MF"): t = t[2:].strip()
    
    parts = [p.strip() for p in t.split('/') if p.strip()]
    numeric_parts = [p for p in parts if any(c.isdigit() for c in p) and len(re.sub(r'\D', '', p)) >= 3]
    
    if len(numeric_parts) >= 2 and p_code:
        if p_code == 'IR' and len(parts) > 0: t = parts[0]
        elif p_code == 'OR' and len(numeric_parts) > 1: t = numeric_parts[1]
    elif '/' in t and len(parts) > 1:
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
    
    VARIANTS_CACHE[cache_key] = variants
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
    weights_dict = MASTER_DATA_CACHE.get("weights") or {}
    for var in variants:
        k = f"{var}_{p_code}"
        if k in weights_dict: 
            WEIGHT_CACHE[key] = weights_dict[k]
            return WEIGHT_CACHE[key]
            
    WEIGHT_CACHE[key] = None
    return None

def get_furnaces_for_part(display_name, p_code, furnace_map, furnace_specs):
    key = (display_name, p_code)
    if key in FURNACE_CACHE: return FURNACE_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    flex_dict = MASTER_DATA_CACHE.get("furnace_type_flexibility") or {}
    for var in variants:
        k = f"{var}_{p_code}"
        if k in flex_dict: 
            FURNACE_CACHE[key] = flex_dict[k]
            return FURNACE_CACHE[key]
            
    default_f = list(furnace_specs.keys())
    FURNACE_CACHE[key] = default_f
    return default_f

def get_box_for_part_detailed(display_name, p_code, box_matrix):
    variants = get_lookup_variants(display_name, p_code)
    box_matrix_cached = MASTER_DATA_CACHE.get("box_matrix") or {}
    for var in variants:
        if var in box_matrix_cached and p_code in box_matrix_cached[var]: 
            qty = box_matrix_cached[var][p_code]['qty']
            source = box_matrix_cached[var][p_code]['source']
            return qty, source, var
            
    norm_disp = re.sub(r'[\s./_\-]', '', str(display_name).upper())
    for b_key, b_val in box_matrix_cached.items():
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

def get_tempering_temp(display_name, p_code, setup_chart_matrix):
    variants = get_lookup_variants(display_name, p_code)
    setup_cached = MASTER_DATA_CACHE.get("setup_chart") or {}
    for var in variants:
        if (var, p_code) in setup_cached:
            return setup_cached[(var, p_code)]
    return None

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
    missing_rate_flag, missing_weight_flag = False, False
    
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
# MAIN SCHEDULER ROUTE
# ==========================================
# ==========================================
# MAIN SCHEDULER ROUTE
# ==========================================
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs, unscheduled = [], []
    RATE_CACHE.clear()
    WEIGHT_CACHE.clear()
    FURNACE_CACHE.clear()
    VARIANTS_CACHE.clear()
    gc.collect()
    
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day_1 = req_date  
        day_2 = req_date + timedelta(days=1)
        month_str = req_date.strftime("%Y-%m")
        
        monthly_data = load_monthly_tracking()
        if month_str not in monthly_data: 
            monthly_data[month_str] = {}

        channel_demands_day1, channel_demands_day2 = {}, {}
        
        # 1. LOAD ONLY DAILY TRANSACTIONAL ZEROSET FROM EXCEL (Cached dynamically)
        for sheet_name, df_zero in get_excel_sheets_cached(ZEROSET_URL, zeroset_sheet_filter):
            sheet_str_upper = str(sheet_name).strip().upper()
            if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                ch_name = f"CH{sheet_str_upper.zfill(2)}"
            elif sheet_str_upper == "SABB": 
                ch_name = "SABB"
            elif sheet_str_upper.startswith("T ") or any(sheet_str_upper.startswith(f"T{k}") for k in range(1, 12)):
                ch_name = sheet_str_upper
            elif "HUB" in sheet_str_upper: 
                ch_name = sheet_str_upper
            else: 
                ch_name = sheet_str_upper

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
                            type_col_idx = j
                            break
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["MF", "PART NO", "BRG NO"]: 
                                type_col_idx = j
                                break
                if mv_col_idx is None:
                    for j, val in enumerate(row_strs):
                        if val in ["MV", "FV", "VAR", "VARIANT"]: 
                            mv_col_idx = j
                            break
                            
                if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                    r_idx = i
                    for j, val in enumerate(df_zero.iloc[i].values):
                        if is_target_date(val, day_1): 
                            c1_col = j
                        if is_target_date(val, day_2): 
                            c2_col = j
                        s_val = str(val).strip()
                        if s_val.isdigit() and 1 <= int(s_val) <= 31: 
                            monthly_cols.append(j)
                if r_idx is not None and type_col_idx is not None and c1_col is not None: 
                    break

            col_to_use = type_col_idx if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "SABB"] else mv_col_idx
            if col_to_use is None: 
                col_to_use = mv_col_idx if mv_col_idx is not None else type_col_idx

            if r_idx is not None and type_col_idx is not None:
                last_mf = ""
                for idx in range(r_idx + 1, len(df_zero)):
                    row_vals_zero = list(df_zero.iloc[idx].values)
                    
                    mf_val = str(row_vals_zero[type_col_idx]).strip() if (type_col_idx is not None and type_col_idx < len(row_vals_zero)) else ""
                    if mf_val and mf_val not in ["NAN", "NONE"]: 
                        last_mf = mf_val
                    raw_t = str(row_vals_zero[col_to_use]).strip() if (col_to_use is not None and col_to_use < len(row_vals_zero)) else ""
                    if not raw_t or raw_t in ["NAN", "NONE"]: 
                        raw_t = last_mf
                    if is_invalid_part(raw_t): 
                        continue
                    
                    display_name = get_display_name(raw_t)
                    GLOBAL_PART_TO_CHANNEL[display_name] = ch_name
                    if display_name not in monthly_data[month_str]:
                        monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": ch_name}
                    
                    row_monthly_sum = sum([safe_float(row_vals_zero[col]) for col in monthly_cols if col < len(row_vals_zero)])
                    if row_monthly_sum > 0: 
                        monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                    
                    val1 = safe_float(row_vals_zero[c1_col]) if (c1_col is not None and c1_col < len(row_vals_zero)) else 0.0
                    val2 = safe_float(row_vals_zero[c2_col]) if (c2_col is not None and c2_col < len(row_vals_zero)) else 0.0
                    
                    r1 = val1 * 1000 if val1 > 0 else 0.0
                    r2 = val2 * 1000 if val2 > 0 else 0.0
                    
                    if r1 > 0:
                        if display_name not in channel_demands_day1: 
                            channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': ch_name}
                        channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1 * ir_multiplier)
                        channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)
                        
                    if r2 > 0:
                        if display_name not in channel_demands_day2: 
                            channel_demands_day2[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': ch_name}
                        channel_demands_day2[display_name]['IR'] = max(channel_demands_day2[display_name]['IR'], r2 * ir_multiplier)
                        channel_demands_day2[display_name]['OR'] = max(channel_demands_day2[display_name]['OR'], r2)

        # 2. LOAD STATIC LOOKUPS FROM IN-MEMORY CACHE (NO EXCEL RUNTIME PARSING)
        weight_matrix = MASTER_DATA_CACHE.get("weights") or {}
        furnace_map = MASTER_DATA_CACHE.get("furnace_type_flexibility") or {}
        box_matrix = MASTER_DATA_CACHE.get("box_matrix") or {}
        setup_chart_matrix = MASTER_DATA_CACHE.get("setup_chart") or {}
        furnace_specs_local = MASTER_DATA_CACHE.get("furnaces_specs") or DEFAULT_FURNACES.copy()

        current_state = get_previous_day_state(payload.date)
        work_items, resources = [], []
        
        for f_name, cap in furnace_specs_local.items(): 
            resources.append(Resource(f_name, 'HT', cap))
        
        face_mcs = MASTER_DATA_CACHE.get("face_machine_compatibility") or {}
        for m_num, rates in face_mcs.items(): 
            resources.append(Resource(m_num, 'FACE', rates))
            
        od_mcs = MASTER_DATA_CACHE.get("od_machine_compatibility") or {}
        for m_num, rates in od_mcs.items(): 
            resources.append(Resource(m_num, 'OD', rates))

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

        ht_balances = {}
        for w_key, w_data in current_state.get("wip", {}).items():
            if "|" not in w_key: 
                continue
            disp, pc = w_key.split('|')
            ch_norm = w_data.get("channel", "UNKNOWN")
            
            if "ht_balance" in w_data: 
                ht_balances[(disp, pc)] = float(w_data["ht_balance"])
                
            routing = get_routing_for_part(ch_norm, pc)

        # --- PLUG IN REST OF SCHEDULER LOGIC HERE ---

        return {
            "status": "success", 
            "message": "Schedule successfully generated.",
            "unscheduled": unscheduled
        }

    except Exception as e:
        debug_logs.append(f"Fatal exception: {str(e)}")
        return {
            "status": "error", 
            "message": f"Scheduling execution failed: {str(e)}", 
            "logs": debug_logs
        }
