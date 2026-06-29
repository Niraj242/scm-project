import os
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import math

router = APIRouter()

ZEROSET_URL = os.getenv("ZEROSET_URL", "zeroset_path.xlsx")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "sho_production_path.xlsx")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "box_ring_path.xlsx")

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

def extract_family(val):
    if pd.isna(val) or not val: return ""
    val_str = str(val).strip().upper()
    match = re.search(r'MF(\d+)', val_str)
    if match: return match.group(1)
    match_uc = re.search(r'(UC\s*\d+)', val_str)
    if match_uc: return match_uc.group(1).replace(" ", "")
    return val_str

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        next_date = req_date + timedelta(days=1)
        
        # 1. PARSE BUFFER ENTRIES
        parsed_buffers = {}
        stage_map = {
            'ch_buffer_1': 'CH', 'ch_buffer_2': 'CH',
            'od_buffer_1': 'OD', 'od_buffer_2': 'OD',
            'face_buffer_1': 'FACE', 'face_buffer_2': 'FACE',
            'ht_buffer_1': 'HT', 'ht_buffer_2': 'HT'
        }
        type_rows = {'ch_buffer_1':'type_1', 'ch_buffer_2':'next_type_1', 'od_buffer_1':'type_2', 'od_buffer_2':'next_type_2'}

        for key, value in payload.entries.items():
            if not value or str(value).strip() == "": continue
            parts = key.split('_')
            if len(parts) >= 4:
                base_row = f"{parts[0]}_{parts[1]}_{parts[2]}" if "buffer" in key else f"{parts[0]}_{parts[1]}"
                col_name, sub_part = parts[-2], parts[-1]
                
                if base_row in stage_map:
                    stage = stage_map[base_row]
                    type_lookup = type_rows.get(base_row, 'type_1')
                    type_val = payload.entries.get(f"{type_lookup}_{col_name}_{sub_part}")
                    
                    family = extract_family(type_val) if type_val else "UNKNOWN"
                    if family not in parsed_buffers:
                        parsed_buffers[family] = {'IR': {'CH':0, 'OD':0, 'FACE':0, 'HT':0}, 'OR': {'CH':0, 'OD':0, 'FACE':0, 'HT':0}}
                    try:
                        parsed_buffers[family][sub_part][stage] += float(value)
                    except ValueError: pass

        # 2. READ ZEROSET DEMAND (2 Days)
        total_demand, daily_demand = {}, {}
        try:
            df_zero = pd.read_excel(ZEROSET_URL, header=None)
            mask = df_zero.apply(lambda r: r.astype(str).str.contains('MTD|PKWIP', flags=re.IGNORECASE).any(), axis=1)
            if mask.any():
                r_idx = df_zero[mask].index[0]
                date_row = df_zero.iloc[r_idx]
                f1, f2 = req_date.strftime("%d-%b").lower(), next_date.strftime("%d-%b").lower()
                c1 = next((i for i, v in enumerate(date_row) if f1 in str(v).lower()), None)
                c2 = next((i for i, v in enumerate(date_row) if f2 in str(v).lower()), None)
                
                for idx in range(r_idx + 1, len(df_zero)):
                    fam = extract_family(df_zero.iloc[idx, 0])
                    if not fam: continue
                    r1 = float(df_zero.iloc[idx, c1]) * 1000 if c1 and pd.notna(df_zero.iloc[idx, c1]) else 0
                    r2 = float(df_zero.iloc[idx, c2]) * 1000 if c2 and pd.notna(df_zero.iloc[idx, c2]) else 0
                    total_demand[fam] = total_demand.get(fam, 0) + r1 + r2
                    daily_demand[fam] = (r1 + r2) / 2
        except: pass

        # 3. PARSE MASTER DATA (Rings/Box, Weights, Furnaces, Machines with Rates)
        box_matrix, weight_matrix = {}, {}
        furnace_map = {}
        machines_data = {'FACE': {}, 'OD': {}} 
        # Structure: machines_data['FACE']['544'] = {'name': 'DDS (544)', 'rates': {'6204_OR': 650 (boxes/hr)}}
        
        try:
            df_box = pd.read_excel(BOX_RING_DATA_URL, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                if pd.notna(r.iloc[0]): 
                    box_matrix[extract_family(r.iloc[0])] = {'OR': float(r.get('O/R', 100)), 'IR': float(r.get('I/R', 100))}
        except: pass

        try:
            xls = pd.ExcelFile(SHO_PRODUCTION_URL)
            
            # Weights
            if 'WEIGHTS' in xls.sheet_names:
                df_w = pd.read_excel(xls, sheet_name='WEIGHTS')
                for _, r in df_w.iterrows():
                    if pd.notna(r.get('Type')):
                        part_code = 'OR' if str(r.get('ir/or')) == '100' else 'IR'
                        wt = float(r.get('weight per ring', 0.1))
                        weight_matrix[f"{extract_family(r.get('Type'))}_{part_code}"] = wt

            # Furnace Flexibility
            if 'Furnace Type Flexibility' in xls.sheet_names:
                df_f = pd.read_excel(xls, sheet_name='Furnace Type Flexibility')
                for _, r in df_f.iterrows():
                    if pd.notna(r.iloc[0]): furnace_map[extract_family(r.iloc[0])] = str(r.iloc[1]).strip()
            
            # Extract Machine Rates & Capabilities
            for sheet in xls.sheet_names:
                if sheet in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: continue
                df_m = pd.read_excel(xls, sheet_name=sheet, header=None)
                cells = np.where(df_m.astype(str).apply(lambda x: x.str.contains('MACHINE', case=False, na=False)))
                
                for i in range(len(cells[0])):
                    r, c = cells[0][i], cells[1][i]
                    m_num = str(df_m.iloc[r, c+1]).strip()
                    m_type = str(df_m.iloc[r, c+2]).strip().upper() # FACE or OD
                    
                    if m_type in ['FACE', 'OD']:
                        if m_num not in machines_data[m_type]:
                            machines_data[m_type][m_num] = {'name': m_num, 'rates': {}}
                        
                        # Parse the block below for Rates
                        headers = df_m.iloc[r+1]
                        block = df_m.iloc[r+2:r+20].copy()
                        block.columns = headers
                        if 'TYPE' in block.columns and 'PART' in block.columns:
                            for _, row in block.dropna(subset=['TYPE']).iterrows():
                                fam = extract_family(row['TYPE'])
                                p_code = 'OR' if '100' in str(row['PART']) else 'IR'
                                
                                # Prefer Boxes/hr, fallback to STD/HR divided by Rings/Box
                                boxes_hr = float(row.get('Boxes/hr', 0))
                                if boxes_hr == 0 and pd.notna(row.get('STD/HR')):
                                    rpb = float(row.get('Rings/Box', 100))
                                    boxes_hr = float(row.get('STD/HR')) / rpb
                                
                                machines_data[m_type][m_num]['rates'][f"{fam}_{p_code}"] = boxes_hr
        except: pass

        # 4. CALCULATE NEEDS (OD -> Face -> HT logic)
        face_reqs, od_reqs, ht_reqs = [], [], []
        
        all_fams = set(list(total_demand.keys()) + list(parsed_buffers.keys()))
        for fam in all_fams:
            for part in ['IR', 'OR']:
                demand = total_demand.get(fam, 0.0)
                rpb = box_matrix.get(fam, {}).get(part, 100.0)
                wt = weight_matrix.get(f"{fam}_{part}", 0.2) # Default 0.2kg if missing
                
                tot_boxes = math.ceil(demand / rpb) if demand > 0 else 0
                daily_boxes = math.ceil(daily_demand.get(fam, 0) / rpb)
                
                b_ch = parsed_buffers.get(fam, {}).get(part, {}).get('CH', 0.0)
                b_od = parsed_buffers.get(fam, {}).get(part, {}).get('OD', 0.0)
                b_fc = parsed_buffers.get(fam, {}).get(part, {}).get('FACE', 0.0)
                b_ht = parsed_buffers.get(fam, {}).get(part, {}).get('HT', 0.0)
                
                if payload.unit_mode == 'Days':
                    b_ch *= daily_boxes; b_od *= daily_boxes; b_fc *= daily_boxes; b_ht *= daily_boxes
                elif payload.unit_mode == 'Rings':
                    b_ch /= rpb; b_od /= rpb; b_fc /= rpb; b_ht /= rpb
                
                # Math Logic
                net_od = max(0, tot_boxes - math.ceil(b_ch))
                net_fc = max(0, net_od - math.ceil(b_od))
                net_ht = max(0, net_fc - math.ceil(b_fc) - math.ceil(b_ht))
                
                req_key = f"{fam}_{part}"
                label = f"{fam}---{part}"
                
                if net_fc > 0: face_reqs.append({'key': req_key, 'label': label, 'boxes': net_fc})
                if net_od > 0: od_reqs.append({'key': req_key, 'label': label, 'boxes': net_od})
                if net_ht > 0: ht_reqs.append({'key': req_key, 'label': label, 'boxes': net_ht, 'weight_kg': net_ht * rpb * wt})

        # 5. ASSIGN TO SPECIFIC MACHINES WITH CAPACITY & SETUP CONSTRAINTS (1 DAY = 24 HRS)
        machine_schedule = {'FACE': {}, 'OD': {}}
        furnace_schedule = {}
        
        # Helper to assign grinding operations
        def assign_grinding(requirements, m_type):
            m_timers = {m: 0.0 for m in machines_data[m_type].keys()}
            for req in requirements:
                assigned = False
                for m_id, m_data in machines_data[m_type].items():
                    rate = m_data['rates'].get(req['key'])
                    if rate and rate > 0:
                        run_time = req['boxes'] / rate
                        total_time = run_time + 2.0 # 2 Hour Setup Time
                        
                        if m_timers[m_id] + total_time <= 24.0:
                            if m_data['name'] not in machine_schedule[m_type]:
                                machine_schedule[m_type][m_data['name']] = []
                            
                            machine_schedule[m_type][m_data['name']].append({
                                "part": req['label'], 
                                "std_box": req['boxes'], 
                                "p_2nd": "", "p_3rd": ""
                            })
                            m_timers[m_id] += total_time
                            assigned = True
                            break
                
                # If specific machine not found in sheet, fallback to manual names provided by user
                if not assigned:
                    fallback = "DDS (544)" if m_type == 'FACE' else "CL-46 Cell 1"
                    if fallback not in machine_schedule[m_type]: machine_schedule[m_type][fallback] = []
                    machine_schedule[m_type][fallback].append({"part": req['label'], "std_box": req['boxes'], "p_2nd": "", "p_3rd": ""})

        assign_grinding(face_reqs, 'FACE')
        assign_grinding(od_reqs, 'OD')

        # Furnace Assignment (30 Min setup)
        f_timers = {}
        for req in ht_reqs:
            fam = req['key'].split('_')[0]
            primary_f = furnace_map.get(fam, "AICHELIN.(896)")
            
            # Extract capacity from name (e.g. "AICHELIN (350 kg/hr)" -> 350) or default to 350
            capacity = 350.0 
            if primary_f not in f_timers: f_timers[primary_f] = 0.0
            
            run_time = req['weight_kg'] / capacity
            total_time = run_time + 0.5 # 30 min Setup Time
            
            if primary_f not in furnace_schedule: furnace_schedule[primary_f] = []
            furnace_schedule[primary_f].append({
                "part": req['label'], 
                "qty": req['boxes'], 
                "cha": payload.sector, 
                "rate": capacity
            })
            f_timers[primary_f] += total_time

        # Format arrays for UI
        format_face = [{"machine": k, "rows": v} for k, v in machine_schedule['FACE'].items()]
        format_od = [{"machine": k, "rows": v} for k, v in machine_schedule['OD'].items()]
        format_ht = [{"furnace": k, "capacity": "350", "rows": v} for k, v in furnace_schedule.items()]

        return {
            "status": "success",
            "data": {
                "face_grinding": format_face,
                "od_grinding": format_od,
                "heat_treatment": format_ht
            }
        }
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
