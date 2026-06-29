import os
import re
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

# Initialize as a router instead of a standalone app
router = APIRouter()

# --- ENVIRONMENT VARIABLES ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "zeroset_path.xlsx")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "sho_production_path.xlsx")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "box_ring_path.xlsx")

# --- PYDANTIC MODELS (Payload from React) ---
class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

# --- HELPER FUNCTIONS ---
def extract_family(val):
    if pd.isna(val): return None
    val_str = str(val).strip().upper()
    match = re.search(r'MF(\d+)', val_str)
    if match: return match.group(1)
    return val_str

# --- DATA PIPELINES ---
def get_zeroset_demand(url, target_date):
    """Extracts Date-specific demand and bearing family."""
    try:
        df = pd.read_excel(url, header=None)
        # Find row with MTD or PKWIP
        date_row_mask = df.apply(lambda r: r.astype(str).str.contains('MTD|PKWIP').any(), axis=1)
        if not date_row_mask.any(): return pd.DataFrame()
        
        date_row_idx = df[date_row_mask].index[0]
        date_row = df.iloc[date_row_idx].astype(str)
        
        # Match user date
        try:
            target_col_idx = date_row[date_row.str.contains(target_date)].index[0]
        except IndexError:
            return pd.DataFrame() # Date not found

        demand_data = []
        for idx in range(date_row_idx + 1, len(df)):
            raw_family = df.iloc[idx, 0] 
            demand_val = df.iloc[idx, target_col_idx]
            
            if pd.notna(demand_val) and str(demand_val).replace('.', '', 1).isdigit():
                family = extract_family(raw_family)
                demand_data.append({
                    'Family': family,
                    'Demand_Rings': float(demand_val) * 1000
                })
        return pd.DataFrame(demand_data).groupby('Family').sum().reset_index()
    except Exception as e:
        print(f"Error reading Zeroset: {e}")
        return pd.DataFrame()

def get_weights(url):
    """Maps Family & Part (100/120) to kg per ring."""
    try:
        df = pd.read_excel(url, sheet_name='WEIGHTS')
        df['PartCode'] = df['ir/or'].map({100: 'OR', 120: 'IR'})
        return df
    except:
        return pd.DataFrame()

def get_furnace_flexibility(url):
    """Maps items to Primary and Alt furnaces."""
    try:
        return pd.read_excel(url, sheet_name='Furnace Type Flexibility')
    except:
        return pd.DataFrame()

def get_grinding_machines(url):
    """Parses dynamic sheets like 544, Gardner BG1."""
    machines = {}
    try:
        xls = pd.ExcelFile(url)
        skip_sheets = ['WEIGHTS', 'Furnace Type Flexibility']
        for sheet in xls.sheet_names:
            if sheet in skip_sheets: continue
            
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
            start_cells = np.where(df == 'MACHINE')
            if not start_cells[0].size: continue
            
            r, c = start_cells[0][0], start_cells[1][0]
            machine_num = df.iloc[r, c+1]
            process = df.iloc[r, c+2] # Face or OD
            
            headers = df.iloc[r+1]
            data = df.iloc[r+2:].copy()
            data.columns = headers
            data['PART'] = data['PART'].map({100: 'OR', 120: 'IR'})
            
            machines[str(machine_num)] = {
                'Process': process,
                'Rates': data[['TYPE', 'PART', 'STD/HR', 'Boxes/hr', 'Rings/Box']].dropna().to_dict('records')
            }
    except:
        pass
    return machines

def get_box_rings(url):
    """Gets Rings per box mapping."""
    try:
        df = pd.read_excel(url, sheet_name='RING PER BOX.')
        return df
    except:
        return pd.DataFrame()

# --- MAIN ENDPOINT ---
# Use @router instead of @app
@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        print(f"Received request for {payload.sector} on {payload.date}. Unit: {payload.unit_mode}")
        
        net_requirements = []
        
        for key, value in payload.entries.items():
            # Skip empty strings, nulls, or pure whitespace
            if not value or str(value).strip() == "": 
                continue
                
            parts = key.split('_')
            if len(parts) >= 4:
                row_type = parts[0] + '_' + parts[1] 
                channel = parts[2]
                part_ir_or = parts[3]
                
                # Safely attempt to convert the input to a float
                try:
                    buffer_val = float(value)
                except ValueError:
                    print(f"Warning: Could not convert '{value}' to a number for {key}")
                    continue # Skip invalid numbers instead of crashing
                
                buffer_in_rings = buffer_val
                
                net_requirements.append({
                    "Channel": channel,
                    "Part": part_ir_or,
                    "BufferRings": buffer_in_rings
                })

        schedule_results = {
            "Furnace_Schedule": [],
            "Grinding_Schedule": []
        }
        
        return {
            "status": "success",
            "message": "Schedule calculated successfully.",
            "data": schedule_results,
            "parsed_requirements": net_requirements # Sending this back so you can debug
        }
        
    except Exception as e:
        # Catch ANY python crash, print it to Render logs, and send it cleanly to React
        import traceback
        error_details = traceback.format_exc()
        print(f"CRITICAL BACKEND ERROR:\n{error_details}")
        
        # Raise a proper HTTP Exception so CORS headers are preserved
        raise HTTPException(
            status_code=500, 
            detail=f"Backend processing error: {str(e)}"
        )


    
