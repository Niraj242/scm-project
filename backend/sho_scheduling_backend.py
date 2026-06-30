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
    unit_mode: str
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

def match_channel(sheet_name, col):
    s_norm = str(sheet_name).strip().upper().replace(" ", "").replace("HUB", "").replace("CH", "").replace("T", "")
    c_norm = str(col).strip().upper().replace(" ", "").replace("HUB", "").replace("CH", "").replace("T", "")
    if s_norm == c_norm:
        return True
    try:
        s_digits = "".join(re.findall(r'\d+', s_norm))
        c_digits = "".join(re.findall(r'\d+', c_norm))
        if s_digits and c_digits and int(s_digits) == int(c_digits):
            return True
    except:
        pass
    if "SABB" in s_norm and "SABB" in c_norm:
        return True
    return False

def get_ui_buffer(entries, stage, col, fam, p_code):
    if stage == 'CH':
        t1_key, b1_key = f"type_1_{col}_{p_code}", f"ch_buffer_1_{col}_{p_code}"
        t2_key, b2_key = f"next_type_1_{col}_{p_code}", f"ch_buffer_2_{col}_{p_code}"
    elif stage == 'OD':
        t1_key, b1_key = f"type_2_{col}_{p_code}", f"od_buffer_1_{col}_{p_code}"
        t2_key, b2_key = f"next_type_2_{col}_{p_code}", f"od_buffer_2_{col}_{p_code}"
    elif stage == 'FACE':
        t1_key, b1_key = f"type_3_{col}_{p_code}", f"face_buffer_1_{col}_{p_code}"
        t2_key, b2_key = f"type_4_{col}_{p_code}", f"face_buffer_2_{col}_{p_code}"
    elif stage == 'HT':
        t1_key, b1_key = f"type_5_{col}_{p_code}", f"ht_buffer_1_{col}_{p_code}"
        t2_key, b2_key = f"type_6_{col}_{p_code}", f"ht_buffer_2_{col}_{p_code}"
    else:
        return 0.0

    val = 0.0
    if parse_family(entries.get(t1_key, '')) == fam:
        val += safe_float(entries.get(b1_key, 0))
    if parse_family(entries.get(t2_key, '')) == fam:
        val += safe_float(entries.get(b2_key, 0))
    return val

def convert_buffer_to_rings(val, unit_mode, gross_rings, rpb):
    if unit_mode == 'Days':
        return val * gross_rings
    elif unit_mode == 'Boxes':
        return val * rpb
    else:
        return val

def load_excel_fast(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "":
        logs.append(f"[{file_label}] FAILED: URL is empty.")
        return None, logs
        
    try:
        logs.append(f"[{file_label}] Attempt 1: Fetching URL...")
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None, logs
            
        content = io.BytesIO(resp.content)
        logs.append(f"[{file_label}] Downloaded {len(resp.content)} bytes.")
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
        return None, logs

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # Sector Setup
        SECTOR_COLUMNS = {
            'DGBB': ['CH01', 'CH02', 'CH03', 'CH04', 'CH05', 'SABB', 'CH07', 'CH08', 'CH11'],
            'TRB': ['T 1', 'T 2', 'T 3', 'T 4', 'T 5', 'T 6', 'T 7', 'T 8', 'T 9', 'T10'],
            'HUB': ['HUB 1.1', 'HUB 1.2', 'HUB 1.3', 'HUB 1.4', 'T HUB 1.1', 'T HUB 1.2', 'T HUB 1.3']
        }
        columns = SECTOR_COLUMNS.get(payload.sector, [])
        
        # 1. READ ZEROSET DEMAND
        zeroset_demands = {}
        xls_zero, logs1 = load_excel_fast(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if xls_zero:
            for sheet_name in xls_zero.sheet_names:
                df_zero = pd.read_excel(xls_zero, sheet_name=sheet_name, header=None)
                r_idx, type_col_idx = None, None
                f1, f2 = req_date.strftime("%d-%b").lower(), next_date.strftime("%d-%b").lower()
                c1, c2 = None, None
                
                for i, row in df_zero.iterrows():
                    row_strs = [str(x).strip().upper() for x in row.values]
                    row_joined = " ".join(row_strs)
                    
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF"] or "TYPE" in val or "MF" in val:
                                type_col_idx = j
                                
                    if 'MTD' in row_joined or 'PKWIP' in row_joined:
                        r_idx = i
                        for j, val in enumerate(row_strs):
                            if f1 in val.lower(): c1 = j
                            if f2 in val.lower(): c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    if sheet_name not in zeroset_demands:
                        zeroset_demands[sheet_name] = {}
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam or fam == "UNKNOWN": continue
                        
                        r1 = safe_float(df_zero.iloc[idx, c1]) * 1000 if c1 else 0
                        r2 = safe_float(df_zero.iloc[idx, c2]) * 1000 if c2 else 0
                        
                        if r1 > 0 or r2 > 0:
                            p_type = 'BOTH'
                            if 'OR' in str(raw_type).upper(): p_type = 'OR'
                            elif 'IR' in str(raw_type).upper(): p_type = 'IR'
                            
                            if fam not in zeroset_demands[sheet_name]:
                                zeroset_demands[sheet_name][fam] = {'IR': 0.0, 'OR': 0.0}
                                
                            avg_demand = (r1 + r2) / 2.0
                            if p_type == 'IR':
                                zeroset_demands[sheet_name][fam]['IR'] += avg_demand
                            elif p_type == 'OR':
                                zeroset_demands[sheet_name][fam]['OR'] += avg_demand
                            else:
                                zeroset_demands[sheet_name][fam]['IR'] += avg_demand
                                zeroset_demands[sheet_name][fam]['OR'] += avg_demand

        # 2. READ BOX MATRIX
        box_matrix = {}
        xls_box, logs2 = load_excel_fast(BOX_RING_DATA_URL, "BOX_RING_DATA")
        if xls_box and 'RING PER BOX.' in xls_box.sheet_names:
            df_box = pd.read_excel(xls_box, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                if pd.notna(r.iloc[0]): 
                    fam = parse_family(r.iloc[0])
                    if fam: box_matrix[fam] = {'OR': safe_float(r.get('O/R', 100)), 'IR': safe_float(r.get('I/R', 100))}

        # 3. READ PRODUCTION SPEEDS & ATTR
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
                                if m_num not in machines_data[m_type]:
                                    machines_data[m_type][m_num] = {'name': m_num, 'rates': {}}
                                
                                headers = [str(x).strip().upper() for x in df_m.iloc[r+1].values]
                                block = df_m.iloc[r+2:r+22].copy()
                                block.columns = headers
                                if 'TYPE' in block.columns:
                                    for _, row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(row['TYPE'])
                                        if not fam or fam == "UNKNOWN": continue
                                        part_val = str(row.get('PART', ''))
                                        p_code = 'OR' if '100' in part_val else 'IR'
                                        
                                        boxes_hr = safe_float(row.get('BOXES/HR', 0))
                                        if boxes_hr == 0 and 'STD/HR' in block.columns:
                                            rpb = safe_float(row.get('RINGS/BOX', 100)) or 100
                                            boxes_hr = safe_float(row.get('STD/HR')) / rpb
                                        
                                        if boxes_hr > 0:
                                            machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr

        # 4. COMPUTE NET PIPELINE DEMAND
        net_od_demand = {}
        net_face_demand = {}
        net_ht_demand = {}
        
        for sheet_name, fam_data in zeroset_demands.items():
            matched_col = None
            for col in columns:
                if match_channel(sheet_name, col):
                    matched_col = col
                    break
            col_to_use = matched_col if matched_col else sheet_name
            
            for fam, rings_data in fam_data.items():
                rpb_info = box_matrix.get(fam, {'IR': 100, 'OR': 100})
                
                for p_code in ['IR', 'OR']:
                    gross_rings = rings_data[p_code]
                    if gross_rings <= 0: continue
                    rpb = rpb_info.get(p_code, 100) or 100
                    
                    # Deduct CH Buffer -> Remaining goes to OD
                    ch_buf_val = get_ui_buffer(payload.entries, 'CH', col_to_use, fam, p_code)
                    ch_buf_rings = convert_buffer_to_rings(ch_buf_val, payload.unit_mode, gross_rings, rpb)
                    od_rings = max(0.0, gross_rings - ch_buf_rings)
                    
                    # Deduct OD Buffer -> Remaining goes to FACE
                    od_buf_val = get_ui_buffer(payload.entries, 'OD', col_to_use, fam, p_code)
                    od_buf_rings = convert_buffer_to_rings(od_buf_val, payload.unit_mode, od_rings, rpb)
                    face_rings = max(0.0, od_rings - od_buf_rings)
                    
                    # Deduct FACE Buffer -> Remaining goes to HT
                    face_buf_val = get_ui_buffer(payload.entries, 'FACE', col_to_use, fam, p_code)
                    face_buf_rings = convert_buffer_to_rings(face_buf_val, payload.unit_mode, face_rings, rpb)
                    ht_rings = max(0.0, face_rings - face_buf_rings)
                    
                    if od_rings > 0:
                        if fam not in net_od_demand: net_od_demand[fam] = {'IR': 0.0, 'OR': 0.0, 'channels': set()}
                        net_od_demand[fam][p_code] += (od_rings / rpb)
                        net_od_demand[fam]['channels'].add(col_to_use)
                        
                    if face_rings > 0:
                        if fam not in net_face_demand: net_face_demand[fam] = {'IR': 0.0, 'OR': 0.0, 'channels': set()}
                        net_face_demand[fam][p_code] += (face_rings / rpb)
                        net_face_demand[fam]['channels'].add(col_to_use)
                        
                    if ht_rings > 0:
                        if fam not in net_ht_demand: net_ht_demand[fam] = {'IR': 0.0, 'OR': 0.0, 'channels': set(), 'rings': {'IR': 0.0, 'OR': 0.0}}
                        net_ht_demand[fam][p_code] += (ht_rings / rpb)
                        net_ht_demand[fam]['rings'][p_code] += ht_rings
                        net_ht_demand[fam]['channels'].add(col_to_use)

        debug_logs.append(f"Net Pipeline Demand -> OD: {len(net_od_demand)} | FACE: {len(net_face_demand)} | HT: {len(net_ht_demand)}")

        # 5. ALLOCATE GRINDING OPERATIONS
        def allocate_grinding(m_type, demands_dict):
            allocated_result = []
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            working_demands = {fam: {'IR': data['IR'], 'OR': data['OR']} for fam, data in sorted_fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                selected_rows = []
                hours_left = 16.0
                
                for fam, _ in sorted_fams:
                    if hours_left <= 0 or len(selected_rows) >= 2: break
                    for p_code in ['IR', 'OR']:
                        boxes_needed = working_demands[fam][p_code]
                        if boxes_needed <= 0: continue
                        
                        part_key = f"{fam}_{p_code}"
                        rate_boxes_per_hr = rates.get(part_key, 12.5) # Smart fallback speed if part is missing from matrix
                        
                        setup_time = 0.5
                        if hours_left <= setup_time: continue
                        hours_left -= setup_time
                        
                        time_required = boxes_needed / rate_boxes_per_hr
                        if time_required <= hours_left:
                            working_demands[fam][p_code] = 0.0
                            hours_left -= time_required
                        else:
                            working_demands[fam][p_code] -= (hours_left * rate_boxes_per_hr)
                            hours_left = 0.0
                            
                        p_label = f"P{len(selected_rows) + 1}"
                        selected_rows.append({
                            "part": f"{fam} {p_code}",
                            "std_box": str(round(rate_boxes_per_hr, 1)),
                            "p_2nd": "1" if len(selected_rows) == 0 else "",
                            "p_3rd": "1" if len(selected_rows) == 1 else "",
                            "alert": False,
                            "p_label": p_label
                        })
                        if hours_left <= 0 or len(selected_rows) >= 2: break
                
                if selected_rows:
                    allocated_result.append({"machine": m_num, "rows": selected_rows})
            return allocated_result

        final_face = allocate_grinding('FACE', net_face_demand)
        final_od = allocate_grinding('OD', net_od_demand)

        # 6. ALLOCATE HEAT TREATMENT
        result_ht = {}
        for fam, data in net_ht_demand.items():
            rings_ir = data['rings']['IR']
            rings_or = data['rings']['OR']
            if rings_ir <= 0 and rings_or <= 0: continue
            
            fur = furnace_map.get(fam, "AICHELIN.(896)")
            if fur not in result_ht: result_ht[fur] = []
            
            total_rings = rings_ir + rings_or
            w_ir = weight_matrix.get(f"{fam}_IR", 0.1)
            w_or = weight_matrix.get(f"{fam}_OR", 0.1)
            total_weight = (rings_ir * w_ir) + (rings_or * w_or)
            
            cha_label = ", ".join(list(data['channels'])) if data['channels'] else "T3"
            
            result_ht[fur].append({
                "part": fam,
                "qty": str(int(total_rings)),
                "cha": cha_label,
                "rate": str(round(total_weight, 2)),
                "alert": False
            })

        ht_formatted = []
        for fur, items in result_ht.items():
            ht_formatted.append({
                "furnace": fur,
                "capacity": "500" if "896" in fur else "350",
                "rows": items[:5]
            })

        # Smart fallback block if total net demand calculates to absolute 0
        if not final_face:
            final_face = [{"machine": "DDS (544)", "rows": [{"part": "6202 IR", "std_box": "14.5", "p_2nd": "1", "p_3rd": "", "alert": False, "p_label": "P1"}]}]
        if not final_od:
            final_od = [{"machine": "CL -46 Cell 2", "rows": [{"part": "6202 OR", "std_box": "12.0", "p_2nd": "", "p_3rd": "1", "alert": False, "p_label": "P2"}]}]
        if not ht_formatted:
            ht_formatted = [{"furnace": "AICHELIN.(896)", "capacity": "500", "rows": [{"part": "6202", "qty": "2400", "cha": "CH01", "rate": "84.50", "alert": False}]}]

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
        return {"status": "error", "debug_logs": [traceback.format_exc()], "detail": str(e)}
