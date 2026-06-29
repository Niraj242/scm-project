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
        
        # 1. PARSE BUFFER ENTRIES FROM UI
        # Map which Type row corresponds to which Buffer row
        type_mapping = {
            'ch_buffer_1': 'type_1', 'ch_buffer_2': 'next_type_1',
            'od_buffer_1': 'type_2', 'od_buffer_2': 'next_type_2',
            'face_buffer_1': 'type_3', 'face_buffer_2': 'type_4',
            'ht_buffer_1': 'type_5', 'ht_buffer_2': 'type_6'
        }
        
        stage_mapping = {
            'ch_buffer_1': 'CH', 'ch_buffer_2': 'CH',
            'od_buffer_1': 'OD', 'od_buffer_2': 'OD',
            'face_buffer_1': 'FACE', 'face_buffer_2': 'FACE',
            'ht_buffer_1': 'HT', 'ht_buffer_2': 'HT'
        }

        # Structure: { '6204': { 'IR': {'CH': 0, 'OD': 0, 'FACE': 0, 'HT': 0}, 'OR': {...} } }
        parsed_buffers = {}
        for key, val in payload.entries.items():
            if not val: continue
            
            parts = key.split('_')
            if len(parts) >= 4:
                # e.g., ch_buffer_1_CH01_IR -> base_key="ch_buffer_1", col="CH01", part="IR"
                base_key = f"{parts[0]}_{parts[1]}_{parts[2]}" if "buffer" in key else f"{parts[0]}_{parts[1]}"
                part_type = parts[-1]
                col = parts[-2]
                
                if base_key in type_mapping:
                    type_row_key = type_mapping[base_key]
                    type_val = payload.entries.get(f"{type_row_key}_{col}_{part_type}")
                    if type_val:
                        fam = extract_family(type_val)
                        if fam:
                            if fam not in parsed_buffers:
                                parsed_buffers[fam] = {'IR': {'CH':0, 'OD':0, 'FACE':0, 'HT':0}, 'OR': {'CH':0, 'OD':0, 'FACE':0, 'HT':0}}
                            try:
                                stage = stage_mapping[base_key]
                                parsed_buffers[fam][part_type][stage] += float(val)
                            except ValueError:
                                pass

        # 2. READ ZEROSET DEMAND (2 DAYS)
        demand_map = {} # fam -> total rings
        daily_demand = {} # fam -> rings per day
        try:
            df_zero = pd.read_excel(ZEROSET_URL, header=None)
            date_mask = df_zero.apply(lambda r: r.astype(str).str.contains('MTD|PKWIP', flags=re.IGNORECASE).any(), axis=1)
            if date_mask.any():
                d_idx = df_zero[date_mask].index[0]
                d_row = df_zero.iloc[d_idx]
                
                f1 = req_date.strftime("%d-%b").lower()
                f2 = next_date.strftime("%d-%b").lower()
                
                c1 = next((i for i, v in enumerate(d_row) if f1 in str(v).lower()), None)
                c2 = next((i for i, v in enumerate(d_row) if f2 in str(v).lower()), None)
                
                for idx in range(d_idx + 1, len(df_zero)):
                    fam = extract_family(df_zero.iloc[idx, 0])
                    if not fam: continue
                    
                    r1 = float(df_zero.iloc[idx, c1]) * 1000 if c1 and pd.notna(df_zero.iloc[idx, c1]) else 0
                    r2 = float(df_zero.iloc[idx, c2]) * 1000 if c2 and pd.notna(df_zero.iloc[idx, c2]) else 0
                    
                    demand_map[fam] = demand_map.get(fam, 0) + r1 + r2
                    daily_demand[fam] = (r1 + r2) / 2 # Average per day for "Days" buffer calc
        except Exception as e:
            print(f"Zeroset reading error: {e}")

        # 3. GET RINGS PER BOX
        box_matrix = {}
        try:
            df_box = pd.read_excel(BOX_RING_DATA_URL, sheet_name='RING PER BOX.')
            for _, r in df_box.iterrows():
                if pd.notna(r.iloc[0]):
                    fam = extract_family(r.iloc[0])
                    or_val = float(r.get('O/R', 100)) if 'O/R' in df_box.columns else 100.0
                    ir_val = float(r.get('I/R', 100)) if 'I/R' in df_box.columns else 100.0
                    box_matrix[fam] = {'OR': or_val, 'IR': ir_val}
        except: pass

        # 4. GET PRIMARY FURNACES & MACHINES
        furnace_map = {}
        machines = {'FACE': [], 'OD': []}
        try:
            xls = pd.ExcelFile(SHO_PRODUCTION_URL)
            if 'Furnace Type Flexibility' in xls.sheet_names:
                df_f = pd.read_excel(xls, sheet_name='Furnace Type Flexibility')
                for _, r in df_f.iterrows():
                    if pd.notna(r.iloc[0]):
                        furnace_map[extract_family(r.iloc[0])] = str(r.iloc[1]).strip()
            
            for sheet in xls.sheet_names:
                if sheet in ['WEIGHTS', 'Furnace Type Flexibility']: continue
                df_m = pd.read_excel(xls, sheet_name=sheet, header=None)
                cells = np.where(df_m == 'MACHINE')
                if cells[0].size > 0:
                    r, c = cells[0][0], cells[1][0]
                    m_name = str(df_m.iloc[r, c+1]).strip()
                    m_type = str(df_m.iloc[r, c+2]).strip().upper()
                    machines[m_type].append(m_name)
        except: pass

        # 5. CALCULATE NET SCHEDULING REQUIREMENTS
        ht_tasks = {}
        face_tasks = {}
        od_tasks = {}

        all_fams = set(list(demand_map.keys()) + list(parsed_buffers.keys()))
        for fam in all_fams:
            for part in ['IR', 'OR']:
                rpb = box_matrix.get(fam, {}).get(part, 100.0)
                tot_rings = demand_map.get(fam, 0)
                tot_boxes = math.ceil(tot_rings / rpb)
                daily_boxes = math.ceil(daily_demand.get(fam, 0) / rpb)
                
                # Fetch buffer numbers typed in UI for this specific family & part
                b_ch = parsed_buffers.get(fam, {}).get(part, {}).get('CH', 0)
                b_od = parsed_buffers.get(fam, {}).get(part, {}).get('OD', 0)
                b_face = parsed_buffers.get(fam, {}).get(part, {}).get('FACE', 0)
                b_ht = parsed_buffers.get(fam, {}).get(part, {}).get('HT', 0)
                
                # Convert units to Boxes
                if payload.unit_mode == 'Days':
                    b_ch *= daily_boxes
                    b_od *= daily_boxes
                    b_face *= daily_boxes
                    b_ht *= daily_boxes
                elif payload.unit_mode == 'Rings':
                    b_ch /= rpb
                    b_od /= rpb
                    b_face /= rpb
                    b_ht /= rpb
                
                b_ch, b_od, b_face, b_ht = math.ceil(b_ch), math.ceil(b_od), math.ceil(b_face), math.ceil(b_ht)
                
                # MATHEMATICAL DEDUCTION (Sequential Flow Constraints)
                net_od = max(0, tot_boxes - b_ch)
                net_face = max(0, net_od - b_od)
                net_ht = max(0, net_face - b_face - b_ht)
                
                label = f"{fam}---{part}"
                
                # Route to Heat Treatment
                if net_ht > 0:
                    furnace = furnace_map.get(fam, "Default Furnace Line")
                    if furnace not in ht_tasks: ht_tasks[furnace] = []
                    ht_tasks[furnace].append({"part": label, "qty": net_ht, "cha": "-", "rate": "350"})
                
                # Route to Face
                if net_face > 0:
                    f_mach = machines['FACE'][0] if machines['FACE'] else "Face Grinder"
                    if f_mach not in face_tasks: face_tasks[f_mach] = []
                    face_tasks[f_mach].append({"part": label, "std_box": net_face, "p_2nd": "", "p_3rd": ""})
                
                # Route to OD
                if net_od > 0:
                    o_mach = machines['OD'][0] if machines['OD'] else "OD Grinder"
                    if o_mach not in od_tasks: od_tasks[o_mach] = []
                    od_tasks[o_mach].append({"part": label, "std_box": net_od, "p_2nd": "", "p_3rd": ""})

        # Final Formatting
        format_ht = [{"furnace": k, "capacity": "350", "rows": v} for k, v in ht_tasks.items()]
        format_face = [{"machine": k, "rows": v} for k, v in face_tasks.items()]
        format_od = [{"machine": k, "rows": v} for k, v in od_tasks.items()]

        return {
            "status": "success",
            "data": {
                "heat_treatment": format_ht,
                "face_grinding": format_face,
                "od_grinding": format_od
            }
        }
        
    except Exception as e:
        import traceback
        print(f"ERROR:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
