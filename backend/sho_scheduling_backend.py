import os
import re
import math
import pandas as pd
import requests
import io
import time
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

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", "", "UNKNOWN"]: return None
    if "AUTOMOTIVE" in text: return None
    
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

def load_excel_all_sheets(url, file_label="Unknown"):
    """Downloads the excel file and parses all sheets at once into a dict of DataFrames for speed."""
    logs = []
    if not url or url.strip() == "":
        logs.append(f"[{file_label}] FAILED: URL is empty.")
        return None, logs
    
    start_time = time.time()
    for attempt in range(2):
        try:
            logs.append(f"[{file_label}] Fetching data stream...")
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                time.sleep(1)
                continue
                
            content = io.BytesIO(resp.content)
            # Read all sheets simultaneously to drastically cut execution time
            try:
                sheets_dict = pd.read_excel(content, sheet_name=None, header=None, engine='calamine')
                logs.append(f"[{file_label}] SUCCESS (calamine) in {round(time.time() - start_time, 2)}s.")
                return sheets_dict, logs
            except Exception:
                sheets_dict = pd.read_excel(content, sheet_name=None, header=None)
                logs.append(f"[{file_label}] SUCCESS (openpyxl) in {round(time.time() - start_time, 2)}s.")
                return sheets_dict, logs
        except Exception as e:
            logs.append(f"[{file_label}] Connection attempt error: {str(e)}")
            time.sleep(1)
            
    return None, logs

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # Build flexible variants for date matching (e.g., "1", "01", "1.0", "01-Apr")
        d1_variants = [str(req_date.day), f"{req_date.day}.0", req_date.strftime("%d-%b").upper(), req_date.strftime("%b-%d").upper()]
        d2_variants = [str(next_date.day), f"{next_date.day}.0", next_date.strftime("%d-%b").upper(), next_date.strftime("%b-%d").upper()]
        
        # ==========================================
        # 1. READ ZEROSET (Pipeline Demand)
        # ==========================================
        channel_demands = {} 
        sheets_zero, logs1 = load_excel_all_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                r_idx, type_col_idx, c1, c2 = None, None, None, None
                
                # Scan first 15 rows to locate data layout headers
                for i in range(min(15, len(df_zero))):
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
                            if pd.isna(val): continue
                            v_str = str(val).strip().upper()
                            if v_str in d1_variants: c1 = j
                            if v_str in d2_variants: c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None and (c1 is not None or c2 is not None):
                    # FIX: Forward-fill the merged Type column so child rows inherit part IDs
                    df_zero[type_col_idx] = df_zero[type_col_idx].ffill()
                    
                    found_count = 0
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam: continue
                        
                        # Extract quantity data (multiply decimal values by 1000 if tracking in hours/k-units)
                        val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        r1 = val1 * 1000 if 0 < val1 <= 50 else val1
                        r2 = val2 * 1000 if 0 < val2 <= 50 else val2
                        
                        if r1 > 0 or r2 > 0:
                            found_count += 1
                            if fam not in channel_demands: 
                                channel_demands[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            
                            # Aggregate demand across both targeted days
                            combined_day_qty = r1 + r2
                            is_or = 'OR' in str(raw_type).upper()
                            is_ir = 'IR' in str(raw_type).upper()
                            
                            if is_or:
                                channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], combined_day_qty)
                            elif is_ir:
                                channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], combined_day_qty)
                            else:
                                channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], combined_day_qty)
                                channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], combined_day_qty)
                                
                    if found_count > 0:
                        debug_logs.append(f"[ZEROSET] Sheet '{sheet_name}' -> Successfully extracted {found_count} demands.")
                        
            del sheets_zero
            gc.collect()

        # ==========================================
        # 2. READ BOXES MATRIX
        # ==========================================
        box_matrix = {}
        sheets_box, logs2 = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box and 'RING PER BOX.' in sheets_box:
            df_box = sheets_box['RING PER BOX.']
            # Reconstruct headers cleanly
            df_box.columns = [str(x).strip().upper() for x in df_box.iloc[0]]
            for idx, r in df_box.iloc[1:].iterrows():
                fam = parse_family(r.iloc[0])
                if fam: 
                    box_matrix[fam] = {
                        'OR': safe_float(r.get('O/R', r.get('OR', 100))), 
                        'IR': safe_float(r.get('I/R', r.get('IR', 100)))
                    }
            del sheets_box
            gc.collect()

        # ==========================================
        # 3. MAP UI LIVE BUFFER ENTRIES 
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
                    # Key syntax matches: type_1_CH01_IR
                    parts = key.split('_')
                    if len(parts) < 3: continue
                    col_channel = parts[-2]
                    sub_ring_type = parts[-1] # IR or OR
                    
                    fam = parse_family(val)
                    if not fam: continue
                    
                    # Match dynamic buffer parameter
                    buf_key = f"{buf_prefix}_{col_channel}_{sub_ring_type}"
                    buf_val = safe_float(payload.entries.get(buf_key, 0))
                    if buf_val <= 0: continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {
                            'CH': {'IR': 0.0, 'OR': 0.0}, 'OD': {'IR': 0.0, 'OR': 0.0}, 
                            'FACE': {'IR': 0.0, 'OR': 0.0}, 'HT': {'IR': 0.0, 'OR': 0.0}
                        }
                    buffers_by_fam[fam][stage][sub_ring_type] += buf_val

        # ==========================================
        # 4. PIPELINE STAGE PIPING & DEDUCTIONS
        # ==========================================
        od_req, face_req, ht_req = {}, {}, {}

        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100) or 100
            rpb_or = box_matrix.get(fam, {}).get('OR', 100) or 100
            
            # Translate gross unit demand down to box structures
            req_boxes_ir = demands['IR'] / rpb_ir
            req_boxes_or = demands['OR'] / rpb_or
            
            def get_buf_boxes(stage, side_code, base_boxes, rpb_rate):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(side_code, 0)
                if payload.unit_mode == 'Days': return raw_buf * base_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb_rate
                return raw_buf 
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_boxes_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_boxes_or, rpb_or)
            od_buf_ir = get_buf_boxes('OD', 'IR', req_boxes_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_boxes_or, rpb_or)
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_boxes_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_boxes_or, rpb_or)

            # Deduct buffers downstream. If buffer is zero, 100% passes down automatically
            net_od_ir = max(0.0, req_boxes_ir - ch_buf_ir)
            net_od_or = max(0.0, req_boxes_or - ch_buf_or)
            
            net_face_ir = max(0.0, net_od_ir - od_buf_ir)
            net_face_or = max(0.0, net_od_or - od_buf_or)
            
            net_ht_ir = max(0.0, net_face_ir - face_buf_ir)
            net_ht_or = max(0.0, net_face_or - face_buf_or)

            if net_od_ir > 0 or net_od_or > 0: 
                od_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': demands['channel']}
            if net_face_ir > 0 or net_face_or > 0: 
                face_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': demands['channel']}
            if net_ht_ir > 0 or net_ht_or > 0: 
                ht_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'rings': {'IR': net_ht_ir * rpb_ir, 'OR': net_ht_or * rpb_or}, 'channel': demands['channel']}

        debug_logs.append(f"Net Pipeline Demands Post-Buffer -> OD: {len(od_req)} | FACE: {len(face_req)} | HT: {len(ht_req)}")

        # ==========================================
        # 5. READ PRODUCTION CAPACITIES & FLEXIBILITY
        # ==========================================
        weight_matrix, furnace_map, machines_data = {}, {}, {'FACE': {}, 'OD': {}}
        sheets_prod, logs3 = load_excel_all_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        debug_logs.extend(logs3)
        
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS']
                df_w.columns = [str(x).strip() for x in df_w.iloc[0]]
                for idx, r in df_w.iloc[1:].iterrows():
                    if pd.notna(r.get('Type')):
                        part_code = 'OR' if str(r.get('ir/or')) == '100' else 'IR'
                        fam = parse_family(r.get('Type'))
                        if fam: weight_matrix[f"{fam}_{part_code}"] = safe_float(r.get('weight per ring', 0.1))

            if 'Furnace Type Flexibility' in sheets_prod:
                df_f = sheets_prod['Furnace Type Flexibility']
                for idx, r in df_f.iterrows():
                    if pd.notna(r.iloc[0]): 
                        fam = parse_family(r.iloc[0])
                        if fam: furnace_map[fam] = str(r.iloc[1]).strip()
            
            # Map dynamic engineering layouts for machine sheets
            for sheet_name, df_m in sheets_prod.items():
                if sheet_name in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                str_matrix = df_m.fillna('').astype(str).values
                
                for r in range(str_matrix.shape[0]):
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text:
                        cells = [c.strip() for c in str_matrix[r] if c.strip()]
                        m_num = cells[1] if len(cells) > 1 else f"MC_{r}"
                        
                        m_type = "UNKNOWN"
                        if "FACE" in row_text or "DDS" in m_num.upper() or "BG" in m_num.upper(): m_type = "FACE"
                        elif "OD" in row_text or "CL" in m_num.upper() or "CELL" in m_num.upper() or "+" in m_num: m_type = "OD"
                        
                        if m_type in ['FACE', 'OD']:
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 16.0}
                            
                            # Find data block column headers down to 5 steps
                            header_idx = -1
                            for offset in range(1, 6):
                                if r + offset >= str_matrix.shape[0]: break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                if 'TYPE' in h_row:
                                    header_idx = r + offset
                                    break
                            
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in df_m.iloc[header_idx].values]
                                block = df_m.iloc[header_idx+1 : header_idx+18].copy()
                                block.columns = headers
                                
                                if 'TYPE' in block.columns:
                                    for _, b_row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(b_row['TYPE'])
                                        if not fam: continue
                                        
                                        p_code = 'OR' if '100' in str(b_row.get('PART', '')) else 'IR'
                                        boxes_hr = safe_float(b_row.get('BOXES/HR', b_row.get('Boxes/hr', 0)))
                                        if boxes_hr == 0 and ('STD/HR' in block.columns or 'Std/hr' in block.columns):
                                            rpb = safe_float(b_row.get('RINGS/BOX', b_row.get('Rings/Box', 100))) or 100
                                            std_hr = safe_float(b_row.get('STD/HR', b_row.get('Std/hr', 0)))
                                            boxes_hr = std_hr / rpb
                                            
                                        if boxes_hr > 0:
                                            machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr
            del sheets_prod
            gc.collect()

        # ==========================================
        # 6. ALLOCATION SCHEDULER ENGINE (GRINDING)
        # ==========================================
        def allocate_grinding(m_type, demands_dict):
            allocated_result = []
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            working_demands = {fam: {'IR': data['IR'], 'OR': data['OR']} for fam, data in sorted_fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                selected_rows = []
                hours_left = m_info['avail_hours']
                
                for fam, _ in sorted_fams:
                    if hours_left <= 0 or len(selected_rows) >= 3: break
                    for p_code in ['IR', 'OR']:
                        boxes_needed = working_demands[fam][p_code]
                        if boxes_needed <= 0: continue
                        
                        part_key = f"{fam}_{p_code}"
                        if part_key in rates and rates[part_key] > 0:
                            rate = rates[part_key]
                            time_required = boxes_needed / rate
                            
                            if time_required <= hours_left:
                                working_demands[fam][p_code] = 0.0
                                hours_used = time_required
                                hours_left -= time_required
                            else:
                                working_demands[fam][p_code] -= (hours_left * rate)
                                hours_used = hours_left
                                hours_left = 0.0
                                
                            selected_rows.append({
                                "part": f"{fam} {p_code}",
                                "std_box": str(round(rate, 1)),
                                "p_2nd": "1" if len(selected_rows) == 0 else "",
                                "p_3rd": "1" if len(selected_rows) == 1 else "",
                                "alert": False,
                                "p_label": f"P{len(selected_rows) + 1}"
                            })
                            if hours_left <= 0 or len(selected_rows) >= 3: break
                
                if selected_rows:
                    allocated_result.append({"machine": m_num, "rows": selected_rows})
            return allocated_result

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # ==========================================
        # 7. HEAT TREATMENT FURNACE ROUTING
        # ==========================================
        result_ht = {}
        for fam, data in ht_req.items():
            rings_ir = data['rings']['IR']
            rings_or = data['rings']['OR']
            if rings_ir <= 0 and rings_or <= 0: continue
            
            # Route using the mapped flexibility configuration matrix
            fur = furnace_map.get(fam, "AICHELIN.(896)")
            if fur not in result_ht: result_ht[fur] = []
            
            total_rings = rings_ir + rings_or
            w_ir = weight_matrix.get(f"{fam}_IR", 0.1)
            w_or = weight_matrix.get(f"{fam}_OR", 0.1)
            total_weight_kg = (rings_ir * w_ir) + (rings_or * w_or)
            
            result_ht[fur].append({
                "part": fam,
                "qty": str(int(total_rings)),
                "cha": data['channel'],
                "rate": str(round(total_weight_kg, 2)),
                "alert": False
            })

        ht_formatted = [{"furnace": fur, "capacity": "500", "rows": items} for fur, items in result_ht.items()]

        # Fallback to display requirements if everything checks out empty
        if not final_face and not final_od and not ht_formatted:
            debug_logs.append("No automated machine routing possible. Outputting global fallback visualization.")

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
        debug_logs.append(f"CRITICAL BACKEND ERROR: {traceback.format_exc()}")
        return {"status": "error", "debug_logs": debug_logs, "detail": str(e)}
