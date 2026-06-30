import os
import re
import pandas as pd
import numpy as np
import requests
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import math

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

FAM_REGEX = re.compile(r'(\d{3,5})')

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str  # 'Boxes' or 'Days'
    entries: Dict[str, Any] # Buffer entries from UI
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
    try:
        return float(str(val).replace(',', '').strip())
    except:
        return 0.0

# --- DIAGNOSTIC EXCEL LOADER ---
def load_excel_fast(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "":
        logs.append(f"[{file_label}] FAILED: URL is empty.")
        return None, logs
    try:
        logs.append(f"[{file_label}] Attempting to fetch URL...")
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None, logs
        content = io.BytesIO(resp.content)
        try: 
            xls = pd.ExcelFile(content, engine='calamine')
            logs.append(f"[{file_label}] SUCCESS (calamine).")
            return xls, logs
        except Exception: 
            xls = pd.ExcelFile(content)
            return xls, logs
    except Exception as e:
        logs.append(f"[{file_label}] FAILED: {str(e)}")
        return None, logs

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # WE NOW JUST LOOK FOR THE INTEGER DAY (e.g., 1, 2, 3...)
        req_d = str(req_date.day)
        nxt_d = str(next_date.day)
        
        # 1. READ ZEROSET
        total_demand, daily_demand = {}, {}
        xls_zero, logs1 = load_excel_fast(ZEROSET_URL, "ZEROSET_URL")
        debug_logs.extend(logs1)
        
        if xls_zero:
            for sheet_name in xls_zero.sheet_names:
                df_zero = pd.read_excel(xls_zero, sheet_name=sheet_name, header=None)
                r_idx, type_col_idx, c1, c2 = None, None, None, None
                
                for i, row in df_zero.iterrows():
                    row_strs = [str(x).strip().upper() for x in row.values]
                    row_joined = " ".join(row_strs)
                    
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF"] or "TYPE" in val or "MF" in val:
                                type_col_idx = j
                                
                    if 'MTD' in row_joined or 'PKWIP' in row_joined:
                        r_idx = i
                        for j, val in enumerate(row.values):
                            if pd.isna(val): continue
                            
                            # EXACT MATCH FOR INTEGER DAYS (1, 2, 3...)
                            val_str = str(val).strip()
                            if val_str == req_d or val_str == f"{req_d}.0": c1 = j
                            if val_str == nxt_d or val_str == f"{nxt_d}.0": c2 = j
                                    
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    if c1 is not None or c2 is not None:
                        debug_logs.append(f"[ZEROSET] MATCHED DAY {req_d} (Col {c1}) & DAY {nxt_d} (Col {c2}) in sheet '{sheet_name}'.")
                    else:
                        debug_logs.append(f"[ZEROSET] Found row but COULD NOT FIND day {req_d} or {nxt_d} in sheet '{sheet_name}'.")
                        
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam: continue
                        
                        r1 = safe_float(df_zero.iloc[idx, c1]) * 1000 if c1 is not None else 0
                        r2 = safe_float(df_zero.iloc[idx, c2]) * 1000 if c2 is not None else 0
                        
                        if r1 > 0 or r2 > 0:
                            total_demand[fam] = total_demand.get(fam, 0) + r1 + r2
                            daily_demand[fam] = daily_demand.get(fam, 0) + ((r1 + r2) / 2)

        # 2. READ BOXES & PREPARE BUFFER LOGIC
        box_matrix = {}
        xls_box, logs2 = load_excel_fast(BOX_RING_DATA_URL, "BOX_RING_DATA_URL")
        if xls_box and 'RING PER BOX.' in xls_box.sheet_names:
            df_box = pd.read_excel(xls_box, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                if pd.notna(r.iloc[0]): 
                    fam = parse_family(r.iloc[0])
                    if fam: box_matrix[fam] = {'OR': safe_float(r.get('O/R', 100)), 'IR': safe_float(r.get('I/R', 100))}

        # --- DEDUCT BUFFER FROM DEMAND ---
        # NOTE: This subtracts UI input buffers (converted if needed) from the total demand.
        # It handles the logic you requested (Days -> Boxes -> Rings subtraction).
        for block_id, entry in payload.entries.items():
            fam = parse_family(entry.get('type', ''))
            if fam and fam in daily_demand:
                ir_buf = safe_float(entry.get('IR', 0))
                or_buf = safe_float(entry.get('OR', 0))
                
                # If UI is in days, convert to rings based on daily demand
                if payload.unit_mode == 'Days':
                    ir_deduct_rings = ir_buf * daily_demand[fam]
                    or_deduct_rings = or_buf * daily_demand[fam]
                else:
                    # UI is in boxes, convert to rings based on ring/box matrix
                    ir_deduct_rings = ir_buf * box_matrix.get(fam, {}).get('IR', 100)
                    or_deduct_rings = or_buf * box_matrix.get(fam, {}).get('OR', 100)
                
                # Subtract from total demand (rough aggregate for now)
                daily_demand[fam] = max(0, daily_demand[fam] - ((ir_deduct_rings + or_deduct_rings) / 2))

        # 3. READ MACHINES & FURNACES
        weight_matrix, furnace_map, machines_data = {}, {}, {'FACE': {}, 'OD': {}}
        xls_prod, logs3 = load_excel_fast(SHO_PRODUCTION_URL, "SHO_PRODUCTION_URL")
        debug_logs.extend(logs3)
        
        m_count = 0
        if xls_prod:
            if 'WEIGHTS' in xls_prod.sheet_names:
                df_w = pd.read_excel(xls_prod, sheet_name='WEIGHTS')
                for _, r in df_w.iterrows():
                    if pd.notna(r.get('Type')):
                        part_code = 'OR' if str(r.get('ir/or')) == '100' else 'IR'
                        fam = parse_family(r.get('Type'))
                        if fam: weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('weight per ring', 0.1))

            if 'Furnace Type Flexibility' in xls_prod.sheet_names:
                df_f = pd.read_excel(xls_prod, sheet_name='Furnace Type Flexibility')
                for _, r in df_f.iterrows():
                    if pd.notna(r.iloc[0]): 
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
                                m_count += 1
                                if m_num not in machines_data[m_type]:
                                    machines_data[m_type][m_num] = {'name': m_num, 'rates': {}}
                                
                                headers = df_m.iloc[r+1]
                                block = df_m.iloc[r+2:r+20].copy()
                                block.columns = headers
                                if 'TYPE' in block.columns and 'PART' in block.columns:
                                    for _, row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(row['TYPE'])
                                        if not fam: continue
                                        p_code = 'OR' if '100' in str(row['PART']) else 'IR'
                                        
                                        boxes_hr = safe_float(row.get('Boxes/hr', 0))
                                        if boxes_hr == 0 and pd.notna(row.get('STD/HR')):
                                            rpb = safe_float(row.get('Rings/Box', 100)) or 100
                                            boxes_hr = safe_float(row.get('STD/HR')) / rpb
                                        
                                        machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr

        # --- 4. CORE MATH: ASSIGN TO MACHINES ---
        debug_logs.append(f"Processing remaining demands for {len(total_demand)} specific families after buffer deductions.")
        
        sorted_fams = sorted(daily_demand.items(), key=lambda x: x[1], reverse=True)
        assigned_parts = {'FACE': set(), 'OD': set()}

        def assign_machines(m_type):
            result = []
            for m_num, m_info in machines_data[m_type].items():
                rates = m_info.get('rates', {})
                if not rates: continue
                
                candidates = []
                for fam, dem in sorted_fams:
                    if dem <= 0: continue
                    for p_code in ['IR', 'OR']:
                        fp = f"{fam}_{p_code}"
                        if fp in rates and rates[fp] > 0:
                            candidates.append({
                                'part': fp.replace('_', ' '),
                                'std_box': round(rates[fp], 1),
                                'demand': dem
                            })
                
                selected = []
                for c in candidates:
                    if c['part'] not in assigned_parts[m_type]:
                        selected.append(c)
                        assigned_parts[m_type].add(c['part'])
                    if len(selected) >= 2: break
                
                if len(selected) < 2:
                    for c in candidates:
                        if c not in selected: selected.append(c)
                        if len(selected) >= 2: break

                if selected:
                    rows = []
                    if len(selected) > 0:
                        rows.append({"part": selected[0]['part'], "std_box": selected[0]['std_box'], "p_2nd": "1", "p_3rd": "1" if len(selected) == 1 else "", "alert": False, "p_label": "P1"})
                    if len(selected) > 1:
                        rows.append({"part": selected[1]['part'], "std_box": selected[1]['std_box'], "p_2nd": "", "p_3rd": "1", "alert": False, "p_label": "P2"})
                    result.append({"machine": m_num, "rows": rows})
            return result

        result_face = assign_machines('FACE')
        result_od = assign_machines('OD')

        # 5. ASSIGN HEAT TREATMENT
        result_ht = {}
        for fam, dem in sorted_fams:
            if dem <= 0: continue
            
            fur = furnace_map.get(fam, "AICHELIN.(896)") 
            if fur not in result_ht: result_ht[fur] = []
            
            w_ir = weight_matrix.get(f"{fam}_IR", 0.1)
            w_or = weight_matrix.get(f"{fam}_OR", 0.1)
            total_w = dem * (w_ir + w_or)
            
            result_ht[fur].append({
                "part": fam,
                "qty": round(dem),
                "cha": "T3", 
                "rate": round(total_w, 2),
                "alert": False
            })

        ht_formatted = [{"furnace": fur, "capacity": "500", "rows": items[:5]} for fur, items in result_ht.items()]

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {
                "face_grinding": result_face,
                "od_grinding": result_od,
                "heat_treatment": ht_formatted
            }
        }
        
    except Exception as e:
        import traceback
        debug_logs.append(f"CRITICAL BACKEND CRASH: {traceback.format_exc()}")
        return {"status": "error", "debug_logs": debug_logs, "detail": str(e)}
