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
    if "INDUSTRILA" in text: text = text.replace("INDUSTRILA", "INDUSTRIAL")
    if "AUTOMOTIVE" in text: return None
    if not text or text in ["NAN", "NONE", "", "UNKNOWN"]: return None
    
    if "HUB" in text:
        match_hub = re.search(r'(T?\s*HUB\s*\d+\.?\d*)', text)
        if match_hub: return match_hub.group(1).replace(" ", "")
        return "HUB"
        
    if text.startswith("T ") or re.match(r'^T\d+', text):
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

# FIXED: GUARANTEED DEFAULT RATE IF PART IS MISSING FROM SHEET
def get_rate_for_part(fam, p_code, rates):
    exact_key = f"{fam}_{p_code}"
    if exact_key in rates: return rates[exact_key]
    
    if fam.startswith("HUB") and f"HUB_{p_code}" in rates: return rates[f"HUB_{p_code}"]
    if fam.startswith("THUB") and f"THUB_{p_code}" in rates: return rates[f"THUB_{p_code}"]
    if fam.startswith("T") and f"T_{p_code}" in rates: return rates[f"T_{p_code}"]
    
    # HARD FALLBACK to prevent parts being dropped completely from grinding schedule
    return 15.0 

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # ==========================================
        # 1. PARSE ZEROSET
        # ==========================================
        channel_demands = {} 
        sheets_zero, logs1 = load_excel_all_sheets(ZEROSET_URL, "ZEROSET")
        debug_logs.extend(logs1)
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
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
                    found_count = 0
                    active_raw_type = None
                    
                    for idx in range(r_idx + 1, len(df_zero)):
                        cell_val = df_zero.iloc[idx, type_col_idx]
                        if pd.notna(cell_val) and str(cell_val).strip() != "":
                            active_raw_type = str(cell_val).strip()
                            
                        if not active_raw_type: continue
                        fam = parse_family(active_raw_type)
                        if not fam: continue
                        
                        val1 = safe_float(df_zero.iloc[idx, c1]) if c1 is not None else 0.0
                        val2 = safe_float(df_zero.iloc[idx, c2]) if c2 is not None else 0.0
                        
                        r1 = val1 * 1000 if 0 < val1 <= 70 else val1
                        r2 = val2 * 1000 if 0 < val2 <= 70 else val2
                        
                        if r1 > 0 or r2 > 0:
                            if r1 == 0 and r2 > 0: continue 
                                
                            found_count += 1
                            if fam not in channel_demands: 
                                channel_demands[fam] = {'IR': 0.0, 'OR': 0.0, 'channel': str(sheet_name).strip()}
                            
                            combined_qty = r1 + r2
                            channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], combined_qty)
                            channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], combined_qty)
                                
            del sheets_zero
            gc.collect()

        # ==========================================
        # 2. BOX MATRIX (FIXED TO READ REPEATING COLUMNS ACROSS ROW)
        # ==========================================
        box_matrix = {}
        sheets_box, _ = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box and 'RING PER BOX.' in sheets_box:
            df_box = sheets_box['RING PER BOX.'].fillna('')
            for idx in range(1, len(df_box)):
                row_vals = list(df_box.iloc[idx])
                for i in range(0, len(row_vals) - 2, 3):
                    fam_raw = str(row_vals[i]).strip()
                    if not fam_raw: continue
                    fam = parse_family(fam_raw)
                    if fam:
                        or_qty = safe_float(row_vals[i+1])
                        ir_qty = safe_float(row_vals[i+2])
                        box_matrix[fam] = {
                            'OR': or_qty if or_qty > 0 else 100,
                            'IR': ir_qty if ir_qty > 0 else 100
                        }
            del sheets_box
            gc.collect()

        # ==========================================
        # 3. BUFFERS
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
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
            req_boxes_ir = demands['IR'] / rpb_ir
            req_boxes_or = demands['OR'] / rpb_or
            
            def get_buf_boxes(stage, side, base_boxes, rpb_rate):
                raw_buf = buffers_by_fam.get(fam, {}).get(stage, {}).get(side, 0)
                if payload.unit_mode == 'Days': return raw_buf * base_boxes
                elif payload.unit_mode == 'Rings': return raw_buf / rpb_rate
                return raw_buf 
                
            ch_buf_ir = get_buf_boxes('CH', 'IR', req_boxes_ir, rpb_ir)
            ch_buf_or = get_buf_boxes('CH', 'OR', req_boxes_or, rpb_or)
            od_buf_ir = get_buf_boxes('OD', 'IR', req_boxes_ir, rpb_ir)
            od_buf_or = get_buf_boxes('OD', 'OR', req_boxes_or, rpb_or)
            face_buf_ir = get_buf_boxes('FACE', 'IR', req_boxes_ir, rpb_ir)
            face_buf_or = get_buf_boxes('FACE', 'OR', req_boxes_or, rpb_or)

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

        # ==========================================
        # 4. PRODUCTION RATES
        # ==========================================
        weight_matrix, furnace_map, furnace_rates, machines_data = {}, {}, {}, {'FACE': {}, 'OD': {}}
        all_furnaces_set = set()

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

            fur_sheet_key = next((k for k in sheets_prod.keys() if 'FURNACE' in str(k).upper()), None)
            if fur_sheet_key:
                df_f = sheets_prod[fur_sheet_key]
                df_f.columns = [str(x).strip().upper() for x in df_f.iloc[0]]
                for idx, r in df_f.iloc[1:].iterrows():
                    fam_val = r.get('TYPE', r.iloc[0] if len(r) > 0 else '')
                    fam = parse_family(fam_val)
                    if fam: 
                        fur_col = next((c for c in df_f.columns if 'FURNACE' in c), None)
                        fur_raw = str(r[fur_col]) if fur_col else str(r.iloc[1] if len(r) > 1 else '')
                        
                        furnaces = [f.strip() for f in re.split(r'[,/|]', fur_raw) if f.strip() and f.strip().upper() != 'NAN']
                        if not furnaces: furnaces = [f.strip() for f in fur_raw.replace(',', ' ').split() if f.strip()]
                        
                        valid_furnaces = []
                        for fur in furnaces:
                            valid_furnaces.append(fur)
                            all_furnaces_set.add(fur)
                        
                        if valid_furnaces: furnace_map[fam] = valid_furnaces
                        
                        cap_col = next((c for c in df_f.columns if 'CAP' in c or 'KG/HR' in c), None)
                        cap = safe_float(r[cap_col]) if cap_col else 400.0
                        if cap > 0: furnace_rates[fam] = cap
            
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
                                machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0}
                            
                            header_idx = -1
                            for offset in range(1, 6):
                                if r + offset >= str_matrix.shape[0]: break
                                h_row = [str(x).strip().upper() for x in df_m.iloc[r + offset].values]
                                if 'TYPE' in h_row:
                                    header_idx = r + offset
                                    break
                            
                            if header_idx != -1:
                                headers = [str(x).strip().upper() for x in df_m.iloc[header_idx].values]
                                block = df_m.iloc[header_idx+1 : header_idx+25].copy()
                                block.columns = headers
                                
                                if 'TYPE' in block.columns:
                                    for _, b_row in block.dropna(subset=['TYPE']).iterrows():
                                        fam = parse_family(b_row['TYPE'])
                                        if not fam: continue
                                        
                                        part_val = str(b_row.get('PART', '')).strip().upper()
                                        p_codes = ['IR', 'OR']
                                        if '100' in part_val or 'OR' in part_val: p_codes = ['OR']
                                        elif '010' in part_val or 'IR' in part_val: p_codes = ['IR']
                                        
                                        boxes_hr = safe_float(b_row.get('BOXES/HR', b_row.get('Boxes/hr', 0)))
                                        if boxes_hr == 0 and ('STD/HR' in block.columns or 'Std/hr' in block.columns):
                                            rpb = safe_float(b_row.get('RINGS/BOX', b_row.get('Rings/Box', 100))) or 100
                                            boxes_hr = safe_float(b_row.get('STD/HR', 0)) / rpb
                                            
                                        if boxes_hr > 0:
                                            for pc in p_codes:
                                                machines_data[m_type][m_num]['rates'][f"{fam}_{pc}"] = boxes_hr
            del sheets_prod
            gc.collect()

        # ==========================================
        # 5. GRINDING SCHEDULER
        # ==========================================
        def allocate_grinding(m_type, demands_dict):
            allocated_result = []
            sorted_fams = sorted(demands_dict.items(), key=lambda x: x[1]['IR'] + x[1]['OR'], reverse=True)
            working_demands = {fam: {'IR': data['IR'], 'OR': data['OR']} for fam, data in sorted_fams}
            
            for m_num, m_info in machines_data.get(m_type, {}).items():
                rates = m_info.get('rates', {})
                selected_rows = []
                hours_left = m_info['avail_hours'] 
                current_fam = None
                
                for fam, _ in sorted_fams:
                    if hours_left <= 0 or len(selected_rows) >= 3: break
                    for p_code in ['IR', 'OR']:
                        boxes_needed = working_demands[fam][p_code]
                        if boxes_needed <= 0: continue
                        
                        rate = get_rate_for_part(fam, p_code, rates)
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
                            if hours_left <= 0 or len(selected_rows) >= 3: break
                
                if selected_rows:
                    allocated_result.append({"machine": m_num, "rows": selected_rows})
            return allocated_result

        final_face = allocate_grinding('FACE', face_req)
        final_od = allocate_grinding('OD', od_req)

        # ==========================================
        # 6. DYNAMIC HEAT TREATMENT (STRICT BATCHING & FAILSAFE)
        # ==========================================
        if not all_furnaces_set:
            all_furnaces_set.add("AICHELIN.(896)")
            
        furnace_clocks = {f: {"avail_hours": 24.0, "current_fam": None, "rows": []} for f in all_furnaces_set}

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
                preferred_furnaces = list(all_furnaces_set)[:1] 
                
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
                time_needed = total_weight_kg / kg_per_hr
                
                selected_fur = preferred_furnaces[0]
                if selected_fur not in furnace_clocks: furnace_clocks[selected_fur] = {"avail_hours": 24.0, "current_fam": None, "rows": []}
                
                ctx = furnace_clocks[selected_fur]
                setup_penalty = 2.0 if (ctx["current_fam"] and ctx["current_fam"] != fam) else 0.0
                
                if (ctx["avail_hours"] - setup_penalty) < time_needed and len(preferred_furnaces) > 1:
                    alt_fur = preferred_furnaces[1]
                    if alt_fur not in furnace_clocks: furnace_clocks[alt_fur] = {"avail_hours": 24.0, "current_fam": None, "rows": []}
                    alt_ctx = furnace_clocks[alt_fur]
                    alt_setup = 2.0 if (alt_ctx["current_fam"] and alt_ctx["current_fam"] != fam) else 0.0
                    
                    if (alt_ctx["avail_hours"] - alt_setup) > (ctx["avail_hours"] - setup_penalty):
                        selected_fur = alt_fur
                        ctx = alt_ctx
                        setup_penalty = alt_setup

                ctx["avail_hours"] -= (time_needed + setup_penalty)
                ctx["current_fam"] = fam
                
                ctx["rows"].append({
                    "part": f"{fam}-{p_code}", 
                    "qty": str(int(qty)), 
                    "cha": data['channel'],
                    "rate": str(round(qty * unit_weight / 24.0, 2)),
                    "alert": ctx["avail_hours"] < 0 
                })

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
