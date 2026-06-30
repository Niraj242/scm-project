import os
import re
import math
import pandas as pd
import requests
import io
import time
import gc  # Added for memory management
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

FAM_REGEX = re.compile(r'(\d{3,5})')

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

# --- HEALTH CHECK (To test if your server deployed correctly) ---
@router.get("/api/health")
def health_check():
    return {"status": "Backend is ALIVE and successfully deployed."}

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", ""]: return "UNKNOWN"
    
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
        f_val = float(s_val)
        return 0.0 if math.isnan(f_val) else f_val
    except Exception:
        return 0.0

def load_excel_fast(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "":
        logs.append(f"[{file_label}] FAILED: URL is empty.")
        return None, logs
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logs.append(f"[{file_label}] Attempt {attempt + 1}: Fetching URL...")
            resp = requests.get(url, timeout=(10, 60), stream=True)
            if resp.status_code != 200:
                time.sleep(2)
                continue
            content = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk: content.write(chunk)
            content.seek(0)
            logs.append(f"[{file_label}] Downloaded {content.getbuffer().nbytes} bytes.")
            try: 
                xls = pd.ExcelFile(content, engine='calamine')
                logs.append(f"[{file_label}] SUCCESS (calamine).")
                return xls, logs
            except Exception: 
                xls = pd.ExcelFile(content)
                logs.append(f"[{file_label}] SUCCESS (openpyxl).")
                return xls, logs
        except Exception as e:
            logs.append(f"[{file_label}] ERROR: {str(e)}")
            if attempt == max_retries - 1: return None, logs
            time.sleep(2)
    return None, logs

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        req_d, nxt_d = str(req_date.day), str(next_date.day)
        
        # ==========================================
        # 1. READ ZEROSET (Pipeline Demand)
        # ==========================================
        channel_demands = {} 
        xls_zero, logs1 = load_excel_fast(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if xls_zero:
            for sheet_name in xls_zero.sheet_names:
                df_zero = pd.read_excel(xls_zero, sheet_name=sheet_name, header=None)
                r_idx, type_col_idx, c1, c2 = None, None, None, None
                for i, row in df_zero.iterrows():
                    row_strs = [str(x).strip().upper() for x in row.values]
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF"] or "TYPE" in val: type_col_idx = j
                    if 'MTD' in " ".join(row_strs) or 'PKWIP' in " ".join(row_strs):
                        r_idx = i
                        for j, val in enumerate(row.values):
                            if pd.isna(val): continue
                            v_str = str(val).strip()
                            if v_str in [req_d, f"{req_d}.0"]: c1 = j
                            if v_str in [nxt_d, f"{nxt_d}.0"]: c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    if c1 is not None or c2 is not None:
                        debug_logs.append(f"[ZEROSET] MATCHED DAY {req_d} (Col {c1}) & DAY {nxt_d} (Col {c2}) in sheet '{sheet_name}'.")
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam or fam == "UNKNOWN": continue
                        r1 = safe_float(df_zero.iloc[idx, c1]) * 1000 if c1 is not None else 0
                        r2 = safe_float(df_zero.iloc[idx, c2]) * 1000 if c2 is not None else 0
                        if r1 > 0 or r2 > 0:
                            if fam not in channel_demands: channel_demands[fam] = {'IR': 0, 'OR': 0, 'channel': sheet_name}
                            channel_demands[fam]['IR'] += ((r1 + r2) / 2)
                            channel_demands[fam]['OR'] += ((r1 + r2) / 2)
            
            # FREE MEMORY to prevent server crash
            del xls_zero
            gc.collect()

        # ==========================================
        # 2. READ BOXES MATRIX
        # ==========================================
        box_matrix = {}
        xls_box, logs2 = load_excel_fast(BOX_RING_DATA_URL, "BOX_RING_DATA")
        if xls_box and 'RING PER BOX.' in xls_box.sheet_names:
            df_box = pd.read_excel(xls_box, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                fam = parse_family(r.iloc[0])
                if fam and fam != "UNKNOWN": box_matrix[fam] = {'OR': safe_float(r.get('O/R', 100)), 'IR': safe_float(r.get('I/R', 100))}
            
            # FREE MEMORY
            del xls_box
            gc.collect()

        # ==========================================
        # 3. PARSE UI BUFFER ENTRIES 
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
                    suffix = key[len(type_prefix + '_'):]
                    fam = parse_family(val)
                    if not fam or fam == "UNKNOWN": continue
                    
                    buf_key = f"{buf_prefix}_{suffix}"
                    buf_val = safe_float(payload.entries.get(buf_key, 0))
                    
                    if buf_val <= 0: continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {'CH': {'IR':0, 'OR':0}, 'OD': {'IR':0, 'OR':0}, 'FACE': {'IR':0, 'OR':0}, 'HT': {'IR':0, 'OR':0}}
                    
                    sub_col = 'OR' if suffix.endswith('_OR') else 'IR'
                    buffers_by_fam[fam][stage][sub_col] += buf_val

        debug_logs.append(f"Successfully linked buffers to {len(buffers_by_fam)} families.")

        # ==========================================
        # 4. CALCULATE NET DEMAND & APPLY UNITS
        # ==========================================
        od_req, face_req, ht_req = {}, {}, {}

        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
            req_boxes_ir = demands['IR'] / rpb_ir if rpb_ir else 0
            req_boxes_or = demands['OR'] / rpb_or if rpb_or else 0
            
            # THE UNIT CONVERSION HAPPENS EXACTLY HERE:
            def get_buf_boxes(stage, p_code, req_boxes, rpb):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(p_code, 0)
                if payload.unit_mode == 'Days': return raw_buf * req_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb if rpb else 0
                else: return raw_buf # Box mode
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_boxes_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_boxes_or, rpb_or)
            
            od_buf_ir = get_buf_boxes('OD', 'IR', req_boxes_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_boxes_or, rpb_or)
            
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_boxes_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_boxes_or, rpb_or)

            # Deductions
            net_od_ir = max(0, req_boxes_ir - ch_buf_ir)
            net_od_or = max(0, req_boxes_or - ch_buf_or)
            
            net_face_ir = max(0, net_od_ir - od_buf_ir)
            net_face_or = max(0, net_od_or - od_buf_or)
            
            net_ht_ir = max(0, net_face_ir - face_buf_ir)
            net_ht_or = max(0, net_face_or - face_buf_or)

            if net_od_ir > 0 or net_od_or > 0: od_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': demands['channel']}
            if net_face_ir > 0 or net_face_or > 0: face_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': demands['channel']}
            if net_ht_ir > 0 or net_ht_or > 0: ht_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'channel': demands['channel']}

        debug_logs.append(f"Net Pipeline Demand -> OD: {len(od_req)} | FACE: {len(face_req)} | HT: {len(ht_req)}")

        # ==========================================
        # 5. READ MACHINES & FURNACES
        # ==========================================
        weight_matrix, furnace_map, machines_data = {}, {}, {'FACE': {}, 'OD': {}}
        xls_prod, logs3 = load_excel_fast(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        
        if xls_prod:
            if 'WEIGHTS' in xls_prod.sheet_names:
                df_w = pd.read_excel(xls_prod, sheet_name='WEIGHTS')
                for _, r in df_w.iterrows():
                    if pd.notna(r.get('Type')):
                        part_code = 'OR' if str(r.get('ir/or')) == '100' else 'IR'
                        fam = parse_family(r.get('Type'))
                        if fam and fam != "UNKNOWN": weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('weight per ring', 0.1))

            if 'Furnace Type Flexibility' in xls_prod.sheet_names:
                df_f = pd.read_excel(xls_prod, sheet_name='Furnace Type Flexibility')
                for _, r in df_f.iterrows():
                    if pd.notna(r.iloc[0]): 
                        fam = parse_family(r.iloc[0])
                        if fam and fam != "UNKNOWN": furnace_map[fam] = str(r.iloc[1]).strip()
            
            for sheet in xls_prod.sheet_names:
                if sheet in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                df_m = pd.read_excel(xls_prod, sheet_name=sheet, header=None)
                str_matrix = df_m.fillna('').astype(str).values
                for r in range(str_matrix.shape[0]):
                    for c in range(str_matrix.shape[1]):
                        if str_matrix[r, c].strip().upper() == 'MACHINE':
                            m_num = str(df_m.iloc[r, c+1]).strip()
                            m_type = str(df_m.iloc[r, c+2]).strip().upper()
                            
                            if m_type in ['FACE', 'OD']:
                                if m_num not in machines_data[m_type]:
                                    machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 16.0}
                                
                                headers = [str(col_val).strip().upper() for col_val in df_m.iloc[r+1].values]
                                block = df_m.iloc[r+2:r+20].copy()
                                block.columns = headers
                                
                                if 'TYPE' in block.columns and 'PART' in block.columns:
                                    for _, row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(row['TYPE'])
                                        if not fam or fam == "UNKNOWN": continue
                                        p_code = 'OR' if '100' in str(row['PART']) else 'IR'
                                        
                                        boxes_hr = safe_float(row.get('BOXES/HR', 0))
                                        if boxes_hr == 0 and pd.notna(row.get('STD/HR')):
                                            rpb = safe_float(row.get('RINGS/BOX', 100)) or 100
                                            boxes_hr = safe_float(row.get('STD/HR')) / rpb
                                        
                                        machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr
            
            # FREE MEMORY
            del xls_prod
            gc.collect()

        # ==========================================
        # 6. ALLOCATE WITH DYNAMIC SETUP PENALTY
        # ==========================================
        def allocate(m_type, demands):
            result = []
            assigned_parts = set()
            sorted_demands = sorted(demands.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            
            for m_num, m_info in machines_data[m_type].items():
                rates = m_info.get('rates', {})
                if not rates: continue
                
                selected_rows = []
                hours_left = m_info['avail_hours']
                
                for fam, reqs in sorted_demands:
                    for p_code in ['IR', 'OR']:
                        boxes_needed = reqs[p_code]
                        part_key = f"{fam}_{p_code}"
                        
                        if boxes_needed > 0 and part_key in rates and rates[part_key] > 0 and part_key not in assigned_parts:
                            setup_time = 0.5 
                            if hours_left < setup_time: continue 
                            hours_left -= setup_time
                            
                            process_time = boxes_needed / rates[part_key]
                            if process_time <= hours_left:
                                hours_left -= process_time
                                reqs[p_code] = 0
                            else:
                                boxes_made = hours_left * rates[part_key]
                                reqs[p_code] -= boxes_made
                                hours_left = 0
                                
                            assigned_parts.add(part_key)
                            selected_rows.append({
                                "part": part_key.replace('_', ' '), 
                                "std_box": round(rates[part_key], 1), 
                                "p_2nd": "1" if len(selected_rows) == 0 else "", 
                                "p_3rd": "1" if len(selected_rows) > 0 else "", 
                                "alert": False,
                                "p_label": f"P{len(selected_rows)+1}"
                            })
                            if hours_left <= 0 or len(selected_rows) >= 2: break
                    if hours_left <= 0 or len(selected_rows) >= 2: break
                
                if selected_rows:
                    result.append({"machine": m_num, "rows": selected_rows})
            return result

        final_face = allocate('FACE', face_req)
        final_od = allocate('OD', od_req)

        # ==========================================
        # 7. HEAT TREATMENT ALLOCATION
        # ==========================================
        result_ht = {}
        for fam, reqs in ht_req.items():
            if reqs['IR'] <= 0 and reqs['OR'] <= 0: continue
            fur = furnace_map.get(fam, "AICHELIN.(896)")
            if fur not in result_ht: result_ht[fur] = []
            
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
            total_rings = (reqs['IR'] * rpb_ir) + (reqs['OR'] * rpb_or)
            w_ir = weight_matrix.get(f"{fam}_IR", 0.1)
            w_or = weight_matrix.get(f"{fam}_OR", 0.1)
            total_weight = (reqs['IR'] * rpb_ir * w_ir) + (reqs['OR'] * rpb_or * w_or)
            
            result_ht[fur].append({
                "part": fam,
                "qty": round(total_rings),
                "cha": reqs['channel'], 
                "rate": round(total_weight, 2),
                "alert": False
            })

        ht_formatted = [{"furnace": fur, "capacity": "500", "rows": items[:5]} for fur, items in result_ht.items()]

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
        debug_logs.append(f"CRITICAL ERROR: {traceback.format_exc()}")
        return {"status": "error", "debug_logs": debug_logs, "detail": traceback.format_exc()}
