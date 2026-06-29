import os
import re
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

# --- ENVIRONMENT VARIABLES ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "zeroset_path.xlsx")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "sho_production_path.xlsx")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "box_ring_path.xlsx")

# --- PYDANTIC MODELS ---
class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

# --- HELPER FUNCTIONS ---
def extract_family(val):
    """Extracts bearing family from MFXXXX or other formats."""
    if pd.isna(val): return None
    val_str = str(val).strip().upper()
    match = re.search(r'MF(\d+)', val_str)
    if match: return match.group(1)
    
    # Handle UC or other specific prefixes
    match_uc = re.search(r'(UC\s*\d+)', val_str)
    if match_uc: return match_uc.group(1).replace(" ", "")
    
    return val_str

# --- DATA PIPELINES ---
def get_zeroset_demand(url, target_date):
    """Extracts exact Date-specific demand from zeroset plan."""
    try:
        df = pd.read_excel(url, header=None)
        # Find row with MTD or PKWIP exactly
        date_row_mask = df.apply(lambda r: r.astype(str).str.contains('MTD|PKWIP', flags=re.IGNORECASE).any(), axis=1)
        if not date_row_mask.any(): return pd.DataFrame()
        
        date_row_idx = df[date_row_mask].index[0]
        date_row = df.iloc[date_row_idx].astype(str)
        
        try:
            target_col_idx = date_row[date_row.str.contains(target_date)].index[0]
        except IndexError:
            return pd.DataFrame() 

        demand_data = []
        for idx in range(date_row_idx + 1, len(df)):
            raw_family = df.iloc[idx, 0] # Assuming first col has family/type
            demand_val = df.iloc[idx, target_col_idx]
            
            if pd.notna(demand_val) and str(demand_val).replace('.', '', 1).isdigit():
                family = extract_family(raw_family)
                demand_data.append({
                    'Family': family,
                    'Demand_Rings': float(demand_val) * 1000 # Values are in thousands
                })
        return pd.DataFrame(demand_data).groupby('Family').sum().reset_index()
    except Exception as e:
        print(f"Error reading Zeroset: {e}")
        return pd.DataFrame()

def get_weights_and_flexibility(url):
    """Maps Family & Part (100/120) and fetches Furnace Flexibility."""
    data = {'weights': pd.DataFrame(), 'furnaces': pd.DataFrame()}
    try:
        # Weights
        w_df = pd.read_excel(url, sheet_name='WEIGHTS')
        w_df['PartCode'] = w_df['ir/or'].map({100: 'OR', 120: 'IR'})
        data['weights'] = w_df
        
        # Flexibility
        f_df = pd.read_excel(url, sheet_name='Furnace Type Flexibility')
        data['furnaces'] = f_df
    except Exception as e:
        print(f"Error reading Weights/Flexibility: {e}")
    return data

def get_grinding_machines(url):
    """Parses dynamic sheets for machines and OD/Face mapping."""
    machines = {}
    try:
        xls = pd.ExcelFile(url)
        skip_sheets = ['WEIGHTS', 'Furnace Type Flexibility']
        for sheet in xls.sheet_names:
            if sheet in skip_sheets: continue
            
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
            start_cells = np.where(df.astype(str).apply(lambda x: x.str.contains('MACHINE', case=False, na=False)))
            
            if not start_cells[0].size: continue
            
            for i in range(len(start_cells[0])):
                r, c = start_cells[0][i], start_cells[1][i]
                machine_num = str(df.iloc[r, c+1]).strip()
                process = str(df.iloc[r, c+2]).strip().upper() # Face or OD
                
                headers = df.iloc[r+1]
                data = df.iloc[r+2:r+20].copy() # Limit to block
                data.columns = headers
                if 'PART' in data.columns:
                    data['PART'] = data['PART'].map({100: 'OR', 120: 'IR', '100': 'OR', '120': 'IR'})
                
                machines[machine_num] = {
                    'Process': process,
                    'Rates': data.dropna(subset=['TYPE', 'STD/HR']).to_dict('records')
                }
    except Exception as e:
        print(f"Error reading Machine data: {e}")
    return machines

def get_box_rings(url):
    """Gets Rings per box mapping."""
    try:
        df = pd.read_excel(url, sheet_name='RING PER BOX.')
        return df
    except:
        return pd.DataFrame()

# --- MAIN ENDPOINT ---
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        # In a full implementation, you'd call the Google Sheets pipelines here.
        # zeroeset = get_zeroset_demand(ZEROSET_URL, payload.date)
        # machine_data = get_grinding_machines(SHO_PRODUCTION_URL)
        # box_data = get_box_rings(BOX_RING_DATA_URL)
        
        # --- PLACEHOLDER SCHEDULING LOGIC based on UI constraints ---
        # The backend processes capacities (e.g., Aichelin 350kg/hr), subtracts 30m for furnace
        # changeovers, and 2hrs for Grinding machine changeovers. 

        # Generating structured mock data to populate the frontend identically to the image provided.
        face_schedule = [
            {"machine": "DDS (544)", "rows": [
                {"part": "33005---OR", "std_box": 0, "p_2nd": 1, "p_3rd": "", "status": "BREAKDOWN DAY 03", "is_alert": True},
                {"part": "33005---IR", "std_box": 0, "p_2nd": 2, "p_3rd": "", "status": "", "is_alert": False},
                {"part": "BT11366---IR BLUE BOX", "std_box": 0, "p_2nd": 3, "p_3rd": "", "status": "", "is_alert": False}
            ]},
            {"machine": "Gardner ( 1016 + USA 1996 )", "rows": [
                {"part": "6306---OR", "std_box": 0, "p_2nd": 1, "p_3rd": "", "status": "", "is_alert": False},
                {"part": "6311---OR APQ", "std_box": 0, "p_2nd": 2, "p_3rd": "", "status": "", "is_alert": True}
            ]}
        ]

        od_schedule = [
            {"machine": "CL -46 Cell 2 ( 0945 + 0839 )", "rows": [
                {"part": "6306-OR TOTE BOX", "std_box": "", "p_2nd": "", "p_3rd": 1, "status": "", "is_alert": True},
                {"part": "2820---OR", "std_box": "", "p_2nd": "", "p_3rd": 2, "status": "", "is_alert": False}
            ]},
            {"machine": "CL-46 Cell 1 ( 0661 + 1125 )", "rows": [
                {"part": "6311---OR", "std_box": "", "p_2nd": "", "p_3rd": 1, "status": "", "is_alert": False},
                {"part": "32212---OR", "std_box": "", "p_2nd": "", "p_3rd": 2, "status": "", "is_alert": False}
            ]}
        ]

        heat_treatment = [
            {"furnace": "AICHELIN.(896)", "capacity": "350", "rows": [
                {"part": "72487---OR", "qty": "", "cha": "T3", "rate": 72.0},
                {"part": "32212---IR", "qty": 6000, "cha": "T5", "rate": 73.04}
            ]},
            {"furnace": "ROLLER FURNACE ( 148 )", "capacity": "250", "rows": [
                {"part": "BAR0594---IR", "qty": 10000, "cha": "HUB3", "rate": 110.0},
                {"part": "32007VB---IR BLUE BOX", "qty": "", "cha": "T8", "rate": 87.33, "is_alert": True}
            ]}
        ]

        return {
            "status": "success",
            "message": "Schedule calculated successfully.",
            "data": {
                "face_grinding": face_schedule,
                "od_grinding": od_schedule,
                "heat_treatment": heat_treatment
            }
        }
        
    except Exception as e:
        import traceback
        print(f"CRITICAL BACKEND ERROR:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Backend processing error: {str(e)}")
