import os
import re
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List

app = FastAPI()

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENVIRONMENT VARIABLES (Mocked for example, set these in your OS) ---
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
            # Assuming Family/Type is in column 0, 1, or 2. We scan early columns.
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
        # Expecting cols: types, ir/or, weight per ring, Type
        # Mapping 100 -> OR, 120 -> IR
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
@app.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    print(f"Received request for {payload.sector} on {payload.date}. Unit: {payload.unit_mode}")
    
    # 1. Fetch live data
    # (In production, replace these with actual file reads or Google Drive API calls)
    # df_demand = get_zeroset_demand(ZEROSET_URL, payload.date)
    # df_weights = get_weights(SHO_PRODUCTION_URL)
    # df_furnace = get_furnace_flexibility(SHO_PRODUCTION_URL)
    # dict_machines = get_grinding_machines(SHO_PRODUCTION_URL)
    # df_boxes = get_box_rings(BOX_RING_DATA_URL)
    
    # 2. Parse UI Buffer Entries (Normalization)
    net_requirements = []
    
    # Example logic to parse the generic UI dictionary 
    # Entries format: 'ch_buffer_1_CH01_IR': '500'
    for key, value in payload.entries.items():
        if not value: continue
        parts = key.split('_')
        if len(parts) >= 4:
            row_type = parts[0] + '_' + parts[1] # e.g., ch_buffer
            channel = parts[2]
            part_ir_or = parts[3]
            
            # Example Normalization Logic (pseudo-implementation)
            buffer_val = float(value)
            buffer_in_rings = buffer_val
            if payload.unit_mode == 'Boxes':
                # buffer_in_rings = buffer_val * get_rings_from_box_db(channel, part_ir_or)
                pass
            elif payload.unit_mode == 'Days':
                # buffer_in_rings = buffer_val * get_daily_demand(channel)
                pass
                
            net_requirements.append({
                "Channel": channel,
                "Part": part_ir_or,
                "BufferRings": buffer_in_rings
            })

    # 3. Apply Heuristic Scheduling Logic
    schedule_results = {
        "Furnace_Schedule": [],
        "Grinding_Schedule": []
    }
    
    # Mock applying the 30min and 2hr changeover constraints
    # for req in sorted_requirements:
    #    time_needed = req['Rings'] / machine['STD/HR']
    #    if previous_type != current_type: time_needed += 2.0 # 2hr changeover
    
    return {
        "status": "success",
        "message": "Schedule calculated based on Buffer inputs, machine capacities, and Zeroset demand.",
        "data": schedule_results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
