import os
import re
import math
import pandas as pd
import requests
import io
import gc
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

# ==========================================
# EDITABLE CHANNEL ROUTING CONFIGURATION (Matrix)
# True = Required (Empty cell), False = Not Required ("No")
# ==========================================
CHANNEL_ROUTING_CONFIG = {
    "1":    {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "2":    {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    "3":    {"IR": {"HT": True, "FACE": True, "OD": True},  "OR": {"HT": True, "FACE": True, "OD": True}},
    "4":    {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    "5":    {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "SABB": {"IR": {"HT": True, "FACE": True, "OD": True},  "OR": {"HT": True, "FACE": True, "OD": True}},
    "7":    {"IR": {"HT": True, "FACE": True, "OD": True},  "OR": {"HT": True, "FACE": True, "OD": True}},
    "8":    {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "11":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "12":   {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    "13":   {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    
    "T1":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T2":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T3":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T4":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T5":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T6":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T7":   {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T8":   {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    "T9":   {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T10":  {"IR": {"HT": True, "FACE": True, "OD": False}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "T11":  {"IR": {"HT": True, "FACE": False, "OD": False}, "OR": {"HT": True, "FACE": False, "OD": False}},
    
    "HUB 1.1": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "HUB 1.2": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "HUB 1.3": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "HUB 1.4": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "HUB 3":   {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    
    "THUB 1.1": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "THUB 1.2": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}},
    "THUB 1.3": {"IR": {"HT": True, "FACE": True, "OD": True}, "OR": {"HT": True, "FACE": True, "OD": True}}
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

def get_routing(channel_raw, part_code, process_name):
    c = str(channel_raw).strip().upper().replace("CH", "").replace(" ", "")
    for key in CHANNEL_ROUTING_CONFIG.keys():
        if c == key.upper().replace(" ", ""): 
            return CHANNEL_ROUTING_CONFIG[key].get(part_code, {}).get(process_name, True)
    return True # Default to True if channel not explicitly mapped

def clean_type(val):
    if not val or pd.isna(val): return None
    v = str(val).strip().upper()
    if not v or v in ['NAN', 'NONE', 'UNKNOWN']: return None
    return v.replace("INDUSTRILA", "INDUSTRIAL")

def get_generic_type(exact_type):
    # Extracts base family for fallback matching (e.g. HUB 1.1 -> HUB)
    if "HUB" in exact_type:
        if "THUB" in exact_type or "T HUB" in exact_type: return "THUB"
        return "HUB"
    if exact_type.startswith("T ") or re.match(r'^T\d+', exact_type): return "T"
    return exact_type

def safe_float(val):
    if pd.isna(val) or val is None: return 0.0
    try:
        s = str(val).replace(',', '').strip()
        if not s or s.lower() in ['nan', 'none', 'null']: return 0.0
        return float(s)
    except:
        return 0.0

def is_date_match(val, target_date):
    if pd.isna(val) or val is None: return False
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.day == target_date.day and val.month == target_date.month
    v_str = str(val).strip().upper()
    # Simple robust day match
    day_str = str(target_date.day)
    day_pad = f"{target_date.day:02d}"
    
    tokens = re.split(r'[-/._: ]', v_str)
    if day_str in tokens or day_pad in tokens:
        month_str = target_date.strftime("%b").upper()
        if any(m in v_str for m in ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]):
            return month_str in v_str
        return True
    return False

def load_excel(url):
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None
        return pd.read_excel(io.BytesIO(resp.content), sheet_name=None, header=None)
    except:
        return None

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # ---------------------------------------------------------
        # 1. EXTRACT DEMAND (ZEROSET)
        # ---------------------------------------------------------
        channel_demands = {} 
        sheets_zero = load_excel(ZEROSET_URL)
        
        if sheets_zero:
            for sheet_name, df_z in sheets_zero.items():
                r_idx, t_col, c1, c2 = None, None, None, None
                
                # Find headers robustly
                for i in range(min(20, len(df_z))):
                    row_vals = [str(x).strip().upper() for x in df_z.iloc[i].values]
                    for j, val in enumerate(row_vals):
                        if val in ["TYPE", "MF", "PART NO", "BRG NO"]: t_col = j
                        if is_date_match(val, req_date): c1 = j
                        if is_date_match(val, next_date): c2 = j
                    if t_col is not None and (c1 is not None or c2 is not None):
                        r_idx = i
                        break
                        
                if r_idx is not None and t_col is not None:
                    for idx in range(r_idx + 1, len(df_z)):
                        raw_type = clean_type(df_z.iloc[idx, t_col])
                        if not raw_type: continue
                        
                        # Skip summary rows
                        row_str = " ".join([str(x).strip().upper() for x in df_z.iloc[idx].values])
                        if any(bw in row_str for bw in ['MTD', 'WIP', 'ACTUAL', 'CUM', 'SHORT', 'ACHIEVE']): continue
                        
                        v1 = safe_float(df_z.iloc[idx, c1]) if c1 is not None else 0.0
                        v2 = safe_float(df_z.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        # Auto-scale thousands
                        r1 = v1 * 1000 if 0 < v1 <= 70 else v1
                        r2 = v2 * 1000 if 0 < v2 <= 70 else v2
                        
                        # If required today OR starting fresh tomorrow
                        if r1 > 0 or (r1 == 0 and r2 > 0):
                            combined = r1 + r2
                            if combined > 0:
                                if raw_type not in channel_demands: 
                                    channel_demands[raw_type] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                                
                                is_ir = " IR" in row_str or "-IR" in row_str or "010" in row_str
                                is_or = " OR" in row_str or "-OR" in row_str or "100" in row_str
                                
                                if is_ir and not is_or: channel_demands[raw_type]['IR'] += combined
                                elif is_or and not is_ir: channel_demands[raw_type]['OR'] += combined
                                else: 
                                    channel_demands[raw_type]['IR'] += combined
                                    channel_demands[raw_type]['OR'] += combined
            del sheets_zero

        # ---------------------------------------------------------
        # 2. MASTER DATA: BOXES & WEIGHTS
        # ---------------------------------------------------------
        box_matrix = {}
        sheets_box = load_excel(BOX_RING_DATA_URL)
        if sheets_box:
            for s_name, df_b in sheets_box.items():
                if 'RING PER BOX' in str(s_name).upper():
                    # Scan every row/column for 'I/R' and 'O/R' mappings
                    for r in range(len(df_b)):
                        for c in range(len(df_b.columns)):
                            val = str(df_b.iloc[r, c]).strip().upper()
                            if val in ['TYPE', 'PART NO']:
                                if c + 2 < len(df_b.columns):
                                    for sub_r in range(r + 1, min(r + 50, len(df_b))):
                                        t_val = clean_type(df_b.iloc[sub_r, c])
                                        if t_val:
                                            # Look rightward for numbers
                                            val1 = safe_float(df_b.iloc[sub_r, c+1])
                                            val2 = safe_float(df_b.iloc[sub_r, c+2])
                                            
                                            if t_val not in box_matrix: box_matrix[t_val] = {'IR': 100.0, 'OR': 100.0}
                                            # Usually O/R is first, I/R is second in your image
                                            if val1 > 0: box_matrix[t_val]['OR'] = val1
                                            if val2 > 0: box_matrix[t_val]['IR'] = val2
            del sheets_box

        weight_matrix, furnace_map, furnace_rates = {}, {}, {}
        machines_data = {'FACE': {}, 'OD': {}}
        dynamic_furnaces = set()
        
        sheets_prod = load_excel(SHO_PRODUCTION_URL)
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS']
                df_w.columns = [str(x).strip().upper() for x in df_w.iloc[0]]
                for _, r in df_w.iloc[1:].iterrows():
                    t_val = clean_type(r.get('TYPE'))
                    if t_val:
                        pc = 'OR' if str(r.get('IR/OR')) == '100' else 'IR'
                        weight_matrix[f"{t_val}_{pc}"] = safe_float(r.get('WEIGHT PER RING', 0.1))

            if 'Furnace Type Flexibility' in sheets_prod:
                df_f = sheets_prod['Furnace Type Flexibility']
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for _, r in df_f.iloc[1:].iterrows():
                    t_val = clean_type(r.get('TYPE', r.iloc[0]))
                    if t_val: 
                        fur_raw = str(r.get('FURNACE', r.iloc[1] if len(r) > 1 else ''))
                        furnaces = [f.strip().upper() for f in fur_raw.replace(',', ' ').split() if f.strip()]
                        if furnaces: 
                            furnace_map[t_val] = furnaces
                            dynamic_furnaces.update(furnaces)
                        cap = safe_float(r.get('CAPACITY', r.get('KG/HR', 400.0)))
                        if cap > 0: furnace_rates[t_val] = cap

            # Dynamic Grinding Machine Scanner
            for s_name, df_m in sheets_prod.items():
                if s_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                
                sheet_m_type = "UNKNOWN"
                if "FACE" in str(s_name).upper(): sheet_m_type = "FACE"
                elif "OD" in str(s_name).upper(): sheet_m_type = "OD"
                
                for r in range(len(df_m)):
                    for c in range(len(df_m.columns)):
                        cell = str(df_m.iloc[r, c]).strip().upper()
                        if 'MACHINE' in cell or any(x in cell for x in ['BG', 'DDS', 'CL', 'CELL']):
                            m_num = cell.replace('MACHINE', '').replace(':', '').strip()
                            if not m_num and c+1 < len(df_m.columns): m_num = str(df_m.iloc[r, c+1]).strip()
                            if not m_num: continue
                            
                            m_type = sheet_m_type
                            if "DDS" in m_num or "BG" in m_num: m_type = "FACE"
                            elif "CL" in m_num or "CELL" in m_num: m_type = "OD"
                            
                            if m_type not in ['FACE', 'OD']: continue
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                                
                            # Find table header nearby
                            h_idx, t_col, r_col, rpb_col = -1, -1, -1, -1
                            for offset in range(1, 8):
                                if r + offset >= len(df_m): break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                for i, h in enumerate(h_row):
                                    if h in ['TYPE', 'PART NO']: t_col, h_idx = i, r + offset
                                    if 'BOX' in h or 'RATE' in h or 'STD/HR' in h: r_col = i
                                    if 'RING' in h and 'BOX' in h: rpb_col = i
                                if h_idx != -1: break
                                
                            if h_idx != -1 and t_col != -1 and r_col != -1:
                                for br in range(h_idx + 1, min(h_idx + 30, len(df_m))):
                                    t_val = clean_type(df_m.iloc[br, t_col])
                                    if not t_val: continue
                                    rate_val = safe_float(df_m.iloc[br, r_col])
                                    
                                    if rate_val > 0:
                                        if 'STD' in str(df_m.iloc[h_idx, r_col]).upper():
                                            rpb = safe_float(df_m.iloc[br, rpb_col]) if rpb_col != -1 else 100
                                            if rpb == 0: rpb = 100
                                            rate_val = rate_val / rpb
                                            
                                        # Map both IR and OR for this type
                                        raw_p = str(df_m.iloc[br, t_col]).upper()
                                        p_codes = ['IR', 'OR']
                                        if '100' in raw_p or 'OR' in raw_p: p_codes = ['OR']
                                        elif '010' in raw_p or 'IR' in raw_p: p_codes = ['IR']
                                        
                                        for pc in p_codes:
                                            machines_data[m_type][m_num]['rates'][f"{t_val}_{pc}"] = rate_val
            del sheets_prod

        # ---------------------------------------------------------
        # 3. BUFFER CASCADING (WITH MATRIX ROUTING)
        # ---------------------------------------------------------
        buffers = {}
        PREFIX_MAP = {
            'ch_buffer_1': ('type_1', 'CH'), 'ch_buffer_2': ('next_type_1', 'CH'),
            'od_buffer_1': ('type_2', 'OD'), 'od_buffer_2': ('next_type_2', 'OD'),
            'face_buffer_1': ('type_3', 'FACE'), 'face_buffer_2': ('type_4', 'FACE'),
            'ht_buffer_1': ('type_5', 'HT'), 'ht_buffer_2': ('type_6', 'HT')
        }

        for bp, (tp, stage) in PREFIX_MAP.items():
            for key, val in payload.entries.items():
                if key.startswith(tp + '_'):
                    parts = key.split('_')
                    if len(parts) < 3: continue
                    ch, ring = parts[-2], parts[-1]
                    
                    fam = clean_type(val)
                    if not fam: continue
                    
                    b_val = safe_float(payload.entries.get(f"{bp}_{ch}_{ring}", 0))
                    if b_val > 0:
                        if fam not in buffers: buffers[fam] = {'CH': {'IR':0,'OR':0}, 'OD': {'IR':0,'OR':0}, 'FACE': {'IR':0,'OR':0}, 'HT': {'IR':0,'OR':0}}
                        buffers[fam][stage][ring] += b_val

        od_req, face_req, ht_req = {}, {}, {}
        
        for fam, dem in channel_demands.items():
            ch_name = dem['channel']
            
            # Fetch generic master data if exact doesn't exist
            gen_fam = get_generic_type(fam)
            rpb_ir = box_matrix.get(fam, box_matrix.get(gen_fam, {})).get('IR', 100)
            rpb_or = box_matrix.get(fam, box_matrix.get(gen_fam, {})).get('OR', 100)
            
            req_ir = dem['IR'] / rpb_ir
            req_or = dem['OR'] / rpb_or
            
            def get_buf(stg, side, rpb):
                b = buffers.get(fam, {}).get(stg, {}).get(side, 0)
                return b if payload.unit_mode == 'Days' else (b / rpb)
                
            b_ch_ir, b_ch_or = get_buf('CH', 'IR', rpb_ir), get_buf('CH', 'OR', rpb_or)
            b_od_ir, b_od_or = get_buf('OD', 'IR', rpb_ir), get_buf('OD', 'OR', rpb_or)
            b_fc_ir, b_fc_or = get_buf('FACE', 'IR', rpb_ir), get_buf('FACE', 'OR', rpb_or)

            # CASCADING (Req <- CH <- OD <- FACE <- HT)
            # If process is NOT required, it bypasses the buffer deduction for that stage
            
            # 1. To OD
            od_n_ir = max(0.0, req_ir - b_ch_ir) if get_routing(ch_name, 'IR', 'OD') else 0.0
            od_n_or = max(0.0, req_or - b_ch_or) if get_routing(ch_name, 'OR', 'OD') else 0.0
            
            curr_ir = max(0.0, od_n_ir - b_od_ir) if od_n_ir > 0 else max(0.0, req_ir - b_ch_ir)
            curr_or = max(0.0, od_n_or - b_od_or) if od_n_or > 0 else max(0.0, req_or - b_ch_or)

            # 2. To FACE
            fc_n_ir = curr_ir if get_routing(ch_name, 'IR', 'FACE') else 0.0
            fc_n_or = curr_or if get_routing(ch_name, 'OR', 'FACE') else 0.0
            
            curr_ir = max(0.0, fc_n_ir - b_fc_ir) if fc_n_ir > 0 else curr_ir
            curr_or = max(0.0, fc_n_or - b_fc_or) if fc_n_or > 0 else curr_or

            # Assign Grinding
            if od_n_ir > 0 or od_n_or > 0: od_req[fam] = {'IR': od_n_ir, 'OR': od_n_or}
            if fc_n_ir > 0 or fc_n_or > 0: face_req[fam] = {'IR': fc_n_ir, 'OR': fc_n_or}

            # 3. To HT (Convert back to rings and Force Equalization)
            ht_n_ir = (curr_ir * rpb_ir) if get_routing(ch_name, 'IR', 'HT') else 0.0
            ht_n_or = (curr_or * rpb_or) if get_routing(ch_name, 'OR', 'HT') else 0.0
            
            if ht_n_ir > 0 and ht_n_or > 0:
                max_ht = max(ht_n_ir, ht_n_or)
                ht_n_ir, ht_n_or = max_ht, max_ht
                
            if ht_n_ir > 0 or ht_n_or > 0:
                ht_req[fam] = {'IR': ht_n_ir, 'OR': ht_n_or, 'channel': ch_name}

        # ---------------------------------------------------------
        # 4. ALLOCATION: GRINDING
        # ---------------------------------------------------------
        def alloc_grind(m_type, reqs):
            allocs = []
            fams = sorted(reqs.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            work_reqs = {f: {'IR': d['IR'], 'OR': d['OR']} for f, d in fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                if not rates: continue
                
                rows, hrs = [], 24.0
                curr_f = None
                
                for fam, _ in fams:
                    if hrs <= 0 or len(rows) >= 6: break
                    gen_fam = get_generic_type(fam)
                    
                    for pc in ['IR', 'OR']:
                        boxes = work_reqs[fam][pc]
                        if boxes <= 0: continue
                        
                        rate = rates.get(f"{fam}_{pc}", rates.get(f"{gen_fam}_{pc}", 0.0))
                        if rate > 0:
                            setup = 1.0 if (curr_f and curr_f != fam) else 0.0
                            if hrs <= setup: hrs = 0.0; break
                            
                            hrs -= setup
                            time_req = boxes / rate
                            
                            if time_req <= hrs:
                                work_reqs[fam][pc] = 0.0
                                hrs -= time_req
                            else:
                                work_reqs[fam][pc] -= (hrs * rate)
                                hrs = 0.0
                                
                            curr_f = fam
                            rows.append({
                                "part": f"{fam} {pc}", "std_box": str(round(rate, 1)),
                                "p_2nd": "1" if len(rows) == 0 else "", "p_3rd": "1" if len(rows) == 1 else "",
                                "alert": False, "p_label": f"P{len(rows) + 1}"
                            })
                            if hrs <= 0 or len(rows) >= 6: break
                if rows: allocs.append({"machine": m_num, "rows": rows})
            return allocs

        final_face = alloc_grind('FACE', face_req)
        final_od = alloc_grind('OD', od_req)

        # ---------------------------------------------------------
        # 5. ALLOCATION: HEAT TREATMENT (STRICT PRIMARY)
        # ---------------------------------------------------------
        all_furs = list(dynamic_furnaces) if dynamic_furnaces else ["AICHELIN.(896)", "BATCH FURNACE"]
        fur_clocks = {f: {"avail_hours": 24.0, "current_fam": None, "rows": []} for f in all_furs}

        for fam, data in sorted(ht_req.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True):
            gen_fam = get_generic_type(fam)
            pref_furs = furnace_map.get(fam, furnace_map.get(gen_fam, [all_furs[0]]))
            kg_hr = furnace_rates.get(fam, furnace_rates.get(gen_fam, 400.0))
            
            w_ir = weight_matrix.get(f"{fam}_IR", weight_matrix.get(f"{gen_fam}_IR", 0.15))
            w_or = weight_matrix.get(f"{fam}_OR", weight_matrix.get(f"{gen_fam}_OR", 0.15))
            
            primary_fur = pref_furs[0]
            if primary_fur not in fur_clocks: fur_clocks[primary_fur] = {"avail_hours": 24.0, "current_fam": None, "rows": []}
            ctx = fur_clocks[primary_fur]
            
            for pc, qty in [('IR', data['IR']), ('OR', data['OR'])]:
                if qty <= 0: continue
                kg = qty * (w_or if pc == 'OR' else w_ir)
                time_req = kg / kg_hr
                
                setup = 2.0 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                ctx["avail_hours"] -= (time_req + setup)
                ctx["current_fam"] = fam
                
                ctx["rows"].append({
                    "part": f"{fam}-{pc}", "qty": str(int(qty)), "cha": data['channel'],
                    "rate": str(round(kg / 24.0, 2)), "alert": ctx["avail_hours"] < 0 
                })

        ht_fmt = [
            {"furnace": f, "capacity": str(int(furnace_rates.get(get_generic_type(d["rows"][0]["part"].split('-')[0]), 400))), "rows": d["rows"]}
            for f, d in fur_clocks.items() if len(d["rows"]) > 0
        ]

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {"face_grinding": final_face, "od_grinding": final_od, "heat_treatment": ht_fmt}
        }
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs + [f"CRITICAL: {traceback.format_exc()}"], "detail": str(e)}
