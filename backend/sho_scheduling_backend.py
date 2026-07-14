import os
import re
import math
import pandas as pd
import requests
import io
import json
import time
import gc
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

# Environment Configurations
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sho_db")

# In-Memory Cache for Neon Master Data (Refreshed hourly)
MASTER_CACHE = {
    "last_updated": 0,
    "weights": {},
    "furnace_flexibility": {},
    "face_compatibility": {},
    "od_compatibility": {},
    "ring_per_box": {},
    "box_per_day_dgbb": {},
    "box_per_day_trb": {},
    "setup_chart": {},
    "machine_master": [],
    "channel_master": []
}

# Dynamic Scheduler Caches (Lifecycle of a single request)
RATE_CACHE = {}
WEIGHT_CACHE = {}
FURNACE_CACHE = {}
VARIANTS_CACHE = {}

DEFAULT_FURNACES = {
    "AICHELIN.(896)": 350.0, 
    "CASTLINK FURNACE( 1018 )": 250.0,
    "ROLLER FURNACE ( 148 )": 250.0, 
    "SIMPLICITY FURNACE(1238)": 180.0,
    "BIRLEC FURNACE   ( 1158 )": 170.0, 
    "SHOEI FURNACE    ( 1062 )": 350.0,
    "AICHELIN UNITHERM ( 2033 )": 250.0
}

# Dynamic ZeroSet Plan In-Memory Cache (Refreshed every 1 hour)
ZEROSET_CACHE = {
    "last_updated": 0,
    "sheets": {}
}

# ==========================================
# NEON POSTGRESQL INITIALIZATION & SYNC
# ==========================================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_neon_tables():
    """Initializes the Neon Master Data and Dynamic Operational Tables."""
    with get_db_connection() as conn:
        with conn.cursor() as c:
            # Master Data Tables
            c.execute("""
                CREATE TABLE IF NOT EXISTS machine_master (
                    resource_name TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    capacity_info TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS channel_master (
                    channel_name TEXT PRIMARY KEY
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS weights (
                    part_key TEXT PRIMARY KEY,
                    weight NUMERIC NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS setup_chart (
                    part_variant TEXT,
                    part_code TEXT,
                    temperature NUMERIC,
                    PRIMARY KEY (part_variant, part_code)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS ring_per_box (
                    part_variant TEXT,
                    part_code TEXT,
                    qty NUMERIC,
                    source TEXT,
                    PRIMARY KEY (part_variant, part_code)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS furnace_flexibility (
                    part_variant TEXT,
                    part_code TEXT,
                    furnaces TEXT,
                    PRIMARY KEY (part_variant, part_code)
                )
            """)
            # Dynamic Storage Tables
            c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS daily_state (date TEXT PRIMARY KEY, state_json TEXT)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS breakdowns (
                    date TEXT, 
                    resource TEXT, 
                    status TEXT, 
                    start_time TEXT, 
                    end_time TEXT, 
                    PRIMARY KEY(date, resource)
                )
            """)
            conn.commit()

init_neon_tables()

def zeroset_sheet_filter(sheet_name: str) -> bool:
    s = str(sheet_name).strip().upper()
    return s in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "SABB"] or s.startswith("T") or "HUB" in s

def parse_excel_to_df_dict(url: str, sheet_filter_fn=None):
    if not url or url.strip() == "":
        return {}
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
                    sheets_data[sheet] = df.fillna('')
            gc.collect()
    except Exception as e:
        print(f"Error parsing sync excel from {url}: {e}")
    return sheets_data

def sync_excel_to_neon():
    """Background task executing hourly UPSERT operations from Excel targets into Neon."""
    print("Starting hourly Master Data Synchronization with Neon PostgreSQL...")
    
    prod_sheets = parse_excel_to_df_dict(SHO_PRODUCTION_URL)
    box_sheets = parse_excel_to_df_dict(BOX_RING_DATA_URL)
    
    with get_db_connection() as conn:
        with conn.cursor() as c:
            # 1. Sync Machine Master & Capacity Information
            machines_found = []
            for f_name, cap in DEFAULT_FURNACES.items():
                machines_found.append((f_name, 'HT', json.dumps(cap)))
            
            for sheet_name, df_m in prod_sheets.items():
                sheet_up = sheet_name.upper().strip()
                if sheet_up not in ['WEIGHTS', 'FURNACE TYPE FLEXIBILITY', 'RING PER BOX.', 'CHANNEL PROCESS FLEXIBILITY'] and 'FLEX' not in sheet_up:
                    str_matrix = df_m.astype(str).values
                    current_m_num = None
                    current_m_type = "UNKNOWN"
                    for r in range(str_matrix.shape[0]):
                        row_text = " ".join(str_matrix[r]).upper()
                        if 'MACHINE' in row_text or 'M/C' in row_text:
                            cells = [c.strip() for c in str_matrix[r] if c.strip()]
                            m_cand = cells[1] if len(cells) > 1 else None
                            if m_cand and m_cand != "MACHINE" and m_cand != "M/C":
                                current_m_num = m_cand
                                if "FACE" in row_text or "DDS" in current_m_num.upper() or "BG" in current_m_num.upper(): 
                                    current_m_type = "FACE"
                                else: 
                                    current_m_type = "OD"
                        
                        if current_m_num and current_m_type in ['FACE', 'OD']:
                            h_row = [c.strip().upper() for c in str_matrix[r]]
                            if any('TYPE' in h or 'PART' in h for h in h_row) and any('HR' in h for h in h_row):
                                norm_headers = [re.sub(r'[\s./_\-]', '', h) for h in h_row]
                                std_hr_idx = next((j for j, h in enumerate(norm_headers) if 'STDHR' in h), -1)
                                box_hr_idx = next((j for j, h in enumerate(norm_headers) if 'BOX' in h and 'HR' in h), -1)
                                ring_hr_idx = next((j for j, h in enumerate(norm_headers) if ('RING' in h and 'HR' in h) or ('QTY' in h and 'HR' in h) or 'RATE' in h), -1)
                                type_idx = next((j for j, h in enumerate(norm_headers) if 'TYPE' in h or 'BEARING' in h or 'PART' in h), -1)
                                
                                rates_dict = {}
                                for offset2 in range(1, 200):
                                    if r + offset2 >= str_matrix.shape[0]: break
                                    row_vals = str_matrix[r + offset2]
                                    if "MACHINE" in " ".join(row_vals).upper() or "M/C" in " ".join(row_vals).upper(): break
                                    raw_t = str(row_vals[type_idx]).strip() if (type_idx != -1 and type_idx < len(row_vals)) else ""
                                    if is_invalid_part(raw_t): continue
                                    
                                    rate_rings = 0.0
                                    if ring_hr_idx != -1 and ring_hr_idx < len(row_vals): rate_rings = safe_float(row_vals[ring_hr_idx])
                                    elif box_hr_idx != -1 and box_hr_idx < len(row_vals): rate_rings = safe_float(row_vals[box_hr_idx]) * 50.0 
                                    elif std_hr_idx != -1 and std_hr_idx < len(row_vals): rate_rings = safe_float(row_vals[std_hr_idx]) * 50.0
                                    
                                    if rate_rings > 0:
                                        for pc in ['IR', 'OR']:
                                            for var in get_lookup_variants(raw_t, pc):
                                                rates_dict[f"{var}_{pc}"] = rate_rings
                                                
                                machines_found.append((current_m_num, current_m_type, json.dumps(rates_dict)))

            if machines_found:
                execute_values(c, """
                    INSERT INTO machine_master (resource_name, resource_type, capacity_info) 
                    VALUES %s ON CONFLICT (resource_name) DO UPDATE SET 
                    resource_type = EXCLUDED.resource_type, capacity_info = EXCLUDED.capacity_info
                """, machines_found)

            # 2. Sync Channel Master
            channels_list = [
                ("CH01",), ("CH02",), ("CH03",), ("CH04",), ("CH05",), ("SABB",), ("CH07",), ("CH08",), ("CH11",), ("CH12",), ("CH13",),
                ("T1",), ("T2",), ("T3",), ("T4",), ("T5",), ("T6",), ("T7",), ("T8",), ("T9",), ("T10",), ("T11",),
                ("HUB 1.1",), ("HUB 1.2",), ("HUB 1.3",), ("HUB 1.4",), ("HUB 3",), ("THUB 1.1",), ("THUB 1.2",), ("THUB 1.3",)
            ]
            execute_values(c, "INSERT INTO channel_master (channel_name) VALUES %s ON CONFLICT DO NOTHING", channels_list)

            # 3. Sync Weights Table
            weight_df = prod_sheets.get('WEIGHTS')
            if weight_df is not None:
                weight_rows = []
                for idx, row in weight_df.iterrows():
                    if idx < 3 or is_invalid_part(row.iloc[0]): continue
                    raw_fam = str(row.iloc[0]).strip()
                    ir_or_val = str(row.iloc[1]).strip() if len(row) > 1 else ""
                    part_code = 'OR' if '100' in ir_or_val else ('IR' if ('120' in ir_or_val or '010' in ir_or_val) else None)
                    wt_val = safe_float(row.iloc[2]) if len(row) > 2 else 0.0
                    if part_code and wt_val > 0:
                        for ck in get_lookup_variants(raw_fam, part_code):
                            weight_rows.append((f"{ck}_{part_code}", wt_val))
                if weight_rows:
                    execute_values(c, "INSERT INTO weights (part_key, weight) VALUES %s ON CONFLICT (part_key) DO UPDATE SET weight = EXCLUDED.weight", weight_rows)

            # 4. Sync Setup Charts Table
            for s_name, df_b in box_sheets.items():
                if 'SETUP' in s_name.upper() and 'CHART' in s_name.upper():
                    setup_rows = []
                    for idx, row in df_b.iterrows():
                        if idx < 2: continue
                        t_val = str(row.iloc[0]).strip()
                        p_val = str(row.iloc[1]).strip().upper()
                        temp_val = safe_float(row.iloc[2]) if len(row) > 2 else 0.0
                        if not t_val or is_invalid_part(t_val) or not temp_val: continue
                        pc = 'IR' if 'IR' in p_val else ('OR' if 'OR' in p_val else None)
                        if pc:
                            for var in get_lookup_variants(t_val, pc):
                                setup_rows.append((var, pc, temp_val))
                    if setup_rows:
                        execute_values(c, "INSERT INTO setup_chart (part_variant, part_code, temperature) VALUES %s ON CONFLICT (part_variant, part_code) DO UPDATE SET temperature = EXCLUDED.temperature", setup_rows)

            # 5. Sync Ring Per Box & Box Matrices
            box_rows = []
            for s_name, df_b in box_sheets.items():
                s_name_up = s_name.upper().strip()
                if 'RING' in s_name_up and 'BOX' in s_name_up:
                    for idx, row in df_b.iterrows():
                        if idx == 0: continue
                        for i in range(0, len(row) - 2, 3):
                            fam_raw = str(row.iloc[i]).strip()
                            if not fam_raw or is_invalid_part(fam_raw): continue
                            for f_raw in (fam_raw.split("/") if "/" in fam_raw else [fam_raw]):
                                for p_c in ['IR', 'OR']:
                                    or_qty = safe_float(row.iloc[i+1])
                                    ir_qty = safe_float(row.iloc[i+2])
                                    qty_to_save = or_qty if p_c == 'OR' else ir_qty
                                    if qty_to_save > 0:
                                        for ck in get_lookup_variants(f_raw, p_c):
                                            box_rows.append((ck, p_c, qty_to_save, s_name))
            if box_rows:
                execute_values(c, "INSERT INTO ring_per_box (part_variant, part_code, qty, source) VALUES %s ON CONFLICT (part_variant, part_code) DO UPDATE SET qty = EXCLUDED.qty, source = EXCLUDED.source", box_rows)
            
            conn.commit()
    print("Master Data Sync Completed Successfully.")
    refresh_memory_cache()

def refresh_memory_cache():
    """Pulls all tracking metadata from Neon directly into RAM to allow instantaneous lookup transactions."""
    global MASTER_CACHE
    print("Refreshing application memory cache from Neon...")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                # Machine Master Lookup
                c.execute("SELECT resource_name, resource_type, capacity_info FROM machine_master")
                MASTER_CACHE["machine_master"] = [{"name": r[0], "type": r[1], "capacity": json.loads(r[2] or '{}')} for r in c.fetchall()]
                
                # Channel Master Lookup
                c.execute("SELECT channel_name FROM channel_master")
                MASTER_CACHE["channel_master"] = [r[0] for r in c.fetchall()]
                
                # Weights Lookup
                c.execute("SELECT part_key, weight FROM weights")
                MASTER_CACHE["weights"] = {r[0]: float(r[1]) for r in c.fetchall()}
                
                # Setup Chart Lookup
                c.execute("SELECT part_variant, part_code, temperature FROM setup_chart")
                MASTER_CACHE["setup_chart"] = {(r[0], r[1]): float(r[2]) for r in c.fetchall()}
                
                # Ring Per Box Lookup
                c.execute("SELECT part_variant, part_code, qty, source FROM ring_per_box")
                MASTER_CACHE["ring_per_box"] = {}
                for var, pc, qty, src in c.fetchall():
                    if var not in MASTER_CACHE["ring_per_box"]: MASTER_CACHE["ring_per_box"][var] = {}
                    MASTER_CACHE["ring_per_box"][var][pc] = {"qty": float(qty), "source": src}
                    
        MASTER_CACHE["last_updated"] = time.time()
        print("In-Memory Master Cache updated successfully.")
    except Exception as e:
        print(f"Error refreshing cache from Neon database: {e}")

def update_dynamic_zeroset_plan_cache():
    """Maintains an isolated in-memory lifecycle for the high-priority dynamic Zeroset layout."""
    global ZEROSET_CACHE
    now = time.time()
    if now - ZEROSET_CACHE["last_updated"] < 3600 and ZEROSET_CACHE["sheets"]:
        return
    print("Refreshing Dynamic Zero Set Plan entries from Google Sheets...")
    fresh_sheets = parse_excel_to_df_dict(ZEROSET_URL, zeroset_sheet_filter)
    if fresh_sheets:
        ZEROSET_CACHE["sheets"] = {sheet: df.values.tolist() for sheet, df in fresh_sheets.items()}
        ZEROSET_CACHE["last_updated"] = now

# Cache Verification Guards
def ensure_caches_are_valid():
    if time.time() - MASTER_CACHE["last_updated"] > 3600 or not MASTER_CACHE["machine_master"]:
        refresh_memory_cache()
    update_dynamic_zeroset_plan_cache()

# ==========================================
# DATABASE OPERATION WRAPPERS (DYNAMIC DATA)
# ==========================================
def get_setting(key, default=None):
    if default is None: default = {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute('SELECT value FROM settings WHERE key=%s', (key,))
                row = c.fetchone()
                return json.loads(row[0]) if row else default
    except Exception:
        return default

def save_setting(key, value):
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute('INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value', (key, json.dumps(value)))
            conn.commit()

def get_previous_day_state(target_date_str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute('SELECT state_json FROM daily_state WHERE date < %s ORDER BY date DESC LIMIT 1', (target_date_str,))
                row = c.fetchone()
                if row: return json.loads(row[0])
    except Exception:
        pass
    return {"machines": {}, "wip": {}}

def save_daily_state(date_str, state_data):
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute('INSERT INTO daily_state (date, state_json) VALUES (%s, %s) ON CONFLICT (date) DO UPDATE SET state_json = EXCLUDED.state_json', (date_str, json.dumps(state_data)))
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
    machine_availability: List[Any] = []

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
    return {"status": "ok", "cache_ready": MASTER_CACHE["last_updated"] > 0}

@router.post("/api/trigger_sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_excel_to_neon)
    return {"status": "sync_triggered", "message": "Background sync processing safely initiated."}

@router.get("/api/monthly_tracking")
def get_monthly_tracking_api():
    return load_monthly_tracking()

@router.get("/api/machines")
def get_machines():
    """Populates the system endpoints with precise resource nomenclature directly from Neon master definitions."""
    ensure_caches_are_valid()
    resource_list = []
    for m in MASTER_CACHE["machine_master"]:
        resource_list.append({"machine": m["name"], "type": m["type"], "status": "Available"})
    for c in MASTER_CACHE["channel_master"]:
        resource_list.append({"machine": c, "type": "Channel", "status": "Available"})
    return {"status": "success", "data": resource_list}

@router.get("/api/get_plan")
def get_plan(date: str):
    try:
        plans = load_saved_plan()
        return {"status": "success", "data": plans.get(date, {})}
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

@router.get("/api/breakdowns")
def get_breakdowns(date: str):
    ensure_caches_are_valid()
    saved = {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("SELECT resource, status, start_time, end_time FROM breakdowns WHERE date=%s", (date,))
                for row in c.fetchall():
                    saved[row[0]] = {"status": row[1], "start_time": row[2], "end_time": row[3]}
    except Exception:
        pass

    res_list = []
    for m in MASTER_CACHE["machine_master"]:
        m_name = m["name"]
        t_label = "Furnace" if m["type"] == "HT" else ("Face Grinding" if m["type"] == "FACE" else "OD Grinding")
        res_list.append({"resource": m_name, "type": t_label, **saved.get(m_name, {"status": "Available", "start_time": "", "end_time": ""})})
        
    for ch in MASTER_CACHE["channel_master"]:
        res_list.append({"resource": ch, "type": "Channel", **saved.get(ch, {"status": "Available", "start_time": "", "end_time": ""})})

    return {"status": "success", "data": res_list}

@router.post("/api/save_breakdowns")
def save_breakdowns(payload: SaveBreakdownsRequest):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM breakdowns WHERE date=%s", (payload.date,))
                for ent in payload.entries:
                    c.execute("INSERT INTO breakdowns (date, resource, status, start_time, end_time) VALUES (%s, %s, %s, %s, %s)",
                              (payload.date, ent.resource, ent.status, ent.start_time, ent.end_time))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# ==========================================
# UTIL FUNCTIONS
# ==========================================
def normalize_channel(ch_str):
    ch = str(ch_str).strip().upper()
    ch = ch.replace("CH", "").replace("CHANNEL", "").replace(" ", "").strip()
    if ch.isdigit(): return f"CH{int(ch):02d}"
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
    return any(k in t for k in invalid_keywords)

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
            return rates[exact_key]
            
        robust_key = exact_key.replace(" ", "").upper()
        if robust_key in robust_rates:
            RATE_CACHE[key] = robust_rates[robust_key]
            return robust_rates[robust_key]
            
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
            return weights[f"{var}_{p_code}"]
            
    WEIGHT_CACHE[key] = None
    return None

def get_furnaces_for_part(display_name, p_code, furnace_map, furnace_specs):
    key = (display_name, p_code)
    if key in FURNACE_CACHE: return FURNACE_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in furnace_map: 
            FURNACE_CACHE[key] = furnace_map[f"{var}_{p_code}"]
            return furnace_map[f"{var}_{p_code}"]
            
    default_f = list(furnace_specs.keys())
    FURNACE_CACHE[key] = default_f
    return default_f

def get_box_for_part_detailed(display_name, p_code, box_matrix):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if var in box_matrix and p_code in box_matrix[var]: 
            return box_matrix[var][p_code]['qty'], box_matrix[var][p_code]['source'], var
            
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

def get_tempering_temp(display_name, p_code, setup_chart_matrix):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if (var, p_code) in setup_chart_matrix:
            return setup_chart_matrix[(var, p_code)]
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
# MAIN SCHEDULER ROUTE
# ==========================================
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    ensure_caches_are_valid()
    debug_logs = []
    unscheduled = []
    
    RATE_CACHE.clear()
    WEIGHT_CACHE.clear()
    FURNACE_CACHE.clear()
    VARIANTS_CACHE.clear()
    
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
        
        # Pull dynamic hourly structured data from ZeroSet cache without hit penalties
        for sheet_name, sheet_matrix in ZEROSET_CACHE["sheets"].items():
            sheet_str_upper = str(sheet_name).strip().upper()
            if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                ch_name = f"CH{sheet_str_upper.zfill(2)}"
            elif sheet_str_upper == "SABB": ch_name = "SABB"
            elif sheet_str_upper.startswith("T ") or any(sheet_str_upper.startswith(f"T{k}") for k in range(1, 12)):
                ch_name = sheet_str_upper
            else: ch_name = sheet_str_upper

            ir_multiplier = 2 if any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB"]) else 1
            
            r_idx, type_col_idx, mv_col_idx = None, None, None
            c1_col, c2_col = None, None
            monthly_cols = []
            
            for i in range(min(25, len(sheet_matrix))):
                row_strs = [str(x).strip().upper() for x in sheet_matrix[i]]
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
                    for j, val in enumerate(sheet_matrix[i]):
                        if is_target_date(val, day_1): c1_col = j
                        if is_target_date(val, day_2): c2_col = j
                        s_val = str(val).strip()
                        if s_val.isdigit() and 1 <= int(s_val) <= 31: monthly_cols.append(j)
                if r_idx is not None and type_col_idx is not None and c1_col is not None: break

            col_to_use = type_col_idx if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "SABB"] else mv_col_idx
            if col_to_use is None: col_to_use = mv_col_idx if mv_col_idx is not None else type_col_idx

            if r_idx is not None and type_col_idx is not None:
                last_mf = ""
                for idx in range(r_idx + 1, len(sheet_matrix)):
                    row_vals_zero = sheet_matrix[idx]
                    
                    mf_val = str(row_vals_zero[type_col_idx]).strip() if (type_col_idx is not None and type_col_idx < len(row_vals_zero)) else ""
                    if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                    raw_t = str(row_vals_zero[col_to_use]).strip() if (col_to_use is not None and col_to_use < len(row_vals_zero)) else ""
                    if not raw_t or raw_t in ["NAN", "NONE"]: raw_t = last_mf
                    if is_invalid_part(raw_t): continue
                    
                    display_name = get_display_name(raw_t)
                    if display_name not in monthly_data[month_str]:
                        monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": ch_name}
                    
                    row_monthly_sum = sum([safe_float(row_vals_zero[col]) for col in monthly_cols if col < len(row_vals_zero)])
                    if row_monthly_sum > 0: monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                    
                    val1 = safe_float(row_vals_zero[c1_col]) if (c1_col is not None and c1_col < len(row_vals_zero)) else 0.0
                    val2 = safe_float(row_vals_zero[c2_col]) if (c2_col is not None and c2_col < len(row_vals_zero)) else 0.0
                    
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

        # Map RAM Caches into exact local algorithm placeholders
        box_matrix = MASTER_CACHE["ring_per_box"]
        weight_matrix = MASTER_CACHE["weights"]
        setup_chart_matrix = MASTER_CACHE["setup_chart"]
        
        furnace_specs_local = DEFAULT_FURNACES.copy()
        furnace_map = {} # Loaded fallbacks handled dynamically inside caching structures
        
        resources = []
        for m in MASTER_CACHE["machine_master"]:
            resources.append(Resource(m["name"], m["type"], m["capacity"]))

        current_state = get_previous_day_state(payload.date)
        work_items = []
        
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
            if "|" not in w_key: continue
            disp, pc = w_key.split('|')
            ch_norm = w_data.get("channel", "UNKNOWN")
            
            if "ht_balance" in w_data: ht_balances[(disp, pc)] = float(w_data["ht_balance"])
                
            routing = get_routing_for_part(ch_norm, pc)
            first_stage = get_first_required_stage(routing)
            
            for stage in ['HT', 'FACE', 'OD']:
                if stage not in routing: continue
                if stage not in w_data: continue
                
                stage_data = w_data.get(stage, {})
                qty = float(stage_data.get("qty", 0.0))
                rt = float(stage_data.get("rt", 0.0))
                
                if qty > 0 and stage != first_stage:
                    work_items.append(WorkItem(stage, disp, pc, -1, ch_norm, qty, rt, 10000.0, routing))

        ch_stats = {}
        for day_idx, demands in [(0, channel_demands_day1), (1, channel_demands_day2)]:
            for display_name, data in demands.items():
                ch_norm = normalize_channel(data['channel'])
                if ch_norm not in ch_stats: ch_stats[ch_norm] = {'demand': 0.0, 'buffer': 0.0, 'score': 1.0}
                ch_stats[ch_norm]['demand'] += data.get('IR', 0) + data.get('OR', 0)

        tracker_ht = {}
        for display_name, data in channel_demands_day1.items():
            for p_code in ['IR', 'OR']:
                raw_d1 = float(data.get(p_code, 0.0))
                if raw_d1 > 0:
                    key = (display_name, p_code)
                    if key not in tracker_ht: tracker_ht[key] = {'raw_d1': 0.0, 'raw_d2': 0.0, 'channel': data['channel']}
                    tracker_ht[key]['raw_d1'] = raw_d1
                    
        for display_name, data in channel_demands_day2.items():
            for p_code in ['IR', 'OR']:
                raw_d2 = float(data.get(p_code, 0.0))
                if raw_d2 > 0:
                    key = (display_name, p_code)
                    if key not in tracker_ht: tracker_ht[key] = {'raw_d1': 0.0, 'raw_d2': 0.0, 'channel': data['channel']}
                    tracker_ht[key]['raw_d2'] = raw_d2

        for key, reqs in tracker_ht.items():
            disp, pc = key
            ch_norm = normalize_channel(reqs['channel'])
            routing = get_routing_for_part(ch_norm, pc)
            first_stage = get_first_required_stage(routing)
            
            if not first_stage: continue
            
            raw_d1 = reqs['raw_d1']
            raw_d2 = reqs['raw_d2']
            bal = ht_balances.get(key, 0.0)
            
            d1_sat = min(raw_d1, bal)
            bal -= d1_sat
            net_d1 = raw_d1 - d1_sat
            
            d2_sat = min(raw_d2, bal)
            bal -= d2_sat
            net_d2 = raw_d2 - d2_sat
            
            reqs['net_d1'] = net_d1
            reqs['net_d2'] = net_d2
            reqs['d2_satisfied'] = d2_sat
            reqs['leftover_bal'] = bal
            reqs['first_stage'] = first_stage
            
            if net_d1 > 0:
                work_items.append(WorkItem(first_stage, disp, pc, 0, reqs['channel'], net_d1, 0.0, ch_stats[ch_norm]['score'], routing))
            if net_d2 > 0:
                work_items.append(WorkItem(first_stage, disp, pc, 1, reqs['channel'], net_d2, 0.0, ch_stats[ch_norm]['score'], routing))

        # Enforce Saved Core & Channel Breakdowns accurately during execution blocks
        db_breakdowns = {}
        try:
            with get_db_connection() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT resource, status, start_time, end_time FROM breakdowns WHERE date=%s", (payload.date,))
                    for row in c.fetchall():
                        db_breakdowns[row[0]] = {"status": row[1], "start_time": row[2], "end_time": row[3]}
        except Exception:
            pass

        for res in resources:
            bd_info = db_breakdowns.get(res.id)
            if bd_info:
                if bd_info["status"] == "Complete Breakdown": res.blocked = True
                elif bd_info["status"] == "Available":
                    st_str = bd_info.get('start_time', '')
                    et_str = bd_info.get('end_time', '')
                    if st_str and et_str:
                        res.has_bd = True
                        res.bd_start = time_str_to_float(st_str)
                        res.bd_end = time_str_to_float(et_str)

        for item in work_items:
            init_item_resources(item, resources, furnace_map, weight_matrix, furnace_specs_local)

        for i in range(len(work_items)):
            item1 = work_items[i]
            if item1.qty <= 0.01 or item1.day_idx != 0: continue
            if not item1.valid_resources: continue
            
            res_dummy = item1.valid_resources[0]
            rate_dummy = item1.rates[res_dummy.id][0] if res_dummy.type == 'HT' else item1.rates[res_dummy.id]
            weight_dummy = item1.rates[res_dummy.id][1] if res_dummy.type == 'HT' else 1.0
            
            est_time1 = (item1.qty * weight_dummy) / rate_dummy if res_dummy.type == 'HT' else item1.qty / rate_dummy
            merge_thresh = 1.0 if res_dummy.type == 'HT' else 2.0
            
            for j in range(i + 1, len(work_items)):
                item2 = work_items[j]
                if (item2.day_idx == 1 and 
                    item2.disp == item1.disp and 
                    item2.pc == item1.pc and 
                    item2.stage == item1.stage and 
                    item2.channel == item1.channel and 
                    item2.qty > 0.01):
                    
                    est_time2 = (item2.qty * weight_dummy) / rate_dummy if res_dummy.type == 'HT' else item2.qty / rate_dummy
                    if est_time1 < merge_thresh or est_time2 < merge_thresh:
                        item1.qty += item2.qty
                        item2.qty = 0.0
                    break

        for target_day in [-1, 0, 1]:
            current_max_time = 24.0 
            for r in resources:
                r.max_time = current_max_time
                if r.ready_time < current_max_time: r.blocked = False
                    
            while True:
                active_items = [i for i in work_items if i.qty > 0.01 and i.ready_time < current_max_time and i.day_idx == target_day]
                
                filtered_active_items = []
                for i in active_items:
                    ch_info = None
                    for k, v in db_breakdowns.items():
                        if normalize_channel(k) == normalize_channel(i.channel):
                            ch_info = v; break
                    if ch_info and ch_info["status"] == "Complete Breakdown":
                        i.missing_reason = "Channel Complete Breakdown"
                        continue
                    filtered_active_items.append(i)
                active_items = filtered_active_items
                
                if not active_items: break 
                    
                best_pair = None
                best_key = (float('inf'), float('inf'), float('inf'), float('inf'), float('-inf'))
                
                for item in active_items:
                    for res in item.valid_resources:
                        if res.blocked or res.ready_time >= res.max_time: continue
                        
                        rate_or_cap = item.rates[res.id][0] if res.type == 'HT' else item.rates[res.id]
                        
                        if res.type == 'HT':
                            if res.last_fam is None: setup = 0.5
                            elif res.last_fam == item.disp and res.last_pc == item.pc: setup = 0.0
                            else:
                                prev_temp = get_tempering_temp(res.last_fam, res.last_pc, setup_chart_matrix)
                                curr_temp = get_tempering_temp(item.disp, item.pc, setup_chart_matrix)
                                setup = 1.5 if (prev_temp is not None and curr_temp is not None and prev_temp != curr_temp) else 0.5
                        else:
                            setup = 2.0
                            if res.last_fam == item.disp: setup = 0.0 if res.last_pc == item.pc else 2.0 
                        
                        start_time = max(res.ready_time + setup, item.ready_time)
                        if start_time >= res.max_time: continue
                        
                        is_continuation = (res.last_fam == item.disp and res.last_pc == item.pc and start_time <= res.ready_time + 0.01)
                        gap = max(0.0, item.ready_time - (res.ready_time + setup))
                        
                        if res.type == 'HT':
                            weight = item.rates[res.id][1]
                            req_time = (item.qty * weight) / rate_or_cap
                        else:
                            req_time = item.qty / rate_or_cap
                            
                        available_time_limit = min(res.max_time, res.bd_start if (res.has_bd and start_time < res.bd_start) else res.max_time)
                        time_available = available_time_limit - start_time
                        
                        needs_split = 1 if req_time > time_available else 0
                        key = (needs_split, start_time, item.day_idx, gap, -item.priority)
                        
                        if key < best_key:
                            best_key = key
                            best_pair = (res, item, start_time, setup, rate_or_cap, is_continuation)
                            
                if not best_pair: break
                    
                res, item, start_time, setup, rate_or_cap, is_continuation = best_pair
                chunk_qty = item.qty
                
                if res.type == 'HT':
                    weight = item.rates[res.id][1]
                    actual_time = (chunk_qty * weight) / rate_or_cap
                else:
                    actual_time = chunk_qty / rate_or_cap

                if start_time < 24.0 and (start_time + actual_time) > 24.0:
                    max_allowed_time = min(6.0, 30.0 - start_time)
                    if actual_time > max_allowed_time:
                        actual_time = max_allowed_time
                        if res.type == 'HT': chunk_qty = (actual_time * rate_or_cap) / weight
                        else: chunk_qty = actual_time * rate_or_cap
                
                if res.has_bd and start_time < res.bd_end and (start_time + actual_time) > res.bd_start:
                    actual_time += (res.bd_end - max(start_time, res.bd_start))

                ch_info_active = None
                for k, v in db_breakdowns.items():
                    if normalize_channel(k) == normalize_channel(item.channel):
                        ch_info_active = v; break
                if ch_info_active and ch_info_active["status"] == "Available":
                    c_st = ch_info_active.get('start_time', '')
                    c_et = ch_info_active.get('end_time', '')
                    if c_st and c_et:
                        ch_bds = time_str_to_float(c_st)
                        ch_bde = time_str_to_float(c_et)
                        if start_time < ch_bde and (start_time + actual_time) > ch_bds:
                            actual_time += (ch_bde - max(start_time, ch_bds))

                if res.type == 'HT':
                    res_ready_time = start_time + actual_time + 0.5
                    out_time = start_time + actual_time + 3.5
                    display_rate = f"{round((chunk_qty * weight), 1)} kg"
                    if item.disp in monthly_data.get(month_str, {}): 
                        monthly_data[month_str][item.disp]["produced"] += chunk_qty
                else:
                    res_ready_time = start_time + actual_time
                    out_time = res_ready_time
                    display_rate = rate_or_cap
                    
                is_same_item = (res.last_fam == item.disp and res.last_pc == item.pc)
                res.ready_time = res_ready_time
                res.last_fam = item.disp
                res.last_pc = item.pc
                
                if res.ready_time >= 24.0: res.blocked = True
                item.qty -= chunk_qty
                
                next_stage = get_next_required_stage(res.type, item.routing)
                if next_stage: 
                    new_item = WorkItem(next_stage, item.disp, item.pc, item.day_idx, item.channel, chunk_qty, out_time, item.priority, item.routing)
                    init_item_resources(new_item, resources, furnace_map, weight_matrix, furnace_specs_local)
                    work_items.append(new_item)

                rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix)
                can_merge = (res.type != 'HT' and res.rows and is_same_item and is_continuation)
                
                day_label = " (WIP)" if item.day_idx == -1 else (" (D2)" if item.day_idx == 1 else " (D1)")

                if can_merge:
                    last_row = res.rows[-1]
                    old_qty = int(float(last_row["qty"]))
                    new_qty = old_qty + int(chunk_qty)
                    last_row["qty"] = str(new_qty)
                    old_start = last_row["timing"].split('-')[0]
                    new_end = format_time(out_time if res.type == 'HT' else res_ready_time)
                    last_row["timing"] = f"{old_start}-{new_end}"
                    if res.type != 'HT':
                        last_row["std_box"] = str(math.ceil(new_qty / rpb)) if rpb > 0 else f"{int(new_qty)}(Q)"
                else:
                    timing_display = f"{format_time(start_time)}-{format_time(out_time if res.type == 'HT' else res_ready_time)}"
                    is_terminal = (next_stage is None)
                    if res.type == 'HT':
                        res.rows.append({"part": f"{item.disp}-{item.pc}{day_label}", "qty": str(int(chunk_qty)), "cha": item.channel, "rate": display_rate, "timing": timing_display, "alert": False, "is_terminal": is_terminal})
                    else:
                        display_val = str(math.ceil(chunk_qty / rpb)) if rpb > 0 else f"{int(chunk_qty)}(Q)"
                        res.rows.append({"part": f"{item.disp} {item.pc}{day_label}", "qty": str(int(chunk_qty)), "std_box": display_val, "timing": timing_display, "p_2nd": "1" if len(res.rows) == 0 else "", "p_3rd": "1" if len(res.rows) == 1 else "", "alert": False, "p_label": f"P{len(res.rows) + 1}", "is_terminal": is_terminal})

        end_state = { "machines": {}, "wip": {} }
        for r in resources:
            end_state["machines"][r.id] = {
                "ready_time": r.ready_time - 24.0,
                "last_fam": r.last_fam,
                "last_pc": r.last_pc
            }

        pending_ht = {}
        for item in work_items:
            if item.qty <= 0.01: continue
            key = (item.disp, item.pc)
            if item.stage == get_first_required_stage(item.routing):
                pending_ht[key] = pending_ht.get(key, 0.0) + item.qty

        new_ht_balances = {}
        for key, reqs in tracker_ht.items():
            fs = reqs.get('first_stage')
            if not fs: continue
            p_ht = pending_ht.get(key, 0.0)
            sched_ht = reqs['net_d1'] + reqs['net_d2']
            completed_ht = max(0.0, sched_ht - p_ht)
            completed_d2 = max(0.0, completed_ht - reqs['net_d1'])
            new_bal = reqs['d2_satisfied'] + completed_d2 + reqs['leftover_bal']
            if new_bal > 0: new_ht_balances[key] = new_bal
                
        for key, bal in ht_balances.items():
            if key not in tracker_ht and bal > 0: new_ht_balances[key] = bal

        for item in work_items:
            if item.qty <= 0.01: continue
            if item.stage == 'HT' and get_weight_for_part(item.disp, item.pc, weight_matrix) is None: assigned_reason = "Missing Weight"
            elif any(r.type == item.stage for r in resources) and len(item.valid_resources) == 0: assigned_reason = "Machine Rate Not Available"
            elif not item.routing or item.stage not in item.routing: assigned_reason = "Missing Routing"
            elif not any(r.type == item.stage for r in resources): assigned_reason = "No Compatible Machine"
            elif item.ready_time < 24.0 and len(item.valid_resources) > 0: assigned_reason = "Insufficient Capacity"
            elif item.day_idx == -1: assigned_reason = "Waiting for Next Process"
            elif item.ready_time >= 24.0: assigned_reason = "Scheduling Window Exhausted"
            else: assigned_reason = "Not Scheduled"

            if item.stage != get_first_required_stage(item.routing):
                w_key = f"{item.disp}|{item.pc}"
                if w_key not in end_state["wip"]: end_state["wip"][w_key] = {"channel": item.channel}
                if item.stage not in end_state["wip"][w_key]: end_state["wip"][w_key][item.stage] = {"qty": 0, "rt": 0}
                end_state["wip"][w_key][item.stage]["qty"] += item.qty
                end_state["wip"][w_key][item.stage]["rt"] = max(0.0, item.ready_time - 24.0)

            rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix)
            missed_val = f"{int(item.qty)}(Q)" if rpb <= 0 else str(math.ceil(item.qty / rpb))
            day_label = "WIP" if item.day_idx == -1 else ("Day 2" if item.day_idx == 1 else "Day 1")
            part_display = f"{item.disp} {item.pc} ({day_label})"
            
            unscheduled.append({
                "stage": item.stage, 
                "part": part_display, 
                "missed_boxes": missed_val,
                "status": assigned_reason, 
                "reason": assigned_reason 
            })

        for key, bal in new_ht_balances.items():
            if bal > 0:
                w_key = f"{key[0]}|{key[1]}"
                if w_key not in end_state["wip"]:
                    channel = tracker_ht[key]['channel'] if key in tracker_ht else "UNKNOWN"
                    end_state["wip"][w_key] = {"channel": channel}
                end_state["wip"][w_key]["ht_balance"] = bal

        final_face, final_od, furnaces_formatted = [], [], []
        today_prod_map = {}
        
        for r in resources:
            if r.type == 'FACE': final_face.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'OD': final_od.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'HT': furnaces_formatted.append({"furnace": r.id, "capacity": f"Total Cap: {int(r.capacity_info if isinstance(r.capacity_info, (int, float)) else 250)} kg/hr", "rows": r.rows})
            
            for row in r.rows:
                if row.get("is_terminal"):
                    part_str = row.get("part", "")
                    qty = float(row.get("qty", 0)) if str(row.get("qty", 0)).replace('.','',1).isdigit() else 0
                    disp = part_str.split("-")[0] if "-" in part_str else part_str.split(" ")[0]
                    today_prod_map[disp] = today_prod_map.get(disp, 0) + qty

        summary_list = []
        for disp_name, data in monthly_data.get(month_str, {}).items():
            ch = data.get("channel", "Unknown")
            mo_req = data.get("total_req", 0)
            mtd_prod = data.get("produced", 0)
            d1_data = channel_demands_day1.get(disp_name, {})
            d1_req = max(d1_data.get("IR", 0), d1_data.get("OR", 0))
            t_prod = today_prod_map.get(disp_name, 0)
            summary_list.append({
                "type": disp_name, "channel": ch, "monthly_req": int(mo_req), "today_req": int(d1_req), "today_prod": int(t_prod),
                "mtd_prod": int(mtd_prod), "balance": int(mo_req - mtd_prod),
                "remaining_pct": round(((mo_req - mtd_prod) / mo_req * 100), 1) if mo_req > 0 else 0,
                "difference": int(t_prod - d1_req)
            })
            
        snapshot = {"monthly_data": monthly_data.get(month_str, {}), "plant_state": end_state}
        save_setting("pending_state", snapshot)

        return {
            "status": "success", 
            "debug_logs": debug_logs, 
            "data": {
                "face_grinding": final_face, 
                "od_grinding": final_od, 
                "heat_treatment": furnaces_formatted, 
                "unscheduled": unscheduled, 
                "summary": summary_list,
                "state_snapshot": snapshot
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs + [f"CRITICAL ERROR: {traceback.format_exc()}"], "detail": str(e)}

# ==========================================
# FIXED REQUIRED DATA AVAILABILITY ENDPOINT
# ==========================================
@router.get("/api/data_availability")
def get_data_availability(date: str):
    """Safely computes data mappings utilizing the non-blocking Neon architecture lookups."""
    ensure_caches_are_valid()
    try:
        req_date = datetime.strptime(date, "%Y-%m-%d")
        availability_records = []
        
        # Load Zeroset definitions from cache safely without repetitive calls
        for sheet_name, sheet_matrix in ZEROSET_CACHE["sheets"].items():
            sheet_str_upper = str(sheet_name).strip().upper()
            if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                ch_name = f"CH{sheet_str_upper.zfill(2)}"
            else:
                ch_name = sheet_str_upper
                
            r_idx, type_col_idx = None, None
            for i in range(min(25, len(sheet_matrix))):
                row_strs = [str(x).strip().upper() for x in sheet_matrix[i]]
                if any(k in " ".join(row_strs) for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING', 'TOTAL']):
                    r_idx = i
                for j, val in enumerate(row_strs):
                    if val in ["TYPE", "MF", "PART NO", "BRG NO"]:
                        type_col_idx = j; break
                if r_idx is not None and type_col_idx is not None: break

            if r_idx is not None and type_col_idx is not None:
                for idx in range(r_idx + 1, len(sheet_matrix)):
                    try:
                        row_vals = sheet_matrix[idx]
                        if type_col_idx >= len(row_vals): continue
                        raw_t = str(row_vals[type_col_idx]).strip()
                        if not raw_t or is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        
                        # Process both configurations safely (IR & OR)
                        for pc in ['IR', 'OR']:
                            # Weight validation
                            wt = MASTER_CACHE["weights"].get(f"{display_name}_{pc}")
                            
                            # Ring per box validation
                            rpb_info = MASTER_CACHE["ring_per_box"].get(display_name, {}).get(pc, {})
                            rpb = rpb_info.get("qty", 0.0)
                            
                            # Grinding compatibility maps tracking
                            face_rate = 0.0
                            od_rate = 0.0
                            for m in MASTER_CACHE["machine_master"]:
                                if m["type"] == "FACE":
                                    face_rate = max(face_rate, m["capacity"].get(f"{display_name}_{pc}", 0.0))
                                elif m["type"] == "OD":
                                    od_rate = max(od_rate, m["capacity"].get(f"{display_name}_{pc}", 0.0))

                            availability_records.append({
                                "part_type": display_name,
                                "part_code": pc,
                                "channel": ch_name,
                                "weight": f"{wt} kg" if wt else "Missing",
                                "ring_per_box": int(rpb) if rpb > 0 else "Missing",
                                "face_rate": f"{int(face_rate)}/hr" if face_rate > 0 else "Missing",
                                "od_rate": f"{int(od_rate)}/hr" if od_rate > 0 else "Missing",
                                "status": "Ready" if (wt and rpb > 0 and (face_rate > 0 or od_rate > 0)) else "Incomplete"
                            })
                    except Exception:
                        continue # Resilient constraint: individual row calculation anomalies must never drop the process

        return {"status": "success", "data": availability_records}
    except Exception as e:
        return {"status": "error", "message": f"Data Availability pipeline failure: {str(e)}", "data": []}
