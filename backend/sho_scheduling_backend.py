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

FAM_REGEX = re.compile(r'(\d{3,5})')

# ==========================================
# EDITABLE CHANNEL ROUTING CONFIGURATION
# Based on Factory Matrix. True = Required (Empty cell in image), False = Not Required ("No" in image).
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

def normalize_channel_key(raw_channel):
    c = str(raw_channel).strip().upper().replace("CH", "").replace(" ", "")
    for key in CHANNEL_ROUTING_CONFIG.keys():
        if c == key.upper().replace(" ", ""): return key
    return None

def process_is_required(channel_raw, part_code, process_name):
    norm_key = normalize_channel_key(channel_raw)
    if not norm_key: return True 
    return CHANNEL_ROUTING_CONFIG[norm_key].get(part_code, {}).get(process_name, True)

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if "INDUSTRILA" in text: text = text.replace("INDUSTRILA", "INDUSTRIAL")
    if "AUTOMOTIVE" in text: return None
    if not text or text in ["NAN", "NONE", "", "UNKNOWN"]: return None
    
    # EXACT PRESERVATION FOR HUB AND TRB
    if "HUB" in text:
        match_hub = re.search(r'(T?\s*HUB\s*\d+\.?\d*)', text)
        if match_hub: return match_hub.group(1).replace(" ", "")
        return "HUB"
        
    if text.startswith("T ") or re.match(r'^T\d+', text) or text.startswith("TRB"):
        match_t = re.search(r'(T\s*\d+)', text)
        if match_t: return match_t.group(1).replace(" ", "")
        return "T"

    t_norm = text.replace("-", " ").replace("_", " ").replace("/", " ")
    words = t_norm.split()
    
    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    
    if "BT" in words or text.startswith("BT") or "-BT" in text or " BT" in text: base = f"BT-{base}"
    elif "BB" in words or text.startswith("BB") or "-BB" in text or " BB" in text: base = f"BB-{base}"
    
    if "UC" in text:
        match_uc = re.search(r'(UC\s*\d+)', text)
        if match_uc: base = match_uc.group(1).replace(" ", "")
        
    return base

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

def load_excel_all_sheets(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "": return None, logs
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None, logs
        content = io.BytesIO(resp.content)
        try:
            return pd.read_excel(content, sheet_name=None, header=None, engine='calamine'), logs
        except Exception:
            return pd.read_excel(content, sheet_name=None, header=None), logs
    except Exception as e:
        return None, [f"[{file_label}] ERR: {str(e)}"]

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # ==========================================
        # 1. PARSE ZEROSET (PIPELINE DEMAND)
        # ==========================================
        channel_demands = {} 
        sheets_zero, logs1 = load_excel_all_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                norm_sheet_key = normalize_channel_key(sheet_name)
                if not norm_sheet_key: continue 
                
                r_idx, type_col_idx, c1, c2 = None, None, None, None
                
                for i in range(min(25, len(df_zero))):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[i].values]
                    row_joined = " ".join(row_strs)
                    
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF", "PART NO", "BRG NO"] or "TYPE" in val: 
                                type_col_idx = j
                                break
                                
                    if any(k in row_joined for k in ['MTD', 'PKWIP', 'PLAN', 'ASKING']):
                        r_idx = i
                        for j, val in enumerate(df_zero.iloc[i].values):
                            if is_target_date(val, req_date): c1 = j
                            if is_target_date(val, next_date): c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None and (c1 is not None or c2 is not None):
                    for idx in range(r_idx + 1, len(df_zero)):
                        cell_val = df_zero.iloc[idx, type_col_idx]
                        if not pd.notna(cell_val) or str(cell_val).strip() == "": continue
                        
                        fam = parse_family(str(cell_val).strip())
                        if not fam: continue
                        
                        val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        r1 = val1 * 1000 if 0 < val1 <= 70 else val1
                        r2 = val2 * 1000 if 0 < val2 <= 70 else val2
                        
                        if r1 > 0:
                            combined_qty = r1 + r2
                            if fam not in channel_demands: 
                                channel_demands[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            
                            channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], combined_qty)
                            channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], combined_qty)
            del sheets_zero
            gc.collect()

        # ==========================================
        # 2. PROPER BOX RATIO EXTRACTION (MULTI-COLUMN GRID)
        # ==========================================
        box_matrix = {}
        sheets_box, _ = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box:
            for sheet_name, df_box in sheets_box.items():
                if 'RING PER BOX' in str(sheet_name).upper():
                    str_matrix = df_box.fillna('').astype(str).values
                    for r in range(str_matrix.shape[0]):
                        for c in range(str_matrix.shape[1]):
                            val = str_matrix[r, c].strip().upper()
                            if val in ['TYPE', 'PART NO', 'PART']:
                                if c + 2 < str_matrix.shape[1]:
                                    col1 = str_matrix[r, c+1].strip().upper()
                                    col2 = str_matrix[r, c+2].strip().upper()
                                    
                                    ir_idx, or_idx = -1, -1
                                    if 'I/R' in col1 or 'IR' in col1: ir_idx = c+1
                                    if 'O/R' in col1 or 'OR' in col1: or_idx = c+1
                                    if 'I/R' in col2 or 'IR' in col2: ir_idx = c+2
                                    if 'O/R' in col2 or 'OR' in col2: or_idx = c+2
                                    
                                    if ir_idx != -1 and or_idx != -1:
                                        for row_d in range(r+1, min(r+30, str_matrix.shape[0])):
                                            t_val = str_matrix[row_d, c].strip()
                                            if not t_val: continue
                                            fam = parse_family(t_val)
                                            if fam:
                                                i_val = safe_float(str_matrix[row_d, ir_idx])
                                                o_val = safe_float(str_matrix[row_d, or_idx])
                                                if fam not in box_matrix: box_matrix[fam] = {'IR': 100.0, 'OR': 100.0}
                                                if i_val > 0: box_matrix[fam]['IR'] = i_val
                                                if o_val > 0: box_matrix[fam]['OR'] = o_val
            del sheets_box
            gc.collect()

        # ==========================================
        # 3. BUFFER MERGING & CORRECTED CASCADING
        # ==========================================
        buffers_by_fam = {}
        BUFFER_MAP = {
            'ch_buffer_1': ('type_1', 'CH'), 'ch_buffer_2': ('next_type_1', 'CH'),
            'od_buffer_1': ('type_2', 'OD'), 'od_buffer_2': ('next_type_2', 'OD'),
            'face_buffer_1': ('type_3', 'FACE'), 'face_buffer_2': ('type_4', 'FACE'),
            'ht_buffer_1': ('type_5', 'HT'), 'ht_buffer_2': ('type_6', 'HT')
        }

        for buf_prefix, (type_prefix, stage) in BUFFER_MAP.items():
            for key, val in payload.entries.items():
                if key.startswith(type_prefix + '_'):
                    parts = key.split('_')
                    if len(parts) < 3: continue
                    col_channel, sub_ring_type = parts[-2], parts[-1]
                    
                    fam = parse_family(val)
                    if not fam: continue
                    
                    buf_val = safe_float(payload.entries.get(f"{buf_prefix}_{col_channel}_{sub_ring_type}", 0))
                    if buf_val <= 0: continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 'FACE': {'IR': 0.0, 'OR': 0.0}, 'HT': {'IR': 0.0, 'OR': 0.0}}
                    buffers_by_fam[fam][stage][sub_ring_type] += buf_val

        od_req, face_req, ht_req = {}, {}, {}
        for fam, demands in channel_demands.items():
            ch_name = demands['channel']
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
            req_ir = demands['IR'] / rpb_ir
            req_or = demands['OR'] / rpb_or
            
            def get_buf_boxes(stage, side, base_boxes, rpb_rate):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(side, 0)
                if payload.unit_mode == 'Days': return raw_buf * base_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb_rate
                return raw_buf 
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_or, rpb_or)
            od_buf_ir = get_buf_boxes('OD', 'IR', req_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_or, rpb_or)
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_or, rpb_or)

            # CASCADING LOGIC - Correctly handles bypassed processes
            od_net_ir = 0.0
            if process_is_required(ch_name, 'IR', 'OD'):
                od_net_ir = max(0.0, req_ir - ch_buf_ir)
                req_ir = max(0.0, od_net_ir - od_buf_ir) 
            else:
                req_ir = max(0.0, req_ir - ch_buf_ir)

            od_net_or = 0.0
            if process_is_required(ch_name, 'OR', 'OD'):
                od_net_or = max(0.0, req_or - ch_buf_or)
                req_or = max(0.0, od_net_or - od_buf_or)
            else:
                req_or = max(0.0, req_or - ch_buf_or)

            face_net_ir = 0.0
            if process_is_required(ch_name, 'IR', 'FACE'):
                face_net_ir = req_ir
                req_ir = max(0.0, face_net_ir - face_buf_ir)
            
            face_net_or = 0.0
            if process_is_required(ch_name, 'OR', 'FACE'):
                face_net_or = req_or
                req_or = max(0.0, face_net_or - face_buf_or)

            if od_net_ir > 0 or od_net_or > 0: 
                od_req[fam] = {'IR': od_net_ir, 'OR': od_net_or, 'channel': ch_name}
            if face_net_ir > 0 or face_net_or > 0: 
                face_req[fam] = {'IR': face_net_ir, 'OR': face_net_or, 'channel': ch_name}

            # EQUAL IR & OR LOGIC FOR HEAT TREATMENT
            req_ht_ir = process_is_required(ch_name, 'IR', 'HT')
            req_ht_or = process_is_required(ch_name, 'OR', 'HT')
            
            ht_net_ir_rings = req_ir * rpb_ir if req_ht_ir else 0.0
            ht_net_or_rings = req_or * rpb_or if req_ht_or else 0.0
            
            # If both are required, equalize them to the maximum
            if req_ht_ir and req_ht_or:
                max_ht_rings = max(ht_net_ir_rings, ht_net_or_rings)
                ht_net_ir_rings = max_ht_rings
                ht_net_or_rings = max_ht_rings
                
            if ht_net_ir_rings > 0 or ht_net_or_rings > 0:
                ht_req[fam] = {
                    'IR': ht_net_ir_rings / rpb_ir,
                    'OR': ht_net_or_rings / rpb_or,
                    'rings': {'IR': ht_net_ir_rings, 'OR': ht_net_or_rings},
                    'channel': ch_name
                }

        # ==========================================
        # 4. UNLOCK ALL MACHINES (DYNAMIC DEEP SCAN)
        # ==========================================
        weight_matrix, furnace_map, furnace_rates = {}, {}, {}
        machines_data = {'FACE': {}, 'OD': {}}
        dynamic_furnace_list = set()
        
        sheets_prod, logs3 = load_excel_all_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS']
                df_w.columns = [str(x).strip().upper() for x in df_w.iloc[0]]
                for idx, r in df_w.iloc[1:].iterrows():
                    if pd.notna(r.get('TYPE')):
                        part_code = 'OR' if str(r.get('IR/OR')) == '100' else 'IR'
                        fam = parse_family(r.get('TYPE'))
                        if fam: weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('WEIGHT PER RING', 0.1))

            if 'Furnace Type Flexibility' in sheets_prod:
                df_f = sheets_prod['Furnace Type Flexibility']
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for idx, r in df_f.iloc[1:].iterrows():
                    fam = parse_family(r.get('TYPE', r.iloc[0]))
                    if fam: 
                        fur_raw = str(r.get('FURNACE', r.iloc[1] if len(r) > 1 else ''))
                        furnaces = [f.strip().upper() for f in fur_raw.replace(',', ' ').split() if f.strip()]
                        if furnaces: 
                            furnace_map[fam] = furnaces
                            dynamic_furnace_list.update(furnaces)
                        
                        cap = safe_float(r.get('CAPACITY', r.get('KG/HR', 400.0)))
                        if cap > 0: furnace_rates[fam] = cap
            
            # Deep Grid-Scan for all 18-20 Face/OD Machines
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                
                sheet_m_type = "UNKNOWN"
                if "FACE" in str(sheet_name).upper(): sheet_m_type = "FACE"
                elif "OD" in str(sheet_name).upper(): sheet_m_type = "OD"
                
                str_matrix = df_m.fillna('').astype(str).values
                for r in range(str_matrix.shape[0]):
                    row_vals = [c.strip().upper() for c in str_matrix[r]]
                    row_joined = " ".join(row_vals)
                    
                    if 'MACHINE' in row_joined or any(m in row_joined for m in ['BG', 'DDS', 'CL', 'CELL']):
                        cells = [c for c in row_vals if c and c != 'NAN']
                        if not cells: continue
                        
                        m_num = cells[0]
                        if 'MACHINE' in m_num and len(cells) > 1: m_num = cells[1]
                        
                        m_type = sheet_m_type
                        if "FACE" in row_joined or "DDS" in m_num or "BG" in m_num: m_type = "FACE"
                        elif "OD" in row_joined or "CL" in m_num or "CELL" in m_num or "+" in m_num: m_type = "OD"
                        
                        if m_type not in ['FACE', 'OD']: 
                            if sheet_m_type != "UNKNOWN": m_type = sheet_m_type
                            else: continue
                        
                        if m_num not in machines_data[m_type]:
                            machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                            
                        # Locate Rate Table Header block underneath
                        header_idx = -1
                        for offset in range(1, 10):
                            if r + offset >= str_matrix.shape[0]: break
                            h_row = [c.strip().upper() for c in str_matrix[r + offset]]
                            if any(t in h_row for t in ['TYPE', 'PART', 'PART NO']):
                                header_idx = r + offset
                                break
                                
                        if header_idx != -1:
                            headers = [c.strip().upper() for c in str_matrix[header_idx]]
                            type_col_idx, rate_col_idx, rpb_col_idx = -1, -1, -1
                            for i, h in enumerate(headers):
                                if h in ['TYPE', 'PART', 'PART NO', 'BRG NO']: type_col_idx = i
                                if 'BOX' in h or 'RATE' in h or 'STD/HR' in h or 'STD' in h: rate_col_idx = i
                                if 'RING' in h and 'BOX' in h: rpb_col_idx = i
                                
                            if type_col_idx != -1 and rate_col_idx != -1:
                                for br in range(header_idx + 1, min(header_idx + 40, str_matrix.shape[0])):
                                    t_val = str_matrix[br, type_col_idx].strip().upper()
                                    if not t_val or t_val == 'NAN': continue
                                    if 'TOTAL' in t_val: break 
                                    
                                    fam = parse_family(t_val)
                                    if not fam: continue
                                    
                                    r_val = safe_float(str_matrix[br, rate_col_idx])
                                    if r_val == 0: continue
                                    
                                    if 'STD' in headers[rate_col_idx]:
                                        rpb = safe_float(str_matrix[br, rpb_col_idx]) if rpb_col_idx != -1 else 100
                                        if rpb == 0: rpb = 100
                                        r_val = r_val / rpb
                                        
                                    p_codes = ['IR', 'OR']
                                    if '100' in t_val or 'OR' in t_val: p_codes = ['OR']
                                    elif '010' in t_val or 'IR' in t_val: p_codes = ['IR']
                                    
                                    for pc in p_codes:
                                        machines_data[m_type][m_num]['rates'][f"{fam}_{pc}"] = r_val
            del sheets_prod
            gc.collect()

        # ==========================================
        # 5. ALLOTMENT: FACE & OD GRINDING SCHEDULER
        # ==========================================
        def allocate_grinding(m_type, demands_dict):
            allocated_result = []
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            working_demands = {fam: {'IR': data['IR'], 'OR': data['OR']} for fam, data in sorted_fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                if not rates: continue
                
                selected_rows = []
                hours_left = m_info['avail_hours'] 
                current_fam = None
                
                for fam, _ in sorted_fams:
                    if hours_left <= 0 or len(selected_rows) >= 6: break
                    for p_code in ['IR', 'OR']:
                        boxes_needed = working_demands[fam][p_code]
                        if boxes_needed <= 0: continue
                        
                        part_key = f"{fam}_{p_code}"
                        # Try exact match, fallback to HUB/T generics
                        rate = rates.get(part_key, 0.0)
                        if rate == 0.0 and fam.startswith("HUB"): rate = rates.get(f"HUB_{p_code}", 0.0)
                        if rate == 0.0 and fam.startswith("T"): rate = rates.get(f"T_{p_code}", 0.0)
                        
                        if rate > 0:
                            setup_cost = 1.0 if (current_fam and current_fam != fam) else 0.0
                                
                            if hours_left <= setup_cost:
                                hours_left = 0.0
                                break
                                
                            hours_left -= setup_cost
                            time_required = boxes_needed / rate
                            
                            if time_required <= hours_left:
                                working_demands[fam][p_code] = 0.0
                                hours_left -= time_required
                            else:
                                working_demands[fam][p_code] -= (hours_left * rate)
                                hours_left = 0.0
                                
                            current_fam = fam
                            selected_rows.append({
                                "part": f"{fam} {p_code}",
                                "std_box": str(round(rate, 1)),
                                "p_2nd": "1" if len(selected_rows) == 0 else "",
                                "p_3rd": "1" if len(selected_rows) == 1 else "",
                                "alert": False,
                                "p_label": f"P{len(selected_rows) + 1}"
                            })
                            if hours_left <= 0 or len(selected_rows) >= 6: break
                
                if selected_rows:
                    allocated_result.append({"machine": m_num, "rows": selected_rows})
            return allocated_result

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # ==========================================
        # 6. ALLOTMENT: DYNAMIC HEAT TREATMENT FURNACES
        # ==========================================
        all_furnaces_to_use = list(dynamic_furnace_list) if dynamic_furnace_list else ["AICHELIN.(896)", "BATCH FURNACE"]
        furnace_clocks = {f: {"avail_hours": 24.0, "current_fam": None, "rows": []} for f in all_furnaces_to_use}

        for fam, data in sorted(ht_req.items(), key=lambda x: x[1]['rings']['IR'] + x[1]['rings']['OR'], reverse=True):
            rings_ir = data['rings']['IR']
            rings_or = data['rings']['OR']
            if rings_ir <= 0 and rings_or <= 0: continue
            
            preferred_furnaces = furnace_map.get(fam, [])
            if not preferred_furnaces:
                if fam.startswith("HUB") and "HUB" in furnace_map: preferred_furnaces = furnace_map["HUB"]
                elif fam.startswith("THUB") and "THUB" in furnace_map: preferred_furnaces = furnace_map["THUB"]
                elif fam.startswith("T") and "T" in furnace_map: preferred_furnaces = furnace_map["T"]
            if not preferred_furnaces:
                preferred_furnaces = [all_furnaces_to_use[0]]
                
            kg_per_hr = furnace_rates.get(fam, 400.0)
            if kg_per_hr == 400.0:
                if fam.startswith("HUB") and "HUB" in furnace_rates: kg_per_hr = furnace_rates["HUB"]
                elif fam.startswith("T") and "T" in furnace_rates: kg_per_hr = furnace_rates["T"]
            
            w_ir = weight_matrix.get(f"{fam}_IR", 0.15)
            w_or = weight_matrix.get(f"{fam}_OR", 0.15)
            
            for p_code, qty in [('IR', rings_ir), ('OR', rings_or)]:
                if qty <= 0: continue
                unit_weight = w_or if p_code == 'OR' else w_ir
                total_weight_kg = qty * unit_weight
                
                allocated = False
                for fur in preferred_furnaces:
                    if fur not in furnace_clocks: furnace_clocks[fur] = {"avail_hours": 24.0, "current_fam": None, "rows": []}
                    ctx = furnace_clocks[fur]
                    setup_penalty = 2.0 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                    
                    if ctx["avail_hours"] > setup_penalty:
                        ctx["avail_hours"] -= setup_penalty
                        time_needed = total_weight_kg / kg_per_hr
                        
                        if time_needed <= ctx["avail_hours"]:
                            run_qty = qty
                            ctx["avail_hours"] -= time_needed
                        else:
                            run_qty = math.floor(ctx["avail_hours"] * kg_per_hr / unit_weight)
                            ctx["avail_hours"] = 0.0
                            
                        if run_qty > 0:
                            ctx["current_fam"] = fam
                            ctx["rows"].append({
                                "part": f"{fam}-{p_code}", "qty": str(int(run_qty)), "cha": data['channel'],
                                "rate": str(round(run_qty * unit_weight / 24.0, 2)), "alert": False
                            })
                            allocated = True
                            break
                            
                if not allocated:
                    sorted_backups = sorted(furnace_clocks.keys(), key=lambda f: furnace_clocks[f]["avail_hours"], reverse=True)
                    for fur in sorted_backups:
                        ctx = furnace_clocks[fur]
                        setup_penalty = 2.0 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                        if ctx["avail_hours"] > setup_penalty:
                            ctx["avail_hours"] -= setup_penalty
                            time_needed = total_weight_kg / kg_per_hr
                            if time_needed <= ctx["avail_hours"]:
                                run_qty = qty
                                ctx["avail_hours"] -= time_needed
                            else:
                                run_qty = math.floor(ctx["avail_hours"] * kg_per_hr / unit_weight)
                                ctx["avail_hours"] = 0.0
                                
                            if run_qty > 0:
                                ctx["current_fam"] = fam
                                ctx["rows"].append({
                                    "part": f"{fam}-{p_code}", "qty": str(int(run_qty)), "cha": data['channel'],
                                    "rate": str(round(run_qty * unit_weight / 24.0, 2)), "alert": False
                                })
                                break

        ht_formatted = [
            {"furnace": fur, "capacity": str(int(furnace_rates.get(f_data["rows"][0]["part"].split('-')[0], 400))), "rows": f_data["rows"]}
            for fur, f_data in furnace_clocks.items() if len(f_data["rows"]) > 0
        ]

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {
                "face_grinding": final_face,
                "od_grinding": final_od,
                "heat_treatment": ht_formatted
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs + [f"CRITICAL ERROR: {traceback.format_exc()}"], "detail": str(e)}
