import os
import re
import math
import pandas as pd
import requests
import io
import time
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
    unit_mode: str # 'Days', 'Boxes', 'Rings'
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if "INDUSTRILA" in text: text = text.replace("INDUSTRILA", "INDUSTRIAL")
    if "AUTOMOTIVE" in text: return None
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
    if not url or url.strip() == "": return None, logs
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code != 200:
                time.sleep(2)
                continue
            content = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk: content.write(chunk)
            content.seek(0)
            try: return pd.ExcelFile(content, engine='calamine'), logs
            except: return pd.ExcelFile(content), logs
        except Exception as e:
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
        
        channel_demands = {} # Store demand per channel and family
        
        # 1. READ ZEROSET (Extract demand by Channel/Sheet)
        xls_zero, logs1 = load_excel_fast(ZEROSET_URL, "ZEROSET")
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
                    channel_demands[sheet_name] = {}
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam: continue
                        
                        r1 = safe_float(df_zero.iloc[idx, c1]) * 1000 if c1 is not None else 0
                        r2 = safe_float(df_zero.iloc[idx, c2]) * 1000 if c2 is not None else 0
                        
                        if r1 > 0 or r2 > 0:
                            channel_demands[sheet_name][fam] = ((r1 + r2) / 2) # Daily demand in RINGS

        # 2. READ BOXES MATRIX
        box_matrix = {}
        xls_box, _ = load_excel_fast(BOX_RING_DATA_URL, "BOX_RING_DATA")
        if xls_box and 'RING PER BOX.' in xls_box.sheet_names:
            df_box = pd.read_excel(xls_box, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                fam = parse_family(r.iloc[0])
                if fam: box_matrix[fam] = {'OR': safe_float(r.get('O/R', 100)), 'IR': safe_float(r.get('I/R', 100))}

        # 3. CALCULATE STAGE-WISE BUFFER AND TRUE DEMAND
        # Schedule dictionaries specific to operations
        ht_schedule_req = {}
        face_schedule_req = {}
        od_schedule_req = {}

        for channel, fams in channel_demands.items():
            # For this MVP logic step, we'll map the UI entries to the families
            # In a full app, the UI entries should strictly link to the Channel + Family
            for fam, rings_req in fams.items():
                ir_rings_per_box = box_matrix.get(fam, {}).get('IR', 100)
                or_rings_per_box = box_matrix.get(fam, {}).get('OR', 100)
                
                req_boxes_ir = rings_req / ir_rings_per_box if ir_rings_per_box else 0
                req_boxes_or = rings_req / or_rings_per_box if or_rings_per_box else 0
                
                # Fetch Buffer from UI payload (matching by family for now)
                ir_buf_val = 0
                or_buf_val = 0
                for _, entry in payload.entries.items():
                    if parse_family(entry.get('type', '')) == fam:
                        ir_buf_val = safe_float(entry.get('IR', 0))
                        or_buf_val = safe_float(entry.get('OR', 0))
                        break

                # Convert Buffer into BOXES based on UI unit mode
                if payload.unit_mode == 'Days':
                    buf_boxes_ir = ir_buf_val * req_boxes_ir
                    buf_boxes_or = or_buf_val * req_boxes_or
                elif payload.unit_mode == 'Rings':
                    buf_boxes_ir = ir_buf_val / ir_rings_per_box if ir_rings_per_box else 0
                    buf_boxes_or = or_buf_val / or_rings_per_box if or_rings_per_box else 0
                else:
                    buf_boxes_ir = ir_buf_val
                    buf_boxes_or = or_buf_val

                # CORE LOGIC: Stage by stage deductions (Assuming standard flow: HT -> Face -> OD)
                # If buffer is sitting at OD, HT and Face are already done. 
                # This requires knowing exactly where the buffer was logged.
                # Assuming standard buffer acts as total WIP ahead of the current bottleneck:
                
                net_ir_boxes = max(0, req_boxes_ir - buf_boxes_ir)
                net_or_boxes = max(0, req_boxes_or - buf_boxes_or)
                
                if net_ir_boxes > 0 or net_or_boxes > 0:
                    face_schedule_req[fam] = {'IR': net_ir_boxes, 'OR': net_or_boxes, 'channel': channel}
                    od_schedule_req[fam] = {'IR': net_ir_boxes, 'OR': net_or_boxes, 'channel': channel}
                    ht_schedule_req[fam] = {'IR': net_ir_boxes, 'OR': net_or_boxes, 'channel': channel}

        # 4. READ MACHINES & FURNACES
        furnace_map, machines_data = {}, {'FACE': {}, 'OD': {}}
        xls_prod, logs3 = load_excel_fast(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        
        if xls_prod:
            if 'Furnace Type Flexibility' in xls_prod.sheet_names:
                df_f = pd.read_excel(xls_prod, sheet_name='Furnace Type Flexibility')
                for _, r in df_f.iterrows():
                    fam = parse_family(r.iloc[0])
                    if fam: furnace_map[fam] = str(r.iloc[1]).strip()
            
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
                                    # Setup time default applied here (e.g., 30 mins)
                                    machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 23.5}
                                
                                headers = df_m.iloc[r+1]
                                block = df_m.iloc[r+2:r+20].copy()
                                block.columns = headers
                                if 'TYPE' in block.columns and 'PART' in block.columns:
                                    for _, row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(row['TYPE'])
                                        if not fam: continue
                                        p_code = 'OR' if '100' in str(row['PART']) else 'IR'
                                        
                                        boxes_hr = safe_float(row.get('Boxes/hr', 0))
                                        machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr

        # 5. ALLOCATE CONSIDERING CAPACITY AND SETUP TIMES
        def allocate(m_type, demands):
            result = []
            assigned_families = set()
            
            for m_num, m_info in machines_data[m_type].items():
                rates = m_info.get('rates', {})
                if not rates: continue
                
                selected_rows = []
                hours_left = m_info['avail_hours']
                
                for fam, reqs in sorted(demands.items(), key=lambda x: x[1]['IR']+x[1]['OR'], reverse=True):
                    if fam in assigned_families: continue
                    
                    for p_code in ['IR', 'OR']:
                        boxes_needed = reqs[p_code]
                        if boxes_needed <= 0: continue
                        
                        part_key = f"{fam}_{p_code}"
                        if part_key in rates and rates[part_key] > 0:
                            # Factor in setup time (e.g., 1 hour per changeover)
                            if hours_left < 1: break 
                            hours_left -= 1.0 # Deduct setup time
                            
                            process_time = boxes_needed / rates[part_key]
                            if process_time <= hours_left:
                                hours_left -= process_time
                                reqs[p_code] = 0 # Fully scheduled
                            else:
                                # Partially scheduled
                                boxes_made = hours_left * rates[part_key]
                                reqs[p_code] -= boxes_made
                                hours_left = 0
                                
                            selected_rows.append({
                                "part": part_key.replace('_', ' '), 
                                "std_box": round(rates[part_key], 1), 
                                "p_2nd": "1" if len(selected_rows)==0 else "", 
                                "p_3rd": "1" if len(selected_rows)>0 else "", 
                                "alert": False,
                                "p_label": f"P{len(selected_rows)+1}"
                            })
                            
                    if reqs['IR'] <= 0 and reqs['OR'] <= 0:
                        assigned_families.add(fam)
                        
                    if hours_left <= 0 or len(selected_rows) >= 2: break
                    
                if selected_rows:
                    result.append({"machine": m_num, "rows": selected_rows})
            return result

        final_face = allocate('FACE', face_schedule_req)
        final_od = allocate('OD', od_schedule_req)

        # 6. HEAT TREATMENT ALLOCATION
        result_ht = {}
        for fam, reqs in ht_schedule_req.items():
            total_boxes = reqs['IR'] + reqs['OR']
            if total_boxes <= 0: continue
            
            fur = furnace_map.get(fam, "AICHELIN.(896)")
            if fur not in result_ht: result_ht[fur] = []
            
            result_ht[fur].append({
                "part": fam,
                "qty": round(total_boxes * box_matrix.get(fam, {}).get('IR', 100)), # Simplified back to rings
                "cha": reqs['channel'], 
                "rate": "N/A", # Will need weight matrix for accurate Kg/Hr
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
        return {"status": "error", "debug_logs": debug_logs, "detail": traceback.format_exc()}
