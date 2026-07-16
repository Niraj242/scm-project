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
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from database import get_db
from sqlalchemy.orm import Session
from datetime import datetime
import models

router = APIRouter()


ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

# Cache tables limited to the lifecycle of a single request
RATE_CACHE = {}
WEIGHT_CACHE = {}
FURNACE_CACHE = {}
VARIANTS_CACHE = {}  

# Global memory cache for downloaded files to optimize performance 
DOWNLOAD_CACHE = {}
CACHE_TTL_SECONDS = 300  

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
        c.execute('CREATE TABLE IF NOT EXISTS breakdowns (date TEXT, resource TEXT, status TEXT, start_time TEXT, end_time TEXT, PRIMARY KEY(date, resource))')
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

class BreakdownItem(BaseModel):
    resource: str
    status: str
    start_time: str
    end_time: str

class SaveBreakdownsRequest(BaseModel):
    date: str
    entries: List[BreakdownItem]

# ==========================================
# UTIL FUNCTIONS & CACHED EXCEL PROCESSOR
# ==========================================
def fetch_with_cache(url: str) -> bytes:
    now = time.time()
    if url in DOWNLOAD_CACHE:
        cached_content, timestamp = DOWNLOAD_CACHE[url]
        if now - timestamp < CACHE_TTL_SECONDS:
            return cached_content
    
    resp = requests.get(url, timeout=60)
    if resp.status_code == 200:
        DOWNLOAD_CACHE[url] = (resp.content, now)
        return resp.content
    raise Exception(f"Failed to fetch Excel sheet from {url}. Status code: {resp.status_code}")

def process_excel_sequentially(url, sheet_names_to_process=None, usecols=None):
    if not url or url.strip() == "": 
        return
    try:
        content = fetch_with_cache(url)
        with io.BytesIO(content) as file_buffer:
            try:
                xls = pd.ExcelFile(file_buffer, engine='calamine')
            except Exception:
                xls = pd.ExcelFile(file_buffer, engine='openpyxl')
                
            target_sheets = sheet_names_to_process if sheet_names_to_process else xls.sheet_names
            
            for sheet in target_sheets:
                if sheet in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet, header=None, usecols=usecols)
                    yield sheet, df
                    del df
                    gc.collect()
            del xls
        gc.collect()
    except Exception as e:
        print(f"Error loading sequentially from {url}: {e}")

MASTER_RESOURCES_CACHE = {"furnaces": [], "face": [], "od": [], "channels": []}

def get_all_resources():
    if MASTER_RESOURCES_CACHE["channels"]:
        return MASTER_RESOURCES_CACHE
    
    channels = set()
    for ch, pc in PROCESS_FLOW.keys():
        channels.add(ch)
    MASTER_RESOURCES_CACHE["channels"] = sorted(list(channels))

    furnaces = set(DEFAULT_FURNACES.keys())
    MASTER_RESOURCES_CACHE["furnaces"] = sorted(list(furnaces))

    face_mcs = set()
    od_mcs = set()
    for sheet_name, df_m in process_excel_sequentially(SHO_PRODUCTION_URL):
        if sheet_name not in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.', 'Channel Process Flexibility']:
            str_matrix = df_m.fillna('').astype(str).values
            for r in range(str_matrix.shape[0]):
                row_text = " ".join(str_matrix[r]).upper()
                if 'MACHINE' in row_text or 'M/C' in row_text:
                    cells = [c.strip() for c in str_matrix[r] if c.strip()]
                    m_cand = cells[1] if len(cells) > 1 else f"MC_{r}"
                    if m_cand and m_cand != "MACHINE" and m_cand != "M/C":
                        if "FACE" in row_text or "DDS" in m_cand.upper() or "BG" in m_cand.upper(): face_mcs.add(m_cand)
                        elif "OD" in row_text or "CL" in m_cand.upper() or "CELL" in m_cand.upper() or "+" in m_cand: od_mcs.add(m_cand)

    if not face_mcs: face_mcs = {"DDS 1", "DDS 2", "BG 1"}
    if not od_mcs: od_mcs = {"CL 1", "CL 2", "CELL 1"}

    MASTER_RESOURCES_CACHE["face"] = sorted(list(face_mcs))
    MASTER_RESOURCES_CACHE["od"] = sorted(list(od_mcs))
    return MASTER_RESOURCES_CACHE

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

    suffixes = ['VK210', 'X/Q', '/Q', 'J2', 'AE', 'AB', 'A', 'B', 'E', 'J', 'X', 'Q', 'LM', 'M', 'ETN9', 'J2/Q']
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
    
    prefixes_to_strip = ['BAH', 'BTH', 'BAR', 'BB1B', 'BB1', 'BB', 'BT1', 'BT', 'UC', 'LM', 'FACE ', 'OD ', 'HT ', 'FACE', 'OD', 'HT', 'BDA']
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

def get_tempering_temp(display_name, p_code, setup_chart_matrix):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if (var, p_code) in setup_chart_matrix:
            return setup_chart_matrix[(var, p_code)]
    return None

# ==========================================
# ROBUST BUFFER DAYS CONVERSION HELPERS
# ==========================================
def get_all_buffers_for_part(disp, pc, ch_norm, payload, box_matrix, demand_rings):
    """
    Parses the flat JSON dictionary structures passed by the React Frontend 
    gracefully to assign the correct buffer quantity to the exact channels.
    Returns a dictionary of available rings mapped by location.
    """
    buffers_rings = {"CH BUFFER": 0.0, "OD": 0.0, "FACE": 0.0, "HT": 0.0}
    
    # Matches the Dropdown options accurately
    unit_mode = str(getattr(payload, 'unit_mode', 'DAYS')).strip().upper()
    if not unit_mode: unit_mode = 'DAYS'
    
    rpb = get_box_for_part(disp, pc, box_matrix)
    
    def convert(val):
        if val <= 0: return 0.0
        if "DAY" in unit_mode: 
            return float(val * demand_rings)
        elif "BOX" in unit_mode: 
            return float(val * rpb)
        else: 
            return float(val) # For No. of Rings

    entries = payload.entries if payload.entries else {}
    ch_clean = normalize_channel(ch_norm).replace(" ", "")
    
    # Map the front-end row identifiers to backend validation rules
    buffer_type_map = {
        'ch_buffer_1': ('type_1', 'CH BUFFER'),
        'ch_buffer_2': ('next_type_1', 'CH BUFFER'),
        'od_buffer_1': ('type_2', 'OD'),
        'od_buffer_2': ('next_type_2', 'OD'),
        'face_buffer_1': ('type_3', 'FACE'),
        'face_buffer_2': ('type_4', 'FACE'),
        'ht_buffer_1': ('type_5', 'HT'),
        'ht_buffer_2': ('type_6', 'HT'),
        'buffer_in_days': (['running', 'next_type_3'], 'CH BUFFER')
    }
    
    disp_variants = [disp.upper()] + [str(v).upper() for v in get_lookup_variants(disp, pc)]

    for key, val in entries.items():
        # Ensure key corresponds to the matching Process Code (IR / OR)
        if not key.endswith(f"_{pc}"):
            continue
            
        prefix_and_ch = key[:-(len(pc)+1)]
        
        # Iterate to find which field this buffer value corresponds to
        for buf_prefix, mapping in buffer_type_map.items():
            if prefix_and_ch.startswith(buf_prefix + "_"):
                
                # Extract channel logic properly
                ch_part = prefix_and_ch[len(buf_prefix)+1:]
                
                if normalize_channel(ch_part).replace(" ", "") == ch_clean:
                    
                    type_keys = mapping[0] if isinstance(mapping[0], list) else [mapping[0]]
                    loc = mapping[1]
                    
                    is_match = False
                    for t_prefix in type_keys:
                        type_key = f"{t_prefix}_{ch_part}_{pc}"
                        type_val = str(entries.get(type_key, "")).strip().upper()
                        
                        if type_val and type_val in disp_variants:
                            is_match = True
                            break
                            
                    # If this type matches the demand part, safely parse the quantity
                    if is_match:
                        buffers_rings[loc] += convert(safe_float(val))

    return buffers_rings

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
# GENERAL ENDPOINTS
# ==========================================
@router.get("/api/health")
def health_check():
    return {"status": "ok"}

@router.get("/api/monthly_tracking")
def get_monthly_tracking_api():
    return load_monthly_tracking()

@router.get("/api/machines")
def get_machines():
    try:
        res = get_all_resources()
        if not res: res = {}
        machines_dict = {}
        for f in res.get("furnaces", []): machines_dict[f] = {"type": "Furnace"}
        for m in res.get("face", []): machines_dict[m] = {"type": "Face Grinding"}
        for m in res.get("od", []): machines_dict[m] = {"type": "OD Grinding"}
        for c in res.get("channels", []): machines_dict[c] = {"type": "Channel"}
        return {"status": "success", "data": machines_dict}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": {}}

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

@router.post("/api/summary")
def get_summary(payload: dict):
    try:
        date = payload.get("date", datetime.now().strftime("%Y-%m-%d"))
        plans = load_saved_plan()
        plan_data = plans.get(date, {})
        return {"status": "success", "data": plan_data.get("summary", [])}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/api/breakdowns")
def get_breakdowns(date: str):
    saved = {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT resource, status, start_time, end_time FROM breakdowns WHERE date=?", (date,))
            for row in c.fetchall():
                saved[row[0]] = {"status": row[1], "start_time": row[2], "end_time": row[3]}
    except Exception:
        pass

    master = get_all_resources()
    res_list = []
    
    for f in master["furnaces"]: res_list.append({"resource": f, "type": "Furnace", **saved.get(f, {"status": "Available", "start_time": "", "end_time": ""})})
    for m in master["face"]: res_list.append({"resource": m, "type": "Face Grinding", **saved.get(m, {"status": "Available", "start_time": "", "end_time": ""})})
    for m in master["od"]: res_list.append({"resource": m, "type": "OD Grinding", **saved.get(m, {"status": "Available", "start_time": "", "end_time": ""})})
    for c in master["channels"]: res_list.append({"resource": c, "type": "Channel", **saved.get(c, {"status": "Available", "start_time": "", "end_time": ""})})

    return {"status": "success", "data": res_list}

@router.post("/api/save_breakdowns")
def save_breakdowns(payload: SaveBreakdownsRequest):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM breakdowns WHERE date=?", (payload.date,))
            for ent in payload.entries:
                c.execute("INSERT INTO breakdowns (date, resource, status, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
                          (payload.date, ent.resource, ent.status, ent.start_time, ent.end_time))
            conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ==========================================
# MAIN Buffer ROUTE
# ==========================================


class BufferSaveRequest(BaseModel):
    buffer_date: str
    sector: str
    unit_mode: str
    entries: Dict[str, Any]


@router.post("/api/save_buffers")
def save_buffers(payload: BufferSaveRequest, db: Session = Depends(get_db)):
    try:
        req_date = datetime.strptime(payload.buffer_date, "%Y-%m-%d").date()

        existing_entry = db.query(models.BufferEntry).filter(
            models.BufferEntry.buffer_date == req_date,
            models.BufferEntry.sector == payload.sector
        ).first()

        entries_json = json.dumps(payload.entries, ensure_ascii=False)

        if existing_entry:
            existing_entry.unit_mode = payload.unit_mode
            existing_entry.entries_json = entries_json
            existing_entry.updated_at = datetime.utcnow()
        else:
            new_entry = models.BufferEntry(
                buffer_date=req_date,
                sector=payload.sector,
                unit_mode=payload.unit_mode,
                entries_json=entries_json
            )
            db.add(new_entry)

        db.commit()

        return {
            "status": "success",
            "message": "Buffer data saved successfully"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/get_buffers")
def get_buffers(buffer_date: str, sector: str, db: Session = Depends(get_db)):
    try:
        req_date = datetime.strptime(buffer_date, "%Y-%m-%d").date()

        entry = db.query(models.BufferEntry).filter(
            models.BufferEntry.buffer_date == req_date,
            models.BufferEntry.sector == sector
        ).first()

        if not entry:
            return {
                "status": "success",
                "unit_mode": "Days",
                "entries": {}
            }

        return {
            "status": "success",
            "unit_mode": entry.unit_mode,
            "entries": json.loads(entry.entries_json or "{}")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ==========================================
# MAIN SCHEDULER ROUTE
# ==========================================
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = []
    
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

        channel_demands_day1 = {} 
        channel_demands_day2 = {}
        
        # 1. LOAD ZEROSET SEQUENTIALLY
        for sheet_name, df_zero in process_excel_sequentially(ZEROSET_URL):
            sheet_str_upper = str(sheet_name).strip().upper()
            if sheet_str_upper in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
                ch_name = f"CH{sheet_str_upper.zfill(2)}"
            elif sheet_str_upper == "SABB": ch_name = "SABB"
            elif sheet_str_upper.startswith("T ") or any(sheet_str_upper.startswith(f"T{k}") for k in range(1, 10)):
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
                    row_vals_zero = list(df_zero.iloc[idx].values)
                    
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

        # 2. LOAD BOX RING MATRIX SEQUENTIALLY (WITH SETUP CHART)
        box_matrices = {"tier1": {}, "tier2": {}, "tier3": {}}
        setup_chart_matrix = {}
        for s_name, df_b in process_excel_sequentially(BOX_RING_DATA_URL):
            s_name_up = str(s_name).upper().strip()
            df_box = df_b.fillna('')
            
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
                                    setup_chart_matrix[(var, pc)] = temp_val

            if 'RING' in s_name_up and 'BOX' in s_name_up:
                tier = "tier1" if "PER" in s_name_up else "tier2"
                target_map = box_matrices[tier]
                
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
                                    if ck not in target_map: target_map[ck] = {}
                                    if or_qty > 0 and p_c == 'OR': target_map[ck]['OR'] = {'qty': or_qty, 'source': s_name}
                                    if ir_qty > 0 and p_c == 'IR': target_map[ck]['IR'] = {'qty': ir_qty, 'source': s_name}
                                    
            elif 'BOX' in s_name_up and 'DAY' in s_name_up:
                tier = "tier3"
                target_map = box_matrices[tier]
                
                for r_idx in range(len(df_box)):
                    for c_idx in range(len(df_box.columns)):
                        cell_val = str(df_box.iloc[r_idx, c_idx]).strip()
                        match = re.search(r'([A-Z0-9/]+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)\s*(\d+)\s*K?', cell_val, re.IGNORECASE)
                        if match:
                            part_type = match.group(1).strip()
                            ir_boxes = int(match.group(2))
                            or_boxes = int(match.group(3))
                            ref_qty = int(match.group(4)) * 1000 if 'K' in cell_val.upper() else int(match.group(4))
                            
                            ir_rpb = ref_qty / ir_boxes if ir_boxes > 0 else 0
                            or_rpb = ref_qty / or_boxes if or_boxes > 0 else 0
                            
                            for p_c in ['IR', 'OR']:
                                clean_keys = get_lookup_variants(part_type, p_c)
                                for ck in clean_keys:
                                    if ck not in target_map: target_map[ck] = {}
                                    if p_c == 'IR' and ('IR' not in target_map[ck] or target_map[ck]['IR']['qty'] <= 0):
                                        if ir_rpb > 0: target_map[ck]['IR'] = {'qty': ir_rpb, 'source': s_name}
                                    if p_c == 'OR' and ('OR' not in target_map[ck] or target_map[ck]['OR']['qty'] <= 0):
                                        if or_rpb > 0: target_map[ck]['OR'] = {'qty': or_rpb, 'source': s_name}

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
                                if ck not in target_map: target_map[ck] = {}
                                if p_c == 'IR' and ('IR' not in target_map[ck] or target_map[ck]['IR']['qty'] <= 0):
                                    fq = safe_float(row_vals[ir_col]) if (ir_col != -1 and ir_col < len(row_vals)) else (safe_float(row_vals[single_rpb_col]) if (single_rpb_col != -1 and single_rpb_col < len(row_vals)) else 0.0)
                                    if fq > 0: target_map[ck]['IR'] = {'qty': fq, 'source': s_name}
                                if p_c == 'OR' and ('OR' not in target_map[ck] or target_map[ck]['OR']['qty'] <= 0):
                                    fq = safe_float(row_vals[or_col]) if (or_col != -1 and or_col < len(row_vals)) else (safe_float(row_vals[single_rpb_col]) if (single_rpb_col != -1 and single_rpb_col < len(row_vals)) else 0.0)
                                    if fq > 0: target_map[ck]['OR'] = {'qty': fq, 'source': s_name}

        box_matrix = {}
        for tier in ["tier3", "tier2", "tier1"]:
            for part_key, part_data in box_matrices[tier].items():
                if part_key not in box_matrix: box_matrix[part_key] = {}
                for p_code, details in part_data.items():
                    if details.get('qty', 0.0) > 0: box_matrix[part_key][p_code] = details

        # -----------------------------------------------------
        # CORRECT BUFFER REDUCTION LOGIC
        # -----------------------------------------------------
        parsed_buffers = {}
        
        # Combine keys to iterate over all possible parts today or tomorrow
        all_parts = set(list(channel_demands_day1.keys()) + list(channel_demands_day2.keys()))
        
        for disp_name in all_parts:
            d1_meta = channel_demands_day1.get(disp_name, {})
            d2_meta = channel_demands_day2.get(disp_name, {})
            ch_raw = d1_meta.get('channel') or d2_meta.get('channel')
            ch_norm = normalize_channel(ch_raw)
            
            for pc in ['IR', 'OR']:
                raw_d1 = float(d1_meta.get(pc, 0.0))
                raw_d2 = float(d2_meta.get(pc, 0.0))
                
                if raw_d1 <= 0 and raw_d2 <= 0: continue
                
                # To accurately convert "1 Day" of buffer to quantities, use the max of D1 and D2 demand.
                daily_rate_ref = max(raw_d1, raw_d2)
                if daily_rate_ref <= 0: continue
                
                buffers_rings = get_all_buffers_for_part(disp_name, pc, ch_norm, payload, box_matrix, daily_rate_ref)
                parsed_buffers[(disp_name, pc, ch_norm)] = buffers_rings
                
                total_avail_rings = sum(buffers_rings.values())
                
                # If there is buffer anywhere (FACE/OD/HT), subtract it strictly from the demand dicts in-place
                # This guarantees that if we have required items further down the stream, we schedule exactly what's needed at HT.
                if total_avail_rings > 0:
                    rem_buf = total_avail_rings
                    
                    if raw_d1 > 0:
                        reduced_d1 = max(0.0, raw_d1 - rem_buf)
                        rem_buf -= (raw_d1 - reduced_d1)
                        channel_demands_day1[disp_name][pc] = reduced_d1
                        
                    if raw_d2 > 0 and rem_buf > 0:
                        reduced_d2 = max(0.0, raw_d2 - rem_buf)
                        rem_buf -= (raw_d2 - reduced_d2)
                        channel_demands_day2[disp_name][pc] = reduced_d2

        # 3. LOAD PRODUCTION MASTER SEQUENTIALLY
        weight_matrix = {}
        furnace_map = {}
        machines_data = {'FACE': {}, 'OD': {}}
        furnace_specs_local = DEFAULT_FURNACES.copy()
        
        for sheet_name, df_m in process_excel_sequentially(SHO_PRODUCTION_URL):
            if 'FURNACE' in str(sheet_name).upper() or 'AICHELIN' in str(sheet_name).upper():
                if 'FLEX' not in str(sheet_name).upper():
                    for r in range(len(df_m)):
                        row = df_m.iloc[r].values
                        f_name = str(row[0]).strip().upper() if len(row) > 0 else ""
                        cap = safe_float(row[1]) if len(row) > 1 else 0.0
                        if f_name and cap > 0 and ('FURNACE' in f_name or 'AICHELIN' in f_name or 'UNITHERM' in f_name):
                            furnace_specs_local[f_name] = cap
            
            if sheet_name == 'WEIGHTS':
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
                                    for ck in clean_keys: weight_matrix[f"{ck}_{part_code}"] = wt_val

            if 'FURNACE' in str(sheet_name).upper() and 'FLEX' in str(sheet_name).upper():
                df_f = df_m
                if len(df_f) > 0:
                    df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                    for idx, r in df_f.iloc[1:].iterrows():
                        comp_level = str(r.iloc[0]).strip() if len(r) > 0 else ""
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

            if sheet_name not in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.', 'Channel Process Flexibility']:
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
                                        for ck in set(clean_keys): machines_data[current_m_type][current_m_num]['rates'][f"{ck}_{pc}"] = rate_rings

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

        # Because we already subtracted buffer above, the raw_d1 inside here is the true reduced demand.
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

            buffer_val = 0.0
            if (disp, pc, ch_norm) in parsed_buffers:
                b_rings = parsed_buffers[(disp, pc, ch_norm)]
                total_rings = sum(b_rings.values())
                demand = max(raw_d1, raw_d2)
                if demand > 0: 
                    buffer_val = total_rings / demand

            item_priority = ch_stats[ch_norm]['score'] - buffer_val

            if net_d1 > 0:
                work_items.append(WorkItem(first_stage, disp, pc, 0, reqs['channel'], net_d1, 0.0, item_priority, routing))
            if net_d2 > 0:
                work_items.append(WorkItem(first_stage, disp, pc, 1, reqs['channel'], net_d2, 0.0, item_priority, routing))

        # LOAD SAVED RESOURCE AND CHANNEL BREAKDOWNS
        db_breakdowns = {}
        channel_bd_map = {}
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT resource, status, start_time, end_time FROM breakdowns WHERE date=?", (payload.date,))
                for row in c.fetchall():
                    r_name = row[0]
                    db_breakdowns[r_name] = {"status": row[1], "start_time": row[2], "end_time": row[3]}
        except Exception:
            pass

        for k, v in db_breakdowns.items():
            norm_k = normalize_channel(k)
            st = v.get("status", "")
            if "Complete" in st:
                channel_bd_map[norm_k] = {"blocked": True}
            else:
                c_st = v.get('start_time', '')
                c_et = v.get('end_time', '')
                if c_st and c_et:
                    channel_bd_map[norm_k] = {
                        "blocked": False,
                        "start": time_str_to_float(c_st),
                        "end": time_str_to_float(c_et)
                    }

        avail_dict = payload.machine_availability if hasattr(payload, 'machine_availability') else {}
        for res in resources:
            bd_info = db_breakdowns.get(res.id)
            if bd_info:
                if "Complete" in bd_info.get("status", ""): 
                    res.blocked = True
                else:
                    st_str = bd_info.get('start_time', '')
                    et_str = bd_info.get('end_time', '')
                    if st_str and et_str:
                        res.has_bd = True
                        res.bd_start = time_str_to_float(st_str)
                        res.bd_end = time_str_to_float(et_str)
            else:
                conf = avail_dict.get(res.id, {})
                if conf:
                    if not conf.get('enabled', True) or conf.get('off_whole_day', False): res.blocked = True
                    else:
                        st_str = conf.get('start_time', '')
                        et_str = conf.get('end_time', '')
                        if st_str and et_str:
                            res.has_bd = True
                            res.bd_start = time_str_to_float(st_str)
                            res.bd_end = time_str_to_float(et_str)

        for item in work_items:
            init_item_resources(item, resources, furnace_map, weight_matrix, furnace_specs_local)

        # 1. LOOK-AHEAD BATCH MERGING
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
                if (item2.day_idx == 1 and item2.disp == item1.disp and item2.pc == item1.pc and item2.stage == item1.stage and item2.channel == item1.channel and item2.qty > 0.01):
                    est_time2 = (item2.qty * weight_dummy) / rate_dummy if res_dummy.type == 'HT' else item2.qty / rate_dummy
                    if est_time1 < merge_thresh or est_time2 < merge_thresh:
                        item1.qty += item2.qty
                        item2.qty = 0.0
                    break

        # SIMULATION LOOP
        for target_day in [-1, 0, 1]:
            current_max_time = 24.0 
            for r in resources:
                r.max_time = current_max_time
                if r.ready_time < current_max_time: r.blocked = False
                    
            while True:
                active_items = [i for i in work_items if i.qty > 0.01 and i.ready_time < current_max_time and i.day_idx == target_day]
                
                filtered_active_items = []
                for i in active_items:
                    norm_ch = normalize_channel(i.channel)
                    if norm_ch in channel_bd_map and channel_bd_map[norm_ch].get("blocked"):
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
                                if prev_temp is not None and curr_temp is not None and prev_temp != curr_temp: setup = 1.5
                                else: setup = 0.5
                        else:
                            setup = 2.0
                            if res.last_fam == item.disp: setup = 0.0 if res.last_pc == item.pc else 2.0 
                        
                        start_time = max(res.ready_time + setup, item.ready_time)
                        
                        if res.type == 'HT':
                            weight = item.rates[res.id][1]
                            est_req_time = (item.qty * weight) / rate_or_cap
                        else:
                            est_req_time = item.qty / rate_or_cap

                        if res.has_bd and start_time < res.bd_end and (start_time + est_req_time) > res.bd_start:
                            start_time = max(start_time, res.bd_end)

                        norm_ch = normalize_channel(item.channel)
                        if norm_ch in channel_bd_map and not channel_bd_map[norm_ch].get("blocked"):
                            ch_bds = channel_bd_map[norm_ch]["start"]
                            ch_bde = channel_bd_map[norm_ch]["end"]
                            if start_time < ch_bde and (start_time + est_req_time) > ch_bds:
                                start_time = max(start_time, ch_bde)
                                
                        if start_time >= res.max_time: continue
                        
                        is_continuation = (res.last_fam == item.disp and res.last_pc == item.pc and start_time <= res.ready_time + 0.01)
                        gap = max(0.0, item.ready_time - (res.ready_time + setup))
                        req_time = (item.qty * item.rates[res.id][1]) / rate_or_cap if res.type == 'HT' else item.qty / rate_or_cap
                        time_available = res.max_time - start_time
                        
                        needs_split = 1 if req_time > time_available else 0
                        key = (needs_split, start_time, item.day_idx, gap, -item.priority)
                        
                        if key < best_key:
                            best_key = key
                            best_pair = (res, item, start_time, setup, rate_or_cap, is_continuation)
                            
                if not best_pair: break
                    
                res, item, start_time, setup, rate_or_cap, is_continuation = best_pair
                chunk_qty = item.qty
                actual_time = (chunk_qty * item.rates[res.id][1]) / rate_or_cap if res.type == 'HT' else chunk_qty / rate_or_cap

                if start_time < 24.0 and (start_time + actual_time) > 24.0:
                    max_allowed_time = min(6.0, 30.0 - start_time)
                    if actual_time > max_allowed_time:
                        actual_time = max_allowed_time
                        if res.type == 'HT': chunk_qty = (actual_time * rate_or_cap) / item.rates[res.id][1]
                        else: chunk_qty = actual_time * rate_or_cap
                
                if res.type == 'HT':
                    res_ready_time = start_time + actual_time + 0.5
                    out_time = start_time + actual_time + 3.5
                    display_rate = f"{round((chunk_qty * item.rates[res.id][1]), 1)} kg"
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
            elif any(r.type == item.stage for r in resources) and len(item.valid_resources) == 0 and not (not item.routing or item.stage not in item.routing): assigned_reason = "Machine Rate Not Available"
            elif not item.routing or item.stage not in item.routing: assigned_reason = "Missing Routing"
            elif not any(r.type == item.stage for r in resources): assigned_reason = "No Compatible Machine"
            elif item.ready_time < 24.0 and len(item.valid_resources) > 0: assigned_reason = "Insufficient Capacity"
            elif (item.routing and item.stage in item.routing and any(u.disp == item.disp and u.pc == item.pc and u.day_idx == item.day_idx and u.stage in item.routing[:item.routing.index(item.stage)] and u.qty > 0.01 for u in work_items)): assigned_reason = "Previous Process Pending"
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
            
            if item.day_idx == -1: day_label = "WIP"
            else: day_label = "Day 2" if item.day_idx == 1 else "Day 1"
                
            unscheduled.append({
                "stage": item.stage, 
                "part": f"{item.disp} {item.pc} ({day_label})", 
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
            elif r.type == 'HT': furnaces_formatted.append({"furnace": r.id, "capacity": f"Total Cap: {int(r.capacity_info)} kg/hr", "rows": r.rows})
            
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
            
        snapshot = {
            "monthly_data": monthly_data.get(month_str, {}),
            "plant_state": end_state
        }
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
