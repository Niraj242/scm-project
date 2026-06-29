import os
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

# Initialize the router for deployment integration
router = APIRouter()

# --- SHEET FILE ROUTING CONFIGURATIONS ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "zeroset_path.xlsx")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "sho_production_path.xlsx")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "box_ring_path.xlsx")

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

# --- ROBUST DATA NORMALIZATION PIPELINES ---
def extract_family(val) -> str:
    """Extracts alphanumeric bearing family codes (e.g., 'MF6204' -> '6204')."""
    if pd.isna(val): 
        return ""
    val_str = str(val).strip().upper()
    match = re.search(r'MF(\d+)', val_str)
    if match: 
        return match.group(1)
    match_uc = re.search(r'(UC\s*\d+)', val_str)
    if match_uc: 
        return match_uc.group(1).replace(" ", "")
    return val_str

def match_excel_date_column(date_row: pd.Series, target_date: datetime) -> int:
    """Robust date matching for Excel strings, serial values, or datetime stamps."""
    formats = [
        target_date.strftime("%d-%b"),      # "02-Mar"
        target_date.strftime("%-d-%b"),     # "2-Mar"
        target_date.strftime("%d/%m/%Y"),   # "02/03/2026"
        target_date.strftime("%Y-%m-%d")    # "2026-03-02"
    ]
    for idx, cell in enumerate(date_row):
        if pd.isna(cell): 
            continue
        if isinstance(cell, (datetime, pd.Timestamp)):
            if cell.date() == target_date.date():
                return idx
        cell_str = str(cell).strip().lower()
        for fmt in formats:
            if fmt.lower() in cell_str:
                return idx
    return -1

def fetch_zeroset_demand(url: str, target_date: datetime) -> Dict[str, float]:
    """Extracts full volume demand (in number of rings) from Zero-Set Plan."""
    demand_map = {}
    try:
        if not os.path.exists(url):
            print(f"File missing at configured path: {url}")
            return {}
        
        df = pd.read_excel(url, header=None)
        # Scan for rows identifying date boundaries
        date_mask = df.apply(lambda r: r.astype(str).str.contains('MTD|PKWIP', flags=re.IGNORECASE).any(), axis=1)
        if not date_mask.any(): 
            return {}
        
        date_row_idx = df[date_mask].index[0]
        date_row = df.iloc[date_row_idx]
        
        target_col = match_excel_date_column(date_row, target_date)
        if target_col == -1: 
            return {}

        for idx in range(date_row_idx + 1, len(df)):
            raw_family = df.iloc[idx, 0]
            demand_val = df.iloc[idx, target_col]
            if pd.isna(raw_family) or pd.isna(demand_val): 
                continue
                
            try:
                raw_qty = float(demand_val)
                # Standard conversion: convert thousand-unit plan multipliers to absolute rings count
                rings = raw_qty * 1000.0 if raw_qty < 15000.0 else raw_qty
                fam_code = extract_family(raw_family)
                if fam_code:
                    demand_map[fam_code] = demand_map.get(fam_code, 0.0) + rings
            except ValueError:
                continue
    except Exception as e:
        print(f"Error parsing Zeroset parameters: {e}")
    return demand_map

def fetch_rings_per_box_matrix(url: str) -> Dict[str, Dict[str, float]]:
    """Maps custom packing box dimensions per family part directly from the sheets."""
    box_matrix = {}
    try:
        if os.path.exists(url):
            df = pd.read_excel(url, sheet_name='RING PER BOX.')
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            type_col = next((c for c in df.columns if 'TYPE' in c or 'FAMILY' in c), None)
            ir_col = next((c for c in df.columns if 'I/R' in c or 'IR' in c or 'INNER' in c), None)
            or_col = next((c for c in df.columns if 'O/R' in c or 'OR' in c or 'OUTER' in c), None)
            
            for _, row in df.iterrows():
                if type_col and pd.notna(row[type_col]):
                    fam = extract_family(row[type_col])
                    if fam:
                        ir_qty = float(row[ir_col]) if ir_col and pd.notna(row[ir_col]) else 100.0
                        or_qty = float(row[or_col]) if or_col and pd.notna(row[or_col]) else 100.0
                        box_matrix[fam] = {'IR': ir_qty, 'OR': or_qty}
    except Exception as e:
        print(f"Box matrix parsing bypassed: {e}")
    return box_matrix

def fetch_furnace_routing_flexibility(url: str) -> Dict[str, str]:
    """Identifies real primary heat treatment assignments configured for each type."""
    routing_map = {}
    try:
        if os.path.exists(url):
            df = pd.read_excel(url, sheet_name='Furnace Type Flexibility')
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            type_col = next((c for c in df.columns if 'TYPE' in c or 'FAMILY' in c), None)
            furnace_col = next((c for c in df.columns if 'FURNACE' in c or 'PRIMARY' in c), None)
            
            for _, row in df.iterrows():
                if type_col and pd.notna(row[type_col]) and furnace_col and pd.notna(row[furnace_col]):
                    fam = extract_family(row[type_col])
                    if fam:
                        routing_map[fam] = str(row[furnace_col]).strip()
    except Exception as e:
        print(f"Furnace routing map fallback active: {e}")
    return routing_map

def fetch_active_shop_machines(url: str) -> Dict[str, Dict[str, Any]]:
    """Dynamically parses and extracts genuine shop-floor machines from the matrix sheets."""
    machine_profiles = {}
    try:
        if not os.path.exists(url): 
            return {}
        xls = pd.ExcelFile(url)
        for sheet in xls.sheet_names:
            if sheet in ['WEIGHTS', 'Furnace Type Flexibility', 'RING PER BOX.']: 
                continue
                
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
            cells = np.where(df == 'MACHINE')
            if not cells[0].size: 
                continue
                
            r, c = cells[0][0], cells[1][0]
            machine_num = str(df.iloc[r, c+1]).strip()
            process_type = str(df.iloc[r, c+2]).strip().upper() # "FACE" or "OD"
            
            headers = [str(h).strip().upper() for h in df.iloc[r+1]]
            data_rows = df.iloc[r+2:].copy()
            data_rows.columns = headers
            
            rates_list = []
            if 'TYPE' in data_rows.columns and 'PART' in data_rows.columns:
                for _, row in data_rows.dropna(subset=['TYPE', 'PART']).iterrows():
                    p_val = str(row['PART']).strip()
                    part_code = 'OR' if '100' in p_val or 'OR' in p_val.upper() else 'IR'
                    rates_list.append({
                        'Family': extract_family(row['TYPE']),
                        'Part': part_code,
                        'StdHr': float(row['STD/HR']) if 'STD/HR' in row and pd.notna(row['STD/HR']) else 0.0,
                        'RingsBox': float(row['Rings/Box']) if 'Rings/Box' in row and pd.notna(row['Rings/Box']) else 100.0
                    })
            
            machine_profiles[machine_num] = {
                'Process': process_type,
                'Capabilities': rates_list
            }
    except Exception as e:
        print(f"Error compiling machine capabilities: {e}")
    return machine_profiles

# --- MAIN AUTOMATION COMPUTATION GATEWAY ---
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        # Determine 2-day lookahead target dates
        day1_date = datetime.strptime(payload.date, "%Y-%m-%d")
        day2_date = day1_date + timedelta(days=1)
        
        # Pull live tracking demands from Zero-Set Plan
        day1_demand = fetch_zeroset_demand(ZEROSET_URL, day1_date)
        day2_demand = fetch_zeroset_demand(ZEROSET_URL, day2_date)
        
        all_families = set(list(day1_demand.keys()) + list(day2_demand.keys()))
        
        # Load constraints from operational sheets
        box_matrix = fetch_rings_per_box_matrix(BOX_RING_DATA_URL)
        furnace_routing = fetch_furnace_routing_flexibility(SHO_PRODUCTION_URL)
        shop_machines = fetch_active_shop_machines(SHO_PRODUCTION_URL)
        
        # Initialize scheduling dictionaries grouped by active physical resources
        furnace_schedule_blocks = {}
        face_schedule_blocks = {}
        od_schedule_blocks = {}
        
        # Run production planning algorithm
        for fam in sorted(all_families):
            if not fam: 
                continue
            
            # Map parameters for inner (IR) and outer (OR) variants
            for part in ['IR', 'OR']:
                d1_rings = day1_demand.get(fam, 0.0)
                d2_rings = day2_demand.get(fam, 0.0)
                
                if d1_rings == 0.0 and d2_rings == 0.0: 
                    continue
                
                # Deduce rings/box factor from sheets
                box_factor = box_matrix.get(fam, {}).get(part, 100.0)
                
                # Precise math conversion logic: compute required standard boxes
                d1_boxes = int(np.ceil(d1_rings / box_factor)) if d1_rings > 0 else 0
                d2_boxes = int(np.ceil(d2_rings / box_factor)) if d2_rings > 0 else 0
                
                part_label = f"MF{fam} ({part})"
                
                # --- RULE 1: HEAT TREATMENT 2-DAY BATCHING CONSTRAINT ---
                is_batched = d1_boxes > 0 and d2_boxes > 0
                total_ht_boxes = (d1_boxes + d2_boxes) if is_batched else d1_boxes
                
                if total_ht_boxes > 0:
                    assigned_furnace = furnace_routing.get(fam, "Furnace F-01")
                    if assigned_furnace not in furnace_schedule_blocks:
                        furnace_schedule_blocks[assigned_furnace] = []
                    
                    furnace_schedule_blocks[assigned_furnace].append({
                        "part": part_label,
                        "qty": total_ht_boxes,
                        "batch_type": "2-Day Combined Batch" if is_batched else "Single Day Run",
                        "sequence": "Seq 1 (HT First)"
                    })
                
                # --- RULE 2: FACE AND OD SEQUENTIAL ROUTING ENGINE ---
                if d1_boxes > 0:
                    # Dynamically match types against authentic sheet machines for Face Grinding
                    face_machine_id = "Face Grinder Line Standard"
                    for m_id, profile in shop_machines.items():
                        if profile['Process'] == 'FACE':
                            if any(cap['Family'] == fam and cap['Part'] == part for cap in profile['Capabilities']):
                                face_machine_id = f"Machine {m_id}"
                                break
                    
                    if face_machine_id not in face_schedule_blocks:
                        face_schedule_blocks[face_machine_id] = []
                    
                    face_schedule_blocks[face_machine_id].append({
                        "part": part_label,
                        "std_box": d1_boxes,
                        "status": "Ready for Setup",
                        "sequence": "Seq 2 (Post-HT)"
                    })
                    
                    # Match against sheet machines for OD Grinding, constrained to occur AFTER Face
                    od_machine_id = "OD Grinder Line Standard"
                    for m_id, profile in shop_machines.items():
                        if profile['Process'] == 'OD':
                            if any(cap['Family'] == fam and cap['Part'] == part for cap in profile['Capabilities']):
                                od_machine_id = f"Machine {m_id}"
                                break
                                
                    if od_machine_id not in od_schedule_blocks:
                        od_schedule_blocks[od_machine_id] = []
                        
                    od_schedule_blocks[od_machine_id].append({
                        "part": part_label,
                        "std_box": d1_boxes,
                        "status": "Pending Face Completion",  # Strict step dependency
                        "sequence": "Seq 3 (Strictly After Face)"
                    })

        # Structure normalized response matrices for front-end consumption
        formatted_furnaces = [{"furnace": k, "rows": v} for k, v in furnace_schedule_blocks.items()]
        formatted_face = [{"machine": k, "rows": v} for k, v in face_schedule_blocks.items()]
        formatted_od = [{"machine": k, "rows": v} for k, v in od_schedule_blocks.items()]
        
        return {
            "status": "success",
            "data": {
                "heat_treatment": formatted_furnaces,
                "face_grinding": formatted_face,
                "od_grinding": formatted_od
            }
        }
    except Exception as e:
        import traceback
        print(f"CRITICAL SYSTEM ERROR ROUTING ENGINE:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Core scheduling processing failure: {str(e)}")
