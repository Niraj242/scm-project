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

EXCEL_CACHE = {}
CACHE_TTL = 3600  

PARSED_MASTER_DATA = {
    "box_matrix": ({}, 0),  
    "production": ({}, {}, {}, {}, 0) 
}

MONTHLY_FILE = "monthly_tracking.json"
SAVED_PLAN_FILE = "saved_plan.json"

HARDCODED_PROCESS_FLEXIBILITY = {
    "T4": {
        "IR": {"FACE": True, "OD": False},
        "OR": {"FACE": True, "OD": True}
    }
}

# --- GLOBAL MEMOIZATION FOR SPEED ---
RATE_CACHE = {}
WEIGHT_CACHE = {}
FURNACE_CACHE = {}
FURNACE_SPECS = {} # Issue 12: Will be loaded dynamically now

def load_monthly_tracking():
    if os.path.exists(MONTHLY_FILE):
        try:
            with open(MONTHLY_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_monthly_tracking(data):
    try:
        with open(MONTHLY_FILE, 'w') as f: json.dump(data, f)
    except Exception as e:
        print(f"Error saving monthly tracking: {e}")

def load_saved_plan():
    if os.path.exists(SAVED_PLAN_FILE):
        try:
            with open(SAVED_PLAN_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]
    machine_availability: Dict[str, Any] = {}

class SavePlanRequest(BaseModel):
    date: str
    plan: Dict[str, Any]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

@router.get("/api/monthly_tracking")
def get_monthly_tracking():
    return load_monthly_tracking()

@router.post("/api/save_plan")
def save_plan(payload: SavePlanRequest):
    # Issue 7: Save Daily Plan Implemented
    try:
        with open(SAVED_PLAN_FILE, "w") as f:
            json.dump(payload.dict(), f)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

def normalize_channel(ch_str):
    ch = str(ch_str).strip().upper()
    ch = ch.replace("CH", "").replace("CHANNEL", "").replace(" ", "").strip()
    return ch

def get_process_flexibility(channel_norm, p_code, flex_map):
    for hard_ch, flex_data in HARDCODED_PROCESS_FLEXIBILITY.items():
        if hard_ch.replace(" ", "") in channel_norm or channel_norm in hard_ch.replace(" ", ""):
            if p_code in flex_data:
                return flex_data[p_code]
    return flex_map.get(channel_norm, {}).get(p_code, {'FACE': True, 'OD': True})

def is_invalid_part(raw_text):
    if pd.isna(raw_text) or not raw_text: return True
    t = str(raw_text).upper()
    invalid_keywords = ["PROJECTED", "PLAN", "QTY", "HRS", "DAY", "NAN", "NONE", "UNKNOWN", "TYPE", "WIP", "MTD", "ASKING", "TOTAL"]
    for k in invalid_keywords:
        if k in t: return True
    return False

def get_lookup_variants(raw_text, p_code=None):
    # Issue 1: "CHECK PART NUMBER" BUG Fix - SAFE FUZZY MATCHER
    if is_invalid_part(raw_text): return []
    t = str(raw_text).upper().strip()
    
    # Strip hidden chars and zero-width spaces causing matching failures
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

    # Safely strip exact suffixes only (Prevents 3212 matching 33212)
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
    
    # Clean leading stage artifacts if present
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
    # Strip stage artifacts for clean display
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
            h, m = str(t_str).replace('(+1)', '').strip().split(':')
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
            return df_dict, [f"Loaded {file_label} from ultra-fast cache."]
    try:
        # Issue 4: PERFORMANCE - Use cache properly and high timeout for big sheets
        resp = requests.get(url, timeout=180)
        if resp.status_code != 200: 
            raise Exception(f"HTTP {resp.status_code}")
        content = io.BytesIO(resp.content)
        df_dict = pd.read_excel(content, sheet_name=None, header=None)
        EXCEL_CACHE[url] = (now, df_dict)
        return df_dict, logs
    except Exception as e:
        raise Exception(f"Failed to load {file_label} Excel sheet: {str(e)}")

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

def get_furnaces_for_part(display_name, p_code, furnace_map):
    key = (display_name, p_code)
    if key in FURNACE_CACHE: return FURNACE_CACHE[key]
    
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if f"{var}_{p_code}" in furnace_map: 
            FURNACE_CACHE[key] = furnace_map[f"{var}_{p_code}"]
            return FURNACE_CACHE[key]
            
    default_f = list(FURNACE_SPECS.keys())
    FURNACE_CACHE[key] = default_f
    return default_f

def get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs=None, logged_set=None):
    variants = get_lookup_variants(display_name, p_code)
    for var in variants:
        if var in box_matrix and p_code in box_matrix[var]: 
            qty = box_matrix[var][p_code]['qty']
            source = box_matrix[var][p_code]['source']
            return qty, source, var
    return 0.0, "NONE", variants[0] if variants else display_name

def get_box_for_part(display_name, p_code, box_matrix, debug_logs=None, logged_set=None):
    qty, _, _ = get_box_for_part_detailed(display_name, p_code, box_matrix, debug_logs, logged_set)
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
    def __init__(self, stage, disp, pc, day_idx, channel, qty, ready_time, priority, flex):
        self.stage = stage
        self.disp = disp
        self.pc = pc
        self.day_idx = day_idx
        self.channel = channel
        self.qty = qty
        self.ready_time = ready_time
        self.priority = priority
        self.flex = flex

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

def parse_master_production_data():
    sheets_prod, _ = get_cached_excel_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
    machines_data = {'FACE': {}, 'OD': {}}
    
    # Issue 12: MACHINE AVAILABILITY - Load furnaces dynamically
    global FURNACE_SPECS
    FURNACE_SPECS.clear()

    if sheets_prod:
        for sheet_name, df_m in sheets_prod.items():
            if 'FURNACE' in str(sheet_name).upper() or 'AICHELIN' in str(sheet_name).upper():
                for r in range(len(df_m)):
                    row = df_m.iloc[r].values
                    f_name = str(row[0]).strip().upper() if len(row) > 0 else ""
                    cap = safe_float(row[1]) if len(row) > 1 else 0.0
                    if f_name and cap > 0 and ('FURNACE' in f_name or 'AICHELIN' in f_name or 'UNITHERM' in f_name):
                        FURNACE_SPECS[f_name] = cap

            if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.', 'Channel Process Flexibility']: continue
            str_matrix = df_m.fillna('').astype(str).values
            for r in range(str_matrix.shape[0]):
                row_text = " ".join(str_matrix[r]).upper()
                if 'MACHINE' in row_text or 'M/C' in row_text:
                    cells = [c.strip() for c in str_matrix[r] if c.strip()]
                    m_cand = cells[1] if len(cells) > 1 else None
                    if m_cand and m_cand not in ["MACHINE", "M/C"]:
                        if "FACE" in row_text or "DDS" in m_cand.upper() or "BG" in m_cand.upper():
                            machines_data['FACE'][m_cand] = True
                        elif "OD" in row_text or "CL" in m_cand.upper() or "CELL" in m_cand.upper() or "+" in m_cand:
                            machines_data['OD'][m_cand] = True
                            
    # Fallback if no furnace sheet is found properly
    if not FURNACE_SPECS:
        FURNACE_SPECS = {
            "AICHELIN.(896)": 350.0, "CASTLINK FURNACE( 1018 )": 250.0,
            "ROLLER FURNACE ( 148 )": 250.0, "SIMPLICITY FURNACE(1238)": 180.0,
            "BIRLEC FURNACE   ( 1158 )": 170.0, "SHOEI FURNACE    ( 1062 )": 350.0,
            "AICHELIN UNITHERM ( 2033 )": 250.0
        }
    return machines_data

@router.get("/api/machines")
def get_machines_list():
    try:
        data = parse_master_production_data()
        all_machines = list(data['FACE'].keys()) + list(data['OD'].keys()) + list(FURNACE_SPECS.keys())
        seen = set()
        unique_machines = [x for x in all_machines if not (x in seen or seen.add(x))]
        return {"status": "success", "data": unique_machines}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/api/summary")
def generate_summary(payload: ScheduleRequest):
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day_1 = req_date + timedelta(days=1)
        month_str = req_date.strftime("%Y-%m")
        monthly_data = load_monthly_tracking()
        if month_str not in monthly_data:
            monthly_data[month_str] = {}
            
        sheets_zero, _ = get_cached_excel_sheets(ZEROSET_URL, "ZEROSET")
        summary_list = []
        channel_demands_day1 = {}

        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                sheet_str_upper = str(sheet_name).strip().upper()
                ir_multiplier = 2 if any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB"]) else 1
                is_trb_hub = any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB", "TRB", "T 1", "T 2", "T 3", "T 4", "T 5", "T 6", "T 7", "T 8", "T 9", "T10", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"])
                
                r_idx, type_col_idx, mv_col_idx, c1_col = None, None, None, None
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
                                if val in ["MF", "PART NO", "BRG NO"]:
                                    type_col_idx = j; break
                                    
                    if mv_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["MV", "FV", "VAR", "VARIANT"]:
                                mv_col_idx = j; break
                                
                    if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                        r_idx = i
                        # Issue 8: MONTHLY REQUIREMENT - strictly digits representing 1-31 dates
                        for j, val in enumerate(df_zero.iloc[i].values):
                            if is_target_date(val, day_1): c1_col = j
                            
                            s_val = str(val).strip()
                            if s_val.isdigit() and 1 <= int(s_val) <= 31:
                                monthly_cols.append(j)
                    
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    last_mf = ""
                    for idx in range(r_idx + 1, len(df_zero)):
                        mf_val = str(df_zero.iloc[idx, type_col_idx]).strip() if type_col_idx is not None else ""
                        if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                        raw_t = (str(df_zero.iloc[idx, mv_col_idx]).strip() if mv_col_idx is not None else "") if is_trb_hub else last_mf
                        if not raw_t or raw_t in ["NAN", "NONE"]: raw_t = last_mf
                        if is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        if display_name not in monthly_data[month_str]:
                            monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": str(sheet_name).strip()}
                        
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0:
                            monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1: 
                                channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1 * ir_multiplier)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)

        saved_plan = load_saved_plan()
        t_prod_map = {}
        if saved_plan.get("date") == payload.date:
            for s_key in ["od_grinding", "face_grinding", "heat_treatment"]:
                for m in saved_plan.get("plan", {}).get(s_key, []):
                    for r in m.get("rows", []):
                        if r.get("is_terminal"):
                            p = r.get("part", "").split("-")[0].split(" ")[0]
                            t_prod_map[p] = t_prod_map.get(p, 0) + safe_float(r.get("qty", 0))

        for disp_name, data in monthly_data.get(month_str, {}).items():
            ch = data.get("channel", "Unknown")
            mo_req = data.get("total_req", 0)
            mtd_prod = data.get("produced", 0)
            d1_data = channel_demands_day1.get(disp_name, {})
            d1_req = max(d1_data.get("IR", 0), d1_data.get("OR", 0))
            t_prod = t_prod_map.get(disp_name, 0)
            
            summary_list.append({
                "type": disp_name, "channel": ch, "monthly_req": int(mo_req), "today_req": int(d1_req), "today_prod": int(t_prod),
                "mtd_prod": int(mtd_prod), "balance": int(mo_req - mtd_prod),
                "remaining_pct": round(((mo_req - mtd_prod) / mo_req * 100), 1) if mo_req > 0 else 0,
                "difference": int(t_prod - d1_req)
            })
            
        return {"status": "success", "data": summary_list}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    unscheduled = []
    logged_rpb = set()
    
    global RATE_CACHE, WEIGHT_CACHE, FURNACE_CACHE
    RATE_CACHE = {}
    WEIGHT_CACHE = {}
    FURNACE_CACHE = {}
    
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day_1 = req_date + timedelta(days=1)
        day_2 = req_date + timedelta(days=2)
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
                ir_multiplier = 2 if any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB"]) else 1
                is_trb_hub = any(k in sheet_str_upper for k in ["HUB", "TBHU", "THUB", "TRB", "T 1", "T 2", "T 3", "T 4", "T 5", "T 6", "T 7", "T 8", "T 9", "T10", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"])
                
                r_idx, type_col_idx, mv_col_idx = None, None, None
                c1_col, c2_col = None, None
                monthly_cols = []
                
                for i in range(min(25, len(df_zero))):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[i].values]
                    row_joined = " ".join(row_strs)
                    
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val == "TYPE" or "TYPE " in val or " TYPE" in val: type_col_idx = j; break
                        if type_col_idx is None:
                            for j, val in enumerate(row_strs):
                                if val in ["MF", "PART NO", "BRG NO"]: type_col_idx = j; break
                                    
                    if mv_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["MV", "FV", "VAR", "VARIANT"]: mv_col_idx = j; break
                                
                    if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                        r_idx = i
                        # Issue 8: Month column check logic
                        for j, val in enumerate(df_zero.iloc[i].values):
                            if is_target_date(val, day_1): c1_col = j
                            if is_target_date(val, day_2): c2_col = j
                            
                            s_val = str(val).strip()
                            if s_val.isdigit() and 1 <= int(s_val) <= 31:
                                monthly_cols.append(j)
                        
                    if r_idx is not None and type_col_idx is not None: break
                    if r_idx is not None and type_col_idx is not None:
                    last_mf = ""
                    for idx in range(r_idx + 1, len(df_zero)):
                        mf_val = str(df_zero.iloc[idx, type_col_idx]).strip() if type_col_idx is not None else ""
                        if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                        raw_t = (str(df_zero.iloc[idx, mv_col_idx]).strip() if mv_col_idx is not None else "") if is_trb_hub else last_mf
                        if not raw_t or raw_t in ["NAN", "NONE"]: raw_t = last_mf
                        if is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        if display_name not in monthly_data[month_str]: monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": str(sheet_name).strip()}
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0: monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2_col]) if c2_col is not None else 0.0
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1: channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1 * ir_multiplier)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)
                        if r2 > 0:
                            if display_name not in channel_demands_day2: channel_demands_day2[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day2[display_name]['IR'] = max(channel_demands_day2[display_name]['IR'], r2 * ir_multiplier)
                            channel_demands_day2[display_name]['OR'] = max(channel_demands_day2[display_name]['OR'], r2)
        del sheets_zero

        box_matrix = {}
        sheets_box, _ = get_cached_excel_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        box_cache_ts = EXCEL_CACHE.get(BOX_RING_DATA_URL, (0, None))[0]
        
        if PARSED_MASTER_DATA["box_matrix"][1] == box_cache_ts:
            box_matrix = PARSED_MASTER_DATA["box_matrix"][0]
        elif sheets_box:
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
                                        fq = 0.0
                                        if ir_col != -1: fq = safe_float(row_vals[ir_col])
                                        elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                        if fq > 0: box_matrix[ck]['IR'] = {'qty': fq, 'source': s_name}
                                    if p_c == 'OR' and ('OR' not in box_matrix[ck] or box_matrix[ck]['OR']['qty'] <= 0):
                                        fq = 0.0
                                        if or_col != -1: fq = safe_float(row_vals[or_col])
                                        elif single_rpb_col != -1: fq = safe_float(row_vals[single_rpb_col])
                                        if fq > 0: box_matrix[ck]['OR'] = {'qty': fq, 'source': s_name}
            PARSED_MASTER_DATA["box_matrix"] = (box_matrix, box_cache_ts)
        del sheets_box

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
                        header_idx = i; break
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
                            
                            face_req = True; od_req = True
                            if face_col != -1 and str(df_flex.iloc[idx, face_col]).strip().upper() == "NO": face_req = False
                            if od_col != -1 and str(df_flex.iloc[idx, od_col]).strip().upper() == "NO": od_req = False
                                
                            if p_code:
                                if c_norm not in channel_flex_map: channel_flex_map[c_norm] = {}
                                channel_flex_map[c_norm][p_code] = {'FACE': face_req, 'OD': od_req}

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
                            else: matched_fn = next((k for k in FURNACE_SPECS.keys() if fn[:4] in k.upper()), None)
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
                                    if comb_val and not is_invalid_part(comb_val): clean_keys.extend(get_lookup_variants(comb_val, pc))
                                    if not clean_keys: continue
                                        
                                    rate_rings = 0.0
                                    rpb = get_box_for_part(raw_t, pc, box_matrix, None, None)
                                    if rpb_idx != -1 and safe_float(row_vals[rpb_idx]) > 0: rpb = safe_float(row_vals[rpb_idx])
                                    if ring_hr_idx != -1 and safe_float(row_vals[ring_hr_idx]) > 0: rate_rings = safe_float(row_vals[ring_hr_idx])
                                    elif box_hr_idx != -1 and safe_float(row_vals[box_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[box_hr_idx]) * rpb
                                    elif std_hr_idx != -1 and safe_float(row_vals[std_hr_idx]) > 0 and rpb > 0: rate_rings = safe_float(row_vals[std_hr_idx]) * rpb
                                        
                                    if rate_rings > 0:
                                        for ck in set(clean_keys): machines_data[current_m_type][current_m_num]['rates'][f"{ck}_{pc}"] = rate_rings
                                            
            PARSED_MASTER_DATA["production"] = (weight_matrix, furnace_map, machines_data, channel_flex_map, prod_cache_ts)
        del sheets_prod

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
                    if display_name not in buffers_by_fam: buffers_by_fam[display_name] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[display_name][stage][sub_ring_type] += buf_val

        ch_stats = {}
        fam_to_ch = {}
        for d_dict in [channel_demands_day1, channel_demands_day2]:
            for fam, data in d_dict.items():
                ch = normalize_channel(data['channel'])
                fam_to_ch[fam] = ch
                if ch not in ch_stats: ch_stats[ch] = {'demand': 0.0, 'buffer': 0.0}
                ch_stats[ch]['demand'] += data.get('IR', 0) + data.get('OR', 0)
                
        for fam, stg_data in buffers_by_fam.items():
            ch = fam_to_ch.get(fam, "UNKNOWN")
            if ch not in ch_stats: ch_stats[ch] = {'demand': 0.0, 'buffer': 0.0}
            for stg, side_data in stg_data.items(): ch_stats[ch]['buffer'] += side_data.get('IR', 0) + side_data.get('OR', 0)
                
        for ch, stats in ch_stats.items(): stats['score'] = (stats['demand'] + 1.0) / (stats['buffer'] + 1.0)

        def process_requirements_for_day(demands, in_out_buffers):
            f_req, o_req, h_req = {}, {}, {}
            for display_name, data in demands.items():
                ch_norm = normalize_channel(data['channel'])
                for side in ['IR', 'OR']:
                    req_rings = data[side]
                    if req_rings <= 0: continue
                    rpb = get_box_for_part(display_name, side, box_matrix)
                    flex = get_process_flexibility(ch_norm, side, channel_flex_map)
                    req_face = flex['FACE']; req_od = flex['OD']
                    
                    def apply_buf(stage, base_rings, rpb_rate):
                        raw_buf = in_out_buffers.get(display_name, {}).get(stage, {}).get(side, 0)
                        if payload.unit_mode == 'Days': avail_buf_rings = raw_buf * base_rings
                        elif payload.unit_mode == 'Boxes': avail_buf_rings = raw_buf * (rpb_rate if rpb_rate > 0 else 100)
                        else: avail_buf_rings = raw_buf 
                        if avail_buf_rings >= base_rings: used_rings, rem_rings = base_rings, avail_buf_rings - base_rings
                        else: used_rings, rem_rings = avail_buf_rings, 0.0
                        if display_name in in_out_buffers:
                            if payload.unit_mode == 'Days': new_raw = (rem_rings / base_rings) if base_rings > 0 else 0
                            elif payload.unit_mode == 'Boxes': new_raw = rem_rings / (rpb_rate if rpb_rate > 0 else 100)
                            else: new_raw = rem_rings
                            in_out_buffers[display_name][stage][side] = new_raw
                        return used_rings

                    current_req = req_rings
                    used_ch_buf = apply_buf('CH', current_req, rpb)
                    current_req = max(0.0, current_req - used_ch_buf)
                    if req_od:
                        if current_req > 0:
                            if display_name not in o_req: o_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            o_req[display_name][side] += current_req
                        used_od_buf = apply_buf('OD', current_req, rpb)
                        current_req = max(0.0, current_req - used_od_buf)
                    if req_face:
                        if current_req > 0:
                            if display_name not in f_req: f_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                            f_req[display_name][side] += current_req
                        used_face_buf = apply_buf('FACE', current_req, rpb)
                        current_req = max(0.0, current_req - used_face_buf)
                    if current_req > 0:
                        if display_name not in h_req: h_req[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': data['channel']}
                        h_req[display_name][side] += current_req
            return f_req, o_req, h_req

        face_req_d1, od_req_d1, ht_req_d1 = process_requirements_for_day(channel_demands_day1, buffers_by_fam)
        face_req_d2, od_req_d2, ht_req_d2 = process_requirements_for_day(channel_demands_day2, buffers_by_fam)

        work_items = []
        for day_idx, demands, f_req, o_req, h_req in [(0, channel_demands_day1, face_req_d1, od_req_d1, ht_req_d1), (1, channel_demands_day2, face_req_d2, od_req_d2, ht_req_d2)]:
            for display_name, data in demands.items():
                ch_norm = normalize_channel(data['channel'])
                for p_code in ['IR', 'OR']:
                    flex = get_process_flexibility(ch_norm, p_code, channel_flex_map)
                    req_o = o_req.get(display_name, {}).get(p_code, 0.0) if display_name in o_req else 0.0
                    req_f = f_req.get(display_name, {}).get(p_code, 0.0) if display_name in f_req else 0.0
                    req_h = h_req.get(display_name, {}).get(p_code, 0.0) if display_name in h_req else 0.0
                    
                    init_f = req_f - req_h if flex['FACE'] else 0.0
                    if flex['OD']: init_o = req_o - req_f if flex['FACE'] else req_o - req_h
                    else: init_o = 0.0
                    
                    init_h = req_h
                    ch_score = ch_stats.get(ch_norm, {}).get('score', 0.0)
                    if init_h > 0: work_items.append(WorkItem('HT', display_name, p_code, day_idx, data['channel'], init_h, 0.0, ch_score, flex))
                    if init_f > 0: work_items.append(WorkItem('FACE', display_name, p_code, day_idx, data['channel'], init_f, 0.0, ch_score, flex))
                    if init_o > 0: work_items.append(WorkItem('OD', display_name, p_code, day_idx, data['channel'], init_o, 0.0, ch_score, flex))

        resources = []
        for f_name, cap in FURNACE_SPECS.items(): resources.append(Resource(f_name, 'HT', cap))
        for m_num, m_info in machines_data.get('FACE', {}).items(): resources.append(Resource(m_num, 'FACE', m_info.get('rates', {})))
        for m_num, m_info in machines_data.get('OD', {}).items(): resources.append(Resource(m_num, 'OD', m_info.get('rates', {})))

        saved_plan = load_saved_plan()
        if saved_plan and saved_plan.get("date"):
            try:
                saved_dt = datetime.strptime(saved_plan.get("date"), "%Y-%m-%d")
                if (req_date - saved_dt).days == 1:
                    plan_data = saved_plan.get("plan", {})
                    for stage, m_list in plan_data.items():
                        for m_data in m_list:
                            m_id = m_data.get("machine") or m_data.get("furnace")
                            rows = m_data.get("rows", [])
                            if not rows: continue
                            last_timing = rows[-1].get("timing", "")
                            if "-" in last_timing:
                                end_t_str = last_timing.split("-")[1].strip()
                                if "(+1)" in end_t_str:
                                    rel_today = time_str_to_float(end_t_str)
                                    for r in resources:
                                        if r.id == m_id:
                                            r.ready_time = max(r.ready_time, rel_today)
                                            part_raw = rows[-1].get("part", "")
                                            parts_split = part_raw.split(" ")
                                            if len(parts_split) >= 2:
                                                r.last_fam = parts_split[0]
                                                r.last_pc = parts_split[1].replace("(D1+D2)", "").replace("(D2)", "").replace("(D1)", "").strip()
            except: pass

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

        # Issue 5 & 6: Strict Day Priority
        for target_day in [0, 1]:
            while True:
                active_items = [i for i in work_items if i.qty > 0.01 and i.ready_time < 24.0 and i.day_idx == target_day]
                if not active_items: 
                    break 
                    
                best_pair = None
                best_key = (float('inf'), float('inf'), float('-inf'))
                for item in active_items:
                    for res in resources:
                        if res.blocked or res.ready_time >= getattr(res, 'max_time', 24.0): continue
                        if res.type != item.stage: continue
                        rate_or_cap = 0.0
                        if res.type == 'HT':
                            valid_furnaces = get_furnaces_for_part(item.disp, item.pc, furnace_map)
                            if res.id not in valid_furnaces: continue
                            weight = get_weight_for_part(item.disp, item.pc, weight_matrix)
                            if not weight: continue 
                            rate_or_cap = res.capacity_info
                        else:
                            rate_or_cap = get_rate_for_part(item.disp, item.pc, res.capacity_info, res.id)
                            if rate_or_cap <= 0: continue
                            
                        setup = 0.5 if res.type == 'HT' else 2.0
                        if res.last_fam == item.disp: setup = 0.0 if res.last_pc == item.pc else 2.0 
                        
                        start_time = max(res.ready_time + setup, item.ready_time)
                        if start_time >= getattr(res, 'max_time', 24.0): continue
                        is_continuation = (res.last_fam == item.disp and res.last_pc == item.pc and start_time <= res.ready_time + 0.01)
                        
                        key = (start_time, -item.priority)
                        if key < best_key:
                            best_key = key
                            best_pair = (res, item, start_time, setup, rate_or_cap, is_continuation)
                            
                if not best_pair: 
                    for i in active_items: i.qty = 0
                    break
                    
                res, item, start_time, setup, rate_or_cap, is_continuation = best_pair
                
                if res.type == 'HT':
                    weight = get_weight_for_part(item.disp, item.pc, weight_matrix)
                    actual_time = (item.qty * weight) / rate_or_cap
                    chunk_qty = item.qty
                    
                    if res.has_bd and start_time < res.bd_end and (start_time + actual_time) > res.bd_start:
                        actual_time += (res.bd_end - max(start_time, res.bd_start))
                        
                    res_ready_time = start_time + actual_time + 0.5
                    out_time = start_time + actual_time + 3.5
                    display_rate = f"{round((item.qty * weight), 1)} kg"
                    if item.disp in monthly_data.get(month_str, {}): monthly_data[month_str][item.disp]["produced"] += chunk_qty
                else:
                    chunk_qty = item.qty
                    if chunk_qty <= 0.01: res.blocked = True; continue
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
                if res.ready_time >= getattr(res, 'max_time', 24.0): res.blocked = True
                item.qty -= chunk_qty
                
                next_stage = None
                if res.type == 'HT': next_stage = 'FACE' if item.flex['FACE'] else ('OD' if item.flex['OD'] else None)
                elif res.type == 'FACE': next_stage = 'OD' if item.flex['OD'] else None
                if next_stage: work_items.append(WorkItem(next_stage, item.disp, item.pc, item.day_idx, item.channel, chunk_qty, out_time, item.priority, item.flex))
                
                rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix, debug_logs, logged_rpb)
                can_merge = (res.type != 'HT' and res.rows and is_same_item and is_continuation)
                if can_merge:
                    last_row = res.rows[-1]
                    old_qty = int(float(last_row["qty"]))
                    new_qty = old_qty + int(chunk_qty)
                    last_row["qty"] = str(new_qty)
                    if "(D1+D2)" not in last_row["part"]: last_row["part"] = last_row["part"].replace(" (D2)", "").replace(" (D1)", "").strip() + " (D1+D2)"
                    old_start = last_row["timing"].split('-')[0]
                    new_end = format_time(out_time if res.type == 'HT' else res_ready_time)
                    last_row["timing"] = f"{old_start}-{new_end}"
                    display_val = f"{math.ceil(new_qty / rpb)} Boxes" if rpb > 0 else f"{int(new_qty)} Rings (Q)"
                    if res.type != 'HT': last_row["std_box"] = display_val
                else:
                    display_val = f"{math.ceil(chunk_qty / rpb)} Boxes" if rpb > 0 else f"{int(chunk_qty)} Rings (Q)"
                    timing_display = f"{format_time(start_time)}-{format_time(out_time if res.type == 'HT' else res_ready_time)}"
                    day_label = " (D2)" if item.day_idx == 1 else " (D1)"
                    
                    is_terminal = False
                    if res.type == 'OD': is_terminal = True
                    elif res.type == 'FACE' and not item.flex['OD']: is_terminal = True
                    elif res.type == 'HT' and not item.flex['FACE'] and not item.flex['OD']: is_terminal = True
                    
                    if res.type == 'HT':
                        res.rows.append({"part": f"{item.disp}-{item.pc}{day_label}", "qty": str(int(chunk_qty)), "cha": item.channel, "rate": display_rate, "timing": timing_display, "alert": False, "is_terminal": is_terminal})
                    else:
                        res.rows.append({"part": f"{item.disp} {item.pc}{day_label}", "qty": str(int(chunk_qty)), "std_box": display_val, "timing": timing_display, "p_2nd": "1" if len(res.rows) == 0 else "", "p_3rd": "1" if len(res.rows) == 1 else "", "alert": False, "p_label": f"P{len(res.rows) + 1}", "is_terminal": is_terminal})

        for item in work_items:
            if item.qty <= 0.01: continue
            rpb, _, _ = get_box_for_part_detailed(item.disp, item.pc, box_matrix, debug_logs, logged_rpb)
            missed_val = f"{int(item.qty)} Rings (Q)" if rpb <= 0 else f"{math.ceil(item.qty / rpb)} Boxes"
            day_label = "Day 2" if item.day_idx == 1 else "Day 1"
            reason = "Capacity Exceeded"
            if item.stage == 'HT':
                if not get_weight_for_part(item.disp, item.pc, weight_matrix): reason = "Missing Weight"
                else:
                    valid_f = get_furnaces_for_part(item.disp, item.pc, furnace_map)
                    if not valid_f: reason = "Missing Machine Rate"
                    elif all(r.blocked for r in resources if r.id in valid_f): reason = "Exceeds Planning Window"
            else:
                rates_found = any(get_rate_for_part(item.disp, item.pc, r.capacity_info, r.id) > 0 for r in resources if r.type == item.stage)
                if not rates_found: reason = "Missing Machine Rate (Check Part Number)"
                elif all(r.blocked for r in resources if r.type == item.stage and get_rate_for_part(item.disp, item.pc, r.capacity_info, r.id) > 0): reason = "Exceeds Planning Window"
            unscheduled.append({"stage": item.stage, "part": f"{item.disp} {item.pc} ({day_label})", "missed_boxes": f"{missed_val} - {reason}"})

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

        save_monthly_tracking(monthly_data)
        return {"status": "success", "debug_logs": debug_logs, "data": {"face_grinding": final_face, "od_grinding": final_od, "heat_treatment": furnaces_formatted, "unscheduled": unscheduled, "summary": summary_list}}
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs + [f"CRITICAL ERROR: {traceback.format_exc()}"], "detail": str(e)}
