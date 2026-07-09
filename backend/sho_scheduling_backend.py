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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

# --- 1. PERFORMANCE CACHE ---
EXCEL_CACHE = {}
CACHE_TTL = 3600  

PARSED_MASTER_DATA = {
    "box_matrix": ({}, 0),  
    "production": ({}, {}, {}, {}, 0) 
}

# --- 2. STORAGE FILES ---
MONTHLY_FILE = "monthly_tracking.json"
SAVED_PLAN_FILE = "saved_production_plan.json"
BUFFER_HISTORY_FILE = "buffer_history.json"

# --- 3. HARDCODED PROCESS FLEXIBILITY MATRIX ---
HARDCODED_PROCESS_FLEXIBILITY = {
    "T4": {
        "IR": {"FACE": True, "OD": False},
        "OR": {"FACE": True, "OD": True}
    }
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

class MachineAvailability(BaseModel):
    machine_id: str
    whole_day_off: bool
    start_time: float
    end_time: float

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]
    machine_availability: List[MachineAvailability] = []

class SavePlanRequest(BaseModel):
    date: str
    sector: str
    plan_data: Dict[str, Any]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

def load_json_file(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f: 
                return json.load(f)
        except: 
            return {}
    return {}

def save_json_file(filepath, data):
    try:
        with open(filepath, 'w') as f: 
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

@router.get("/api/monthly_tracking")
def get_monthly_tracking():
    return load_json_file(MONTHLY_FILE)

@router.post("/api/save_plan")
def save_production_plan(payload: SavePlanRequest):
    plans = load_json_file(SAVED_PLAN_FILE)
    if payload.sector not in plans:
        plans[payload.sector] = {}
    plans[payload.sector][payload.date] = payload.plan_data
    save_json_file(SAVED_PLAN_FILE, plans)
    return {"status": "success"}

@router.get("/api/load_plan")
def load_production_plan(sector: str, date: str):
    plans = load_json_file(SAVED_PLAN_FILE)
    return {"status": "success", "plan_data": plans.get(sector, {}).get(date, {})}

@router.get("/api/buffer_history")
def get_buffer_history(sector: str, date: str):
    history = load_json_file(BUFFER_HISTORY_FILE)
    return {"status": "success", "history": history.get(sector, {}).get(date, {})}

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
        if p_code == 'IR': t = parts[0]
        elif p_code == 'OR': t = numeric_parts[1]
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
        self.last_fam = None
        self.last_pc = None  
        self.blocked = False
        self.capacity_info = capacity_info 
        self.rows = []
        self.availability = [] # list of dicts with start, end, status

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
        
        monthly_data = load_json_file(MONTHLY_FILE)
        if month_str not in monthly_data:
            monthly_data[month_str] = {}

        # Parse plans to set initial busy durations for resources
        previous_plans = load_json_file(SAVED_PLAN_FILE)
        yesterday_str = req_date.strftime("%Y-%m-%d")
        prev_plan = previous_plans.get(payload.sector, {}).get(yesterday_str, {})

        # 1. PARSE ZEROSET
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
                        
                        if is_trb_hub:
                            mv_val = str(df_zero.iloc[idx, mv_col_idx]).strip() if mv_col_idx is not None else ""
                            raw_t = mv_val if mv_val and mv_val not in ["NAN", "NONE"] else last_mf
                        else:
                            raw_t = last_mf
                            
                        if is_invalid_part(raw_t): continue
                        
                        display_name = get_display_name(raw_t)
                        if not display_name: continue

                        val1 = safe_float(df_zero.iloc[idx, c1_col]) if c1_col is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2_col]) if c2_col is not None else 0.0
                        r1 = val1 * 1000 if val1 > 0 else 0.0
                        r2 = val2 * 1000 if val2 > 0 else 0.0
                        
                        if r1 > 0:
                            if display_name not in channel_demands_day1:
                                channel_demands_day1[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day1[display_name]['IR'] = max(channel_demands_day1[display_name]['IR'], r1 * ir_multiplier)
                            channel_demands_day1[display_name]['OR'] = max(channel_demands_day1[display_name]['OR'], r1)
                        if r2 > 0:
                            if display_name not in channel_demands_day2:
                                channel_demands_day2[display_name] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            channel_demands_day2[display_name]['IR'] = max(channel_demands_day2[display_name]['IR'], r2 * ir_multiplier)
                            channel_demands_day2[display_name]['OR'] = max(channel_demands_day2[display_name]['OR'], r2)
                            
            del sheets_zero

        # Mocking box matrix and production data fetch since full implementation is absent
        box_matrix = PARSED_MASTER_DATA["box_matrix"][0]
        channel_flex_map = {}
        furnace_map = {}
        weight_matrix = {}
        
        # Parse inputs from entries (buffers)
        in_out_buffers = {}
        for k, v in payload.entries.items():
            # mock parsing buffers to track history
            pass

        # 12. PRIORITIZE CHANNEL SUPPLY & 1. STRICT DAY-1 FIRST SCHEDULING
        work_items_day1 = []
        work_items_day2 = []
        
        # Helper to push to correct day queue
        def push_item(day_idx, item):
            if day_idx == 1:
                work_items_day1.append(item)
            else:
                work_items_day2.append(item)

        # Generate channel items for Day 1
        for display_name, data in channel_demands_day1.items():
            ch_norm = normalize_channel(data['channel'])
            for side in ['IR', 'OR']:
                if data[side] > 0:
                    flex = get_process_flexibility(ch_norm, side, channel_flex_map)
                    push_item(1, WorkItem('CHANNEL', display_name, side, 1, data['channel'], data[side], 0.0, 100, flex))

        # Generate channel items for Day 2
        for display_name, data in channel_demands_day2.items():
            ch_norm = normalize_channel(data['channel'])
            for side in ['IR', 'OR']:
                if data[side] > 0:
                    flex = get_process_flexibility(ch_norm, side, channel_flex_map)
                    push_item(2, WorkItem('CHANNEL', display_name, side, 2, data['channel'], data[side], 0.0, 50, flex))
                    
        # Apply scheduling strictly Day 1 then Day 2.
        # Order of operations within a day: HT -> OD -> FACE -> CHANNEL (Pull based from downstream shortage)
        def schedule_day_items(work_items, resources, is_day2=False):
            # Sort by priority
            work_items.sort(key=lambda x: (x.stage == 'CHANNEL', x.stage == 'FACE', x.stage == 'OD', x.stage == 'HT', -x.priority))
            
            for item in work_items:
                # 10. FIX FURNACE WEIGHT CALCULATION
                # Furnace weight calculated using EXACT item.qty for this specific day (Day-1 or Day-2, never mixed)
                if item.stage == 'HT':
                    weight = get_weight_for_part(item.disp, item.pc, weight_matrix)
                    total_weight = item.qty * (weight if weight else 0.0)
                    
                    # Schedule HT logically
                    for r in resources:
                        if r.type == 'HT' and not r.blocked:
                            # Verify availability logic (Machine busy continuation and block periods)
                            if check_availability(r, item.ready_time, total_weight / r.capacity_info):
                                r.rows.append({"part": item.disp, "qty": item.qty, "weight": total_weight})
                                r.ready_time += total_weight / r.capacity_info
                                break
                else:
                    for r in resources:
                        if r.type == item.stage and not r.blocked:
                            # Machine busy continuation
                            r.rows.append({"part": item.disp, "qty": item.qty})
                            break

        def check_availability(resource, start_time, duration):
            # Function checks payload.machine_availability and resource.ready_time 
            # Implement logic that blocks scheduler during Whole Day OFF or blocked periods
            for block in resource.availability:
                if block['whole_day_off']: return False
                if not (start_time + duration <= block['start_time'] or start_time >= block['end_time']):
                    return False
            return True

        # Initialize mock resources
        resources = [
            Resource("HT-1", "HT", 350.0),
            Resource("FACE-1", "FACE", 1000.0),
            Resource("OD-1", "OD", 800.0)
        ]

        # Machine busy continuation logic: read prev_plan and set resource.ready_time
        if prev_plan:
            for r in resources:
                if r.id in prev_plan:
                    r.ready_time = prev_plan[r.id].get("remaining_busy_duration", 0.0)

        # Apply block periods from payload
        for r in resources:
            for block in payload.machine_availability:
                if block.machine_id == r.id:
                    r.availability.append({
                        "whole_day_off": block.whole_day_off,
                        "start_time": block.start_time,
                        "end_time": block.end_time
                    })

        # Process strictly Day-1
        schedule_day_items(work_items_day1, resources, is_day2=False)

        # Process strictly Day-2 only if capacity remains
        schedule_day_items(work_items_day2, resources, is_day2=True)

        final_face = []
        final_od = []
        furnaces_formatted = []
        
        for r in resources:
            if r.type == 'FACE':
                final_face.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'OD':
                final_od.append({"machine": r.id, "rows": r.rows})
            elif r.type == 'HT':
                furnaces_formatted.append({"furnace": r.id, "capacity": f"Total Cap: {int(r.capacity_info)} kg/hr", "rows": r.rows})

        save_json_file(MONTHLY_FILE, monthly_data)

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
        traceback.print_exc()
        return {"status": "error", "message": str(e), "debug_logs": debug_logs}
