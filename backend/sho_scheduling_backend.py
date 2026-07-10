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
        self.capacity_info = capacity_info
        self.ready_time = 0.0
        self.rows = []
        self.last_fam = ""
        self.has_bd = False
        self.bd_start = 0.0
        self.bd_end = 0.0

def parse_master_production_data():
    global FURNACE_SPECS
    now = time.time()
    cache_ts = EXCEL_CACHE.get(SHO_PRODUCTION_URL, (0, None))[0]
    if PARSED_MASTER_DATA["production"][4] == cache_ts and cache_ts > 0:
        return PARSED_MASTER_DATA["production"]

    sheets_prod, _ = get_cached_excel_sheets(SHO_PRODUCTION_URL, "MASTER")
    if not sheets_prod: return {'FACE': {}, 'OD': {}, 'FURNACE': {}, 'WEIGHTS': {}, 'PROCESS_FLEX': {}}
    
    face_rates, od_rates, furnace_map, weights_map, flex_map = {}, {}, {}, {}, {}
    
    for sheet_name, df_p in sheets_prod.items():
        sn_upper = str(sheet_name).strip().upper()
        if "FACE" in sn_upper: target_dict = face_rates
        elif "OD" in sn_upper: target_dict = od_rates
        elif "HT" in sn_upper or "HEAT" in sn_upper: target_dict = furnace_map
        else: continue
        
        part_col, pc_col, hr_col, weight_col, furn_col = -1, -1, -1, -1, -1
        mach_cols = {}
        for c in range(len(df_p.columns)):
            col_val = str(df_p.iloc[0, c]).strip().upper()
            if col_val == "PART NO": part_col = c
            elif col_val in ["IR / OR", "P/C"]: pc_col = c
            elif col_val == "WEIGHT(KG)": weight_col = c
            elif col_val == "HEAT TREATMENT FURNACE": furn_col = c
            elif col_val == "HR/RINGS": hr_col = c
            elif "MACHINE" in sn_upper and col_val not in ["NAN", "NONE", ""]:
                mach_cols[c] = col_val

        if furn_col != -1 and "HT" in sn_upper:
            # Issue 12: Dynamic Furnace Discovery
            for r_idx in range(1, len(df_p)):
                val = str(df_p.iloc[r_idx, furn_col]).strip().upper()
                if val and val not in ["NAN", "NONE"]:
                    # Split comma separated furnaces to build the spec map
                    furnaces = [f.strip() for f in val.replace('/', ',').split(',')]
                    for f in furnaces:
                        if f and f not in FURNACE_SPECS:
                            FURNACE_SPECS[f] = 250.0  # Default fallback capacity

        for r_idx in range(1, len(df_p)):
            try:
                p_val = str(df_p.iloc[r_idx, part_col]).strip() if part_col != -1 else ""
                pc_val = str(df_p.iloc[r_idx, pc_col]).strip().upper() if pc_col != -1 else ""
                if not p_val or p_val == "nan": continue
                
                parts = [x.strip() for x in p_val.split('/')] if '/' in p_val else [p_val]
                p_codes = [x.strip() for x in pc_val.split('/')] if '/' in pc_val else [pc_val]
                if not p_codes or p_codes[0] == "NAN": p_codes = ["IR", "OR"]

                weight_val = safe_float(df_p.iloc[r_idx, weight_col]) if weight_col != -1 else None

                for p in parts:
                    clean_p = p.upper()
                    for pc in p_codes:
                        if weight_val is not None and weight_val > 0:
                            weights_map[f"{clean_p}_{pc}"] = weight_val
                            
                        if "HT" in sn_upper and furn_col != -1:
                            f_val = str(df_p.iloc[r_idx, furn_col]).strip().upper()
                            if f_val and f_val not in ["NAN", "NONE"]:
                                furnace_map[f"{clean_p}_{pc}"] = [f.strip() for f in f_val.replace('/', ',').split(',')]
                        
                        elif target_dict is not None:
                            if hr_col != -1:
                                rate = safe_float(df_p.iloc[r_idx, hr_col])
                                if rate > 0: target_dict[f"{clean_p}_{pc}"] = rate
                            else:
                                for c_idx, m_name in mach_cols.items():
                                    rate = safe_float(df_p.iloc[r_idx, c_idx])
                                    if rate > 0: target_dict[f"{clean_p}_{pc}"] = rate

            except Exception as e:
                continue

    result = {'FACE': face_rates, 'OD': od_rates, 'FURNACE': furnace_map, 'WEIGHTS': weights_map, 'PROCESS_FLEX': flex_map, 4: cache_ts}
    PARSED_MASTER_DATA["production"] = result
    return result

@router.get("/api/furnaces")
def get_furnaces():
    parse_master_production_data()
    # Issue 12: Safely return dynamically captured furnaces from the master plan
    if not FURNACE_SPECS:
        return {
            "AICHELIN.(896)": 350.0,
            "CASTLINK FURNACE( 1018 )": 250.0,
            "ROLLER FURNACE ( 148 )": 250.0,
            "SIMPLICITY FURNACE(1238)": 180.0,
            "BIRLEC FURNACE   ( 1158 )": 170.0,
            "SHOEI FURNACE    ( 1062 )": 350.0,
            "AICHELIN UNITHERM ( 2033 )": 250.0
        }
    machines_data = {}
    for f in FURNACE_SPECS.keys():
        machines_data[f] = 250.0
    # Overwrite known specifically typed furnaces
    known = {
        "AICHELIN.(896)": 350.0,
        "CASTLINK FURNACE( 1018 )": 250.0,
        "ROLLER FURNACE ( 148 )": 250.0,
        "SIMPLICITY FURNACE(1238)": 180.0,
        "BIRLEC FURNACE   ( 1158 )": 170.0,
        "SHOEI FURNACE    ( 1062 )": 350.0,
        "AICHELIN UNITHERM ( 2033 )": 250.0
    }
    for k, v in known.items():
        if k in machines_data: machines_data[k] = v
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
        
        channel_demands_day1 = {}
        sheets_zero, _ = get_cached_excel_sheets(ZEROSET_URL, "ZEROSET")
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                r_idx, type_col_idx, mv_col_idx = None, None, None
                c1_col = None
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
                            if pd.notna(val):
                                if isinstance(val, (datetime, pd.Timestamp)) and val.month == req_date.month:
                                    monthly_cols.append(j)
                                elif str(val).strip().isdigit() and 1 <= int(str(val).strip()) <= 31:
                                    monthly_cols.append(j)
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    last_mf = ""
                    for idx in range(r_idx + 1, len(df_zero)):
                        mf_val = str(df_zero.iloc[idx, type_col_idx]).strip() if type_col_idx is not None else ""
                        if mf_val and mf_val not in ["NAN", "NONE"]: last_mf = mf_val
                        
                        mv_val = str(df_zero.iloc[idx, mv_col_idx]).strip() if mv_col_idx is not None else ""
                        raw_t = mv_val if mv_val and mv_val not in ["NAN", "NONE"] else last_mf
                        
                        if is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        if display_name not in monthly_data.get(month_str, {}):
                            if month_str not in monthly_data: monthly_data[month_str] = {}
                            monthly_data[month_str][display_name] = {"total_req": 0, "produced": 0, "channel": str(sheet_name).strip()}
                        
                        row_monthly_sum = sum([safe_float(df_zero.iloc[idx, col]) for col in monthly_cols if col < len(df_zero.columns)])
                        if row_monthly_sum > 0:
                            monthly_data[month_str][display_name]["total_req"] += (row_monthly_sum * 1000)
                        
                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1: 
                                channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)

        saved_plan = load_saved_plan()
        today_prod_map = {}
        if saved_plan and saved_plan.get("date") == req_date.strftime("%Y-%m-%d"):
            plan_data = saved_plan.get("plan", {})
            for m_data in plan_data.get("face_grinding", []):
                for row in m_data.get("rows", []):
                    part_str = row.get("part", "")
                    qty = int(row.get("qty", 0).replace(' Rings (Q)','').replace(' Boxes','').strip()) if isinstance(row.get("qty", 0), str) and row.get("qty", 0).replace('.','',1).isdigit() else 0
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
        summary_list.sort(key=lambda x: x["channel"])

        return {
            "status": "success",
            "date": req_date.strftime("%Y-%m-%d"),
            "data": summary_list
        }
    except Exception as e:
        import traceback
        return {"status": "error", "detail": str(e), "trace": traceback.format_exc()}


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
        
        # 2. PARSE BOX MATRIX 
        box_matrix = {}
        sheets_box, _ = get_cached_excel_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        box_cache_ts = EXCEL_CACHE.get(BOX_RING_DATA_URL, (0, None))[0]
        
        if PARSED_MASTER_DATA["box_matrix"][1] == box_cache_ts and box_cache_ts > 0:
            box_matrix = PARSED_MASTER_DATA["box_matrix"][0]
        elif sheets_box:
            for sheet_name, df_b in sheets_box.items():
                s_name = str(sheet_name).strip().upper()
                part_col, ir_col, or_col = -1, -1, -1
                for c in range(len(df_b.columns)):
                    c_val = str(df_b.iloc[0, c]).strip().upper()
                    if c_val == "PART NO": part_col = c
                    elif c_val == "IR" or c_val == "IR RINGS / BOX": ir_col = c
                    elif c_val == "OR" or c_val == "OR RINGS / BOX": or_col = c
                
                if part_col != -1:
                    for r_idx in range(1, len(df_b)):
                        try:
                            p_val = str(df_b.iloc[r_idx, part_col]).strip()
                            if not p_val or p_val == "nan": continue
                            ck = get_lookup_variants(p_val)[0]
                            if ck not in box_matrix: box_matrix[ck] = {}
                            
                            if ir_col != -1:
                                iv = safe_float(df_b.iloc[r_idx, ir_col])
                                if iv > 0: box_matrix[ck]['IR'] = {'qty': iv, 'source': s_name}
                            if or_col != -1:
                                ov = safe_float(df_b.iloc[r_idx, or_col])
                                if ov > 0: box_matrix[ck]['OR'] = {'qty': ov, 'source': s_name}
                        except: pass
            PARSED_MASTER_DATA["box_matrix"] = (box_matrix, box_cache_ts)
        del sheets_box

        # 3. PARSE MASTER DATA 
        m_data = parse_master_production_data()
        face_rates = m_data['FACE']
        od_rates = m_data['OD']
        furnace_map = m_data['FURNACE']
        weights_map = m_data['WEIGHTS']
        flex_map = m_data['PROCESS_FLEX']

        def get_rate(disp, pc, mach_dict):
            return get_rate_for_part(disp, pc, mach_dict)

        # 4. PREPARE BUFFER LOGIC 
        in_out_buffers = {}
        for row_key, row_data in payload.entries.items():
            disp = row_data.get('disp')
            stage = row_data.get('stage')
            side = row_data.get('side')
            val = safe_float(row_data.get('val', 0))
            if not disp or not stage or not side: continue
            if disp not in in_out_buffers: in_out_buffers[disp] = {'FACE': {}, 'OD': {}, 'HT': {}, 'CH': {}}
            in_out_buffers[disp][stage][side] = val

        o_req = {}
        for disp in set(list(channel_demands_day1.keys()) + list(channel_demands_day2.keys())):
            d1 = channel_demands_day1.get(disp, {'IR': 0, 'OR': 0, 'channel': 'Unknown'})
            d2 = channel_demands_day2.get(disp, {'IR': 0, 'OR': 0, 'channel': 'Unknown'})
            req_ir = d1['IR'] + d2['IR']
            req_od = d1['OR'] + d2['OR']
            chan = d1['channel'] if d1['channel'] != 'Unknown' else d2['channel']
            
            if req_ir <= 0 and req_od <= 0: continue
            
            def apply_buf(stage, req_rings, rpb_rate):
                if req_rings <= 0 or disp not in in_out_buffers or stage not in in_out_buffers[disp]: return 0.0
                side = 'IR' if req_ir > 0 else 'OR'
                if side not in in_out_buffers[disp][stage]: return 0.0
                
                raw_val = in_out_buffers[disp][stage][side]
                base_rings = d1['IR'] if side == 'IR' else d1['OR']
                
                if payload.unit_mode == 'Days': avail_rings = raw_val * base_rings
                elif payload.unit_mode == 'Boxes': avail_rings = raw_val * (rpb_rate if rpb_rate > 0 else 100)
                else: avail_rings = raw_val

                used_rings = min(req_rings, avail_rings)
                rem_rings = avail_rings - used_rings
                
                if payload.unit_mode == 'Days':
                    new_raw = (rem_rings / base_rings) if base_rings > 0 else 0
                elif payload.unit_mode == 'Boxes':
                    new_raw = rem_rings / (rpb_rate if rpb_rate > 0 else 100)
                else:
                    new_raw = rem_rings
                    
                in_out_buffers[disp][stage][side] = new_raw
                return used_rings

            current_req = req_ir
            rpb_ir = get_box_for_part(disp, 'IR', box_matrix, debug_logs, logged_rpb)
            used_ch_buf = apply_buf('CH', current_req, rpb_ir)
            current_req = max(0.0, current_req - used_ch_buf)
            
            if req_ir:
                if current_req > 0:
                    if disp not in o_req: o_req[disp] = {'IR': 0.0, 'OR': 0.0, 'channel': chan}
                    o_req[disp]['IR'] = current_req
                    
            current_req = req_od
            rpb_od = get_box_for_part(disp, 'OR', box_matrix, debug_logs, logged_rpb)
            used_ch_buf = apply_buf('CH', current_req, rpb_od)
            current_req = max(0.0, current_req - used_ch_buf)
            
            if req_od:
                if current_req > 0:
                    if disp not in o_req: o_req[disp] = {'IR': 0.0, 'OR': 0.0, 'channel': chan}
                    o_req[disp]['OR'] = current_req

        # 5. CREATE WORK ITEMS 
        work_items = []
        for disp, reqs in o_req.items():
            chan = reqs['channel']
            c_norm = normalize_channel(chan)
            
            for pc in ['IR', 'OR']:
                qty = reqs[pc]
                if qty > 0:
                    flex = get_process_flexibility(c_norm, pc, flex_map)
                    d1_qty = channel_demands_day1.get(disp, {}).get(pc, 0)
                    if d1_qty >= qty:
                        work_items.append(WorkItem('HT', disp, pc, 0, c_norm, qty, 0.0, 1, flex))
                    else:
                        if d1_qty > 0: work_items.append(WorkItem('HT', disp, pc, 0, c_norm, d1_qty, 0.0, 1, flex))
                        d2_qty = qty - d1_qty
                        if d2_qty > 0: work_items.append(WorkItem('HT', disp, pc, 1, c_norm, d2_qty, 0.0, 2, flex))

        work_items.sort(key=lambda x: (x.day_idx, x.priority))

        # 6. INITIALIZE RESOURCES 
        resources = []
        for f, cap in FURNACE_SPECS.items(): resources.append(Resource(f, 'HT', cap))
        
        mach_list = set()
        for k in face_rates.keys(): mach_list.add(k.split("_")[0])
        for k in od_rates.keys(): mach_list.add(k.split("_")[0])
        
        for m in list(mach_list)[:15]:
            resources.append(Resource(f"{m} (F)", 'FACE', face_rates))
            resources.append(Resource(f"{m} (O)", 'OD', od_rates))

        # 7. APPLY PREVIOUS PLAN DATA 
        saved_plan = load_saved_plan()
        if saved_plan and saved_plan.get("date") == req_date.strftime("%Y-%m-%d"):
            plan_data = saved_plan.get("plan", {})
            for section in ["face_grinding", "od_grinding", "heat_treatment"]:
                for m_data in plan_data.get(section, []):
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
                                    break

        # 8. APPLY MACHINE UNAVAILABILITY 
        for m_id, m_hours in payload.machine_availability.items():
            for r in resources:
                if r.id == m_id:
                    if m_hours >= 24: r.blocked = True
                    else: r.ready_time = max(r.ready_time, float(m_hours))

        # 9. SCHEDULING LOGIC 
        for item in work_items:
            weight = get_weight_for_part(item.disp, item.pc, weights_map)
            rpb = get_box_for_part(item.disp, item.pc, box_matrix, debug_logs, logged_rpb)
            
            stages_to_run = []
            if item.stage == 'HT':
                stages_to_run = ['FACE', 'OD', 'HT']
                if not item.flex.get('FACE', True): stages_to_run.remove('FACE')
                if not item.flex.get('OD', True): stages_to_run.remove('OD')

            for stg in stages_to_run:
                stg_qty = item.qty
                used_buf = apply_buf(stg, stg_qty, rpb)
                stg_qty = max(0.0, stg_qty - used_buf)
                if stg_qty <= 0: continue

                rem_qty = stg_qty
                loop_count = 0
                while rem_qty > 0 and loop_count < 10:
                    loop_count += 1
                    best_res = None
                    best_time = 9999.0
                    rate_or_cap = 0.0

                    for r in resources:
                        if r.type != stg or r.blocked: continue
                        
                        r_rate = 0.0
                        if stg == 'HT':
                            valid_f = get_furnaces_for_part(item.disp, item.pc, furnace_map)
                            if r.id in valid_f and weight is not None and weight > 0:
                                cap_kg = r.capacity_info
                                r_rate = cap_kg / weight
                        else:
                            r_rate = get_rate(item.disp, item.pc, r.capacity_info)

                        if r_rate > 0:
                            setup_time = 0.0 if r.last_fam == item.disp else 1.5
                            finish_time = r.ready_time + setup_time + (rem_qty / r_rate)
                            
                            if finish_time < best_time:
                                best_time = finish_time
                                best_res = r
                                rate_or_cap = r_rate

                    if best_res and rate_or_cap > 0:
                        start_time = best_res.ready_time
                        if best_res.last_fam != item.disp and best_res.last_fam != "": start_time += 1.5
                        
                        max_possible_qty = rate_or_cap * (24.0 - start_time)
                        if max_possible_qty <= 0:
                            best_res.blocked = True
                            continue

                        chunk_qty = min(rem_qty, max_possible_qty)
                        if stg == 'HT':
                            if weight is None or weight <= 0: weight = 0.1
                            chunk_qty_kg = chunk_qty * weight
                            actual_time = chunk_qty_kg / best_res.capacity_info
                            if actual_time > (24.0 - start_time):
                                actual_time = 24.0 - start_time
                                chunk_qty_kg = actual_time * best_res.capacity_info
                                chunk_qty = chunk_qty_kg / weight
                            
                            if chunk_qty <= 0.01:
                                best_res.blocked = True
                                continue
                                
                            actual_time += 3.5
                            display_rate = f"{round((item.qty * weight), 1)} kg"
                            
                            if item.disp in monthly_data.get(month_str, {}):
                                monthly_data[month_str][item.disp]["produced"] += chunk_qty
                        else:
                            if chunk_qty <= 0.01:
                                best_res.blocked = True
                                continue
                            actual_time = chunk_qty / rate_or_cap
                            if best_res.has_bd and start_time < best_res.bd_end and (start_time + actual_time) > best_res.bd_start:
                                actual_time += (best_res.bd_end - max(start_time, best_res.bd_start))
                                
                        res_ready_time = start_time + actual_time
                        best_res.ready_time = res_ready_time
                        best_res.last_fam = item.disp

                        if stg != 'HT':
                            display_rate = f"{int(rate_or_cap)} / hr"

                        best_res.rows.append({
                            "part": f"{item.disp}-{item.pc}",
                            "channel": item.channel,
                            "qty": f"{int(chunk_qty)} Rings (Q)" if rpb <= 0 else f"{math.ceil(chunk_qty / rpb)} Boxes",
                            "rate": display_rate,
                            "timing": f"{format_time(start_time)} - {format_time(res_ready_time)}"
                        })
                        rem_qty -= chunk_qty
                    else:
                        break

                if rem_qty > 0.1:
                    item.qty = rem_qty
                    item.stage = stg
                    break

        for item in work_items:
            if item.qty <= 0.1: continue
            rpb = get_box_for_part(item.disp, item.pc, box_matrix, debug_logs, logged_rpb)
            missed_val = f"{int(item.qty)} Rings (Q)" if rpb <= 0 else f"{math.ceil(item.qty / rpb)} Boxes"
            day_label = "Day 2" if item.day_idx == 1 else "Day 1"
            
            reason = "Capacity Exceeded"
            if item.stage == 'HT' and get_weight_for_part(item.disp, item.pc, weights_map) is None:
                reason = "Missing Weight Data"
            elif item.stage != 'HT':
                if not any(get_rate(item.disp, item.pc, r.capacity_info) > 0 for r in resources if r.type == item.stage):
                    reason = "Missing Machine Rate"
                elif all(r.blocked for r in resources if r.type == item.stage and get_rate(item.disp, item.pc, r.capacity_info) > 0):
                    reason = "Exceeds Planning Window"
                    
            unscheduled.append({
                "stage": item.stage,
                "part": f"{item.disp} {item.pc} ({day_label})",
                "missed_boxes": f"{missed_val} - {reason}"
            })

        final_face = []
        final_od = []
        furnaces_formatted = []
        
        for r in resources:
            if r.type == 'FACE': final_face.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'OD': final_od.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'HT': furnaces_formatted.append({"furnace": r.id, "capacity": f"Total Cap: {int(r.capacity_info)} kg/hr", "rows": r.rows})

        save_monthly_tracking(monthly_data)

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {
                "face_grinding": final_face,
                "od_grinding": final_od,
                "heat_treatment": furnaces_formatted,
                "unscheduled": unscheduled
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "detail": str(e), "trace": traceback.format_exc()}
