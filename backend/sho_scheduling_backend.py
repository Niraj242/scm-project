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
    if not text or text in ["NAN", "NONE", ""]: return None
    match = re.search(r'(\d{3,5})', text)
    if match: return match.group(1)
    return text.split()[0].split('-')[0]

def safe_float(val):
    if pd.isna(val) or val is None: return 0.0
    try:
        s_val = str(val).replace(',', '').strip().lower()
        if s_val in ['nan', 'none', '', 'null']: return 0.0
        f_val = float(s_val)
        return 0.0 if math.isnan(f_val) else f_val
    except Exception:
        return 0.0

def parse_qty(val):
    """Safely parse quantities. If the Zeroset uses decimals (1.5 for 1500), convert it."""
    v = safe_float(val)
    if 0 < v <= 50: return v * 1000 
    return v

def load_excel_fast(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "":
        logs.append(f"[{file_label}] FAILED: URL is empty.")
        return None, logs
    
    for attempt in range(3):
        try:
            logs.append(f"[{file_label}] Attempt {attempt + 1}: Fetching URL...")
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                time.sleep(2)
                continue
                
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
                
                # Scan for Headers
                for i, row in df_zero.iterrows():
                    row_strs = [str(x).strip().upper() for x in row.values]
                    if type_col_idx is None:
                        for j, val in enumerate(row_strs):
                            if val in ["TYPE", "MF", "PART NO", "BRG NO"] or "TYPE" in val: 
                                type_col_idx = j
                                break
                    if 'MTD' in " ".join(row_strs) or 'PKWIP' in " ".join(row_strs) or 'PLAN' in " ".join(row_strs):
                        r_idx = i
                        for j, val in enumerate(row.values):
                            if pd.isna(val): continue
                            v_str = str(val).strip()
                            if v_str in [req_d, f"{req_d}.0"]: c1 = j
                            if v_str in [nxt_d, f"{nxt_d}.0"]: c2 = j
                    if r_idx is not None and type_col_idx is not None: break
                        
                if r_idx is not None and type_col_idx is not None:
                    # CRITICAL FIX: Handle merged cells by forward-filling the TYPE column
                    df_zero[type_col_idx] = df_zero[type_col_idx].ffill()
                    
                    found_count = 0
                    if c1 is not None or c2 is not None:
                        debug_logs.append(f"[ZEROSET] MATCHED DAY {req_d} & {nxt_d} in sheet '{sheet_name}'.")
                    
                    for idx in range(r_idx + 1, len(df_zero)):
                        raw_type = df_zero.iloc[idx, type_col_idx]
                        fam = parse_family(raw_type)
                        if not fam: continue
                        
                        r1 = parse_qty(df_zero.iloc[idx, c1]) if c1 is not None else 0
                        r2 = parse_qty(df_zero.iloc[idx, c2]) if c2 is not None else 0
                        
                        if r1 > 0 or r2 > 0:
                            found_count += 1
                            if fam not in channel_demands: 
                                channel_demands[fam] = {'IR': 0, 'OR': 0, 'channel': sheet_name}
                            
                            avg_d = (r1 + r2) / 2.0
                            is_or = 'OR' in str(raw_type).upper()
                            is_ir = 'IR' in str(raw_type).upper()
                            
                            # Use max to avoid double-counting WIP + PLAN rows for the same family
                            if is_or:
                                channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], avg_d)
                            elif is_ir:
                                channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], avg_d)
                            else:
                                channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], avg_d)
                                channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], avg_d)
                                
                    if found_count > 0:
                        debug_logs.append(f"[ZEROSET] Sheet '{sheet_name}' -> Read {found_count} demand entries.")
                        
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
                if fam: box_matrix[fam] = {'OR': safe_float(r.get('O/R', 100)), 'IR': safe_float(r.get('I/R', 100))}
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
                    if not fam: continue
                    
                    buf_val = safe_float(payload.entries.get(f"{buf_prefix}_{suffix}", 0))
                    if buf_val <= 0: continue
                    
                    if fam not in buffers_by_fam:
                        buffers_by_fam[fam] = {'CH': {'IR':0, 'OR':0}, 'OD': {'IR':0, 'OR':0}, 'FACE': {'IR':0, 'OR':0}, 'HT': {'IR':0, 'OR':0}}
                    
                    sub_col = 'OR' if suffix.endswith('_OR') else 'IR'
                    buffers_by_fam[fam][stage][sub_col] += buf_val

        # ==========================================
        # 4. STAGE DEDUCTIONS (THE PIPELINE)
        # ==========================================
        od_req, face_req, ht_req = {}, {}, {}

        for fam, demands in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100) or 100
            rpb_or = box_matrix.get(fam, {}).get('OR', 100) or 100
            
            req_boxes_ir = demands['IR'] / rpb_ir
            req_boxes_or = demands['OR'] / rpb_or
            
            def get_buf_boxes(stage, p_code, req_boxes, rpb):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(p_code, 0)
                if payload.unit_mode == 'Days': return raw_buf * req_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb
                return raw_buf 
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_boxes_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_boxes_or, rpb_or)
            
            od_buf_ir = get_buf_boxes('OD', 'IR', req_boxes_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_boxes_or, rpb_or)
            
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_boxes_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_boxes_or, rpb_or)

            # Deductions (If no buffer, 100% of demand passes through)
            net_od_ir = max(0, req_boxes_ir - ch_buf_ir)
            net_od_or = max(0, req_boxes_or - ch_buf_or)
            
            net_face_ir = max(0, net_od_ir - od_buf_ir)
            net_face_or = max(0, net_od_or - od_buf_or)
            
            net_ht_ir = max(0, net_face_ir - face_buf_ir)
            net_ht_or = max(0, net_face_or - face_buf_or)

            if net_od_ir > 0 or net_od_or > 0: od_req[fam] = {'IR': net_od_ir, 'OR': net_od_or, 'channel': demands['channel']}
            if net_face_ir > 0 or net_face_or > 0: face_req[fam] = {'IR': net_face_ir, 'OR': net_face_or, 'channel': demands['channel']}
            if net_ht_ir > 0 or net_ht_or > 0: ht_req[fam] = {'IR': net_ht_ir, 'OR': net_ht_or, 'channel': demands['channel']}
            
            # Store raw ring count for HT 
            if fam in ht_req:
                ht_req[fam]['rings'] = {'IR': net_ht_ir * rpb_ir, 'OR': net_ht_or * rpb_or}

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
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text:
                        cells = [c.strip() for c in str_matrix[r] if c.strip()]
                        m_num = cells[1] if len(cells) > 1 else f"Unknown_{r}"
                        
                        m_type = "UNKNOWN"
                        if "FACE" in row_text: m_type = "FACE"
                        elif "OD" in row_text: m_type = "OD"
                        
                        if m_type in ['FACE', 'OD']:
                            if m_num not in machines_data[m_type]:
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 16.0}
                            
                            # Hunt for headers
                            header_idx = -1
                            for offset in range(1, 6):
                                if r + offset >= str_matrix.shape[0]: break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                if 'TYPE' in h_row:
                                    header_idx = r + offset
                                    break
                            
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in df_m.iloc[header_idx].values]
                                block = df_m.iloc[header_idx+1 : header_idx+20].copy()
                                block.columns = headers
                                
                                if 'TYPE' in block.columns:
                                    for _, row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(row['TYPE'])
                                        if not fam: continue
                                        
                                        p_code = 'OR' if '100' in str(row.get('PART', '')) else 'IR'
                                        boxes_hr = safe_float(row.get('BOXES/HR', 0))
                                        if boxes_hr == 0 and 'STD/HR' in block.columns:
                                            rpb = safe_float(row.get('RINGS/BOX', 100)) or 100
                                            boxes_hr = safe_float(row.get('STD/HR')) / rpb
                                            
                                        if boxes_hr > 0:
                                            machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr

            del xls_prod
            gc.collect()

        # ==========================================
        # 6. GRINDING ALLOCATION
        # ==========================================
        def allocate(m_type, demands_dict):
            allocated_result = []
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            working_demands = {fam: {'IR': data['IR'], 'OR': data['OR']} for fam, data in sorted_fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                selected_rows = []
                hours_left = m_info['avail_hours']
                
                for fam, _ in sorted_fams:
                    if hours_left <= 0 or len(selected_rows) >= 2: break
                    for p_code in ['IR', 'OR']:
                        boxes_needed = working_demands[fam][p_code]
                        if boxes_needed <= 0: continue
                        
                        part_key = f"{fam}_{p_code}"
                        if part_key in rates and rates[part_key] > 0:
                            rate = rates[part_key]
                            
                            setup_time = 0.5
                            if hours_left <= setup_time: continue
                            hours_left -= setup_time
                            
                            time_required = boxes_needed / rate
                            if time_required <= hours_left:
                                working_demands[fam][p_code] = 0.0
                                hours_left -= time_required
                            else:
                                working_demands[fam][p_code] -= (hours_left * rate)
                                hours_left = 0.0
                                
                            selected_rows.append({
                                "part": f"{fam} {p_code}",
                                "std_box": str(round(rate, 1)),
                                "p_2nd": "1" if len(selected_rows) == 0 else "",
                                "p_3rd": "1" if len(selected_rows) == 1 else "",
                                "alert": False,
                                "p_label": f"P{len(selected_rows) + 1}"
                            })
                            if hours_left <= 0 or len(selected_rows) >= 2: break
                
                if selected_rows:
                    allocated_result.append({"machine": m_num, "rows": selected_rows})
            return allocated_result

        final_face = allocate('FACE', face_req)
        final_od = allocate('OD', od_req)

        # ==========================================
        # 7. HEAT TREATMENT ALLOCATION
        # ==========================================
        result_ht = {}
        for fam, data in ht_req.items():
            rings_ir = data['rings']['IR']
            rings_or = data['rings']['OR']
            if rings_ir <= 0 and rings_or <= 0: continue
            
            fur = furnace_map.get(fam, "AICHELIN.(896)")
            if fur not in result_ht: result_ht[fur] = []
            
            total_rings = rings_ir + rings_or
            w_ir = weight_matrix.get(f"{fam}_IR", 0.1)
            w_or = weight_matrix.get(f"{fam}_OR", 0.1)
            total_weight = (rings_ir * w_ir) + (rings_or * w_or)
            
            result_ht[fur].append({
                "part": fam,
                "qty": str(int(total_rings)),
                "cha": data['channel'],
                "rate": str(round(total_weight, 2)),
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
        return {"status": "error", "debug_logs": debug_logs, "detail": str(e)}
