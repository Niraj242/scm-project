import os
import math
import uvicorn
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENVIRONMENT VARIABLES ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

# --- DATA MODELS ---
class BufferEntry(BaseModel):
    part_type: str
    unit: str  # 'Boxes', 'Rings', 'Days'
    quantity: float
    component: str # 'IR' (120) or 'OR' (100)
    channel: str

class ScheduleRequest(BaseModel):
    target_date: str
    buffers: List[BufferEntry]

# --- SHEET FETCHING ENGINE ---
def fetch_sheet_data(url: str, sheet_name: str = None) -> pd.DataFrame:
    """Positional read to prevent duplicate column Pandas crashes."""
    try:
        if not url: return pd.DataFrame()
        df = pd.read_excel(url, sheet_name=sheet_name, header=None)
        return df.fillna(0.0)
    except Exception as e:
        print(f"Fetch Error [{sheet_name or 'Default'}]: {e}")
        return pd.DataFrame()

# --- ZEROSET PARSING ENGINE ---
def get_zeroset_demand(df: pd.DataFrame, target_date: str) -> Dict[str, float]:
    """Finds MTD/PKWIP row, maps the date column, extracts families (* 1000)."""
    demand = {}
    if df.empty: return demand

    target_col_idx = None
    for row_idx, row in df.iterrows():
        row_values = [str(val).strip().upper() for val in row.values]
        if 'MTD' in row_values or 'PKWIP' in row_values:
            for idx, val in enumerate(row_values):
                if target_date in val:
                    target_col_idx = idx
                    break
            if target_col_idx is not None:
                break
                
    if target_col_idx is None:
        return demand

    for row_idx in range(len(df)):
        cell_val = str(df.iloc[row_idx, 0]).strip().upper()
        # Handle "MFXXXX", "UC 205", or raw family names
        family = cell_val.replace("MF", "").strip() if cell_val.startswith("MF") else cell_val
        if family:
            try:
                qty_thousands = float(df.iloc[row_idx, target_col_idx])
                if qty_thousands > 0:
                    demand[family] = qty_thousands * 1000
            except ValueError:
                continue
    return demand

# --- MASTER DATA PARSERS ---
def get_weights(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Extracts weights per ring from SHO_PRODUCTION -> WEIGHTS. IR=120, OR=100"""
    weights = {} # Format: {'6306': {'100': 0.182, '120': 0.150}}
    # Assuming positional columns: Type, IR/OR code, Weight
    if df.empty: return weights
    for row_idx in range(1, len(df)):
        part_type = str(df.iloc[row_idx, 0]).strip().upper()
        comp_code = str(df.iloc[row_idx, 1]).strip()
        weight = float(df.iloc[row_idx, 2])
        
        if part_type not in weights:
            weights[part_type] = {}
        weights[part_type][comp_code] = weight
    return weights

def get_box_capacities(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """Extracts rings/box from BOX_RING_DATA."""
    capacities = {}
    if df.empty: return capacities
    for row_idx in range(1, len(df)):
        part_type = str(df.iloc[row_idx, 0]).strip().upper()
        try:
            or_cap = int(df.iloc[row_idx, 1])
            ir_cap = int(df.iloc[row_idx, 2])
            capacities[part_type] = {'100': or_cap, '120': ir_cap}
        except:
            continue
    return capacities

# --- SCHEDULING ENGINES ---
def schedule_heat_treatment(demand: Dict, weights: Dict) -> List[Dict]:
    """Routes to 7 specific furnaces handling capacities & 30m changeover (0.5 hrs)."""
    furnaces = [
        {"name": "AICHELIN.(896)", "cap": 350, "jobs": [], "hrs_used": 0},
        {"name": "SHOEI FURNACE (1062)", "cap": 350, "jobs": [], "hrs_used": 0},
        {"name": "CASTLINK FURNACE(1018)", "cap": 250, "jobs": [], "hrs_used": 0},
        {"name": "AICHELIN UNITHERM(2033)", "cap": 250, "jobs": [], "hrs_used": 0},
        {"name": "ROLLER FURNACE(148)", "cap": 250, "jobs": [], "hrs_used": 0},
        {"name": "SIMPLICITY FURNACE(1238)", "cap": 180, "jobs": [], "hrs_used": 0},
        {"name": "BIRLEC FURNACE (1158)", "cap": 170, "jobs": [], "hrs_used": 0},
    ]
    
    changeover_hrs = 0.5
    
    for part, qty in demand.items():
        # Default fallback weight if missing in master data
        weight_per_ring = weights.get(part, {}).get('100', 0.2) 
        total_kg = qty * weight_per_ring
        
        # Find furnace with available 24h capacity
        for f in furnaces:
            req_hrs = (total_kg / f['cap']) + (changeover_hrs if f['jobs'] else 0)
            if f['hrs_used'] + req_hrs <= 24.0:
                f['jobs'].append({
                    "job": part, 
                    "qty_kg": round(total_kg, 2), 
                    "channel": "Auto-Route"
                })
                f['hrs_used'] += req_hrs
                break
                
    return furnaces

def schedule_face_od_grinding(demand: Dict, box_caps: Dict) -> List[Dict]:
    """Buckets production into Shifts A, B, C. Enforces 2 HR changeovers."""
    machine_schedule = []
    
    # Mocking machine capacities from sheet layout you provided
    mock_machines = [
        {"name": "544 Gardner", "type": "Face", "std_hr": 7771, "box_hr": 12},
        {"name": "CL-46 Cell", "type": "OD", "std_hr": 7471, "box_hr": 17}
    ]
    
    changeover_hrs = 2.0
    shift_hours = [8.0, 8.0, 8.0] # Shift 1, Shift 2, Shift 3
    
    for m in mock_machines:
        m_data = {
            "machine": m["name"],
            "type": m["type"],
            "std_box": m["box_hr"],
            "shifts": [{"shift": "1", "qty": 0, "job": "", "priority": ""},
                       {"shift": "2", "qty": 0, "job": "", "priority": ""},
                       {"shift": "3", "qty": 0, "job": "", "priority": ""}]
        }
        
        # Simple distribution logic across shifts
        for part, qty in demand.items():
            remaining_qty = qty
            
            for i in range(3):
                if remaining_qty <= 0: break
                
                # Deduct changeover if a job is already in this shift
                available_hrs = shift_hours[i] - (changeover_hrs if m_data["shifts"][i]["job"] else 0)
                if available_hrs <= 0: continue
                
                max_qty = available_hrs * m["std_hr"]
                
                if max_qty > 0:
                    produce_qty = min(remaining_qty, max_qty)
                    m_data["shifts"][i]["qty"] = int(produce_qty)
                    m_data["shifts"][i]["job"] = part
                    m_data["shifts"][i]["priority"] = "P1"
                    
                    remaining_qty -= produce_qty
                    shift_hours[i] -= (produce_qty / m["std_hr"])

        # Flatten shifts for the frontend mapping
        flat_data = {
            "machine": m_data["machine"],
            "type": m_data["type"],
            "std_box": m_data["std_box"],
            "shift_1": m_data["shifts"][0],
            "shift_2": m_data["shifts"][1],
            "shift_3": m_data["shifts"][2],
        }
        machine_schedule.append(flat_data)
        
    return machine_schedule

# --- API ENDPOINT ---
@app.post("/api/schedule")
async def generate_schedule(req: ScheduleRequest):
    """Main routing endpoint"""
    try:
        # 1. Fetch live sheets
        zeroset_df = fetch_sheet_data(ZEROSET_URL)
        weights_df = fetch_sheet_data(SHO_PRODUCTION_URL, "WEIGHTS")
        box_df = fetch_sheet_data(BOX_RING_DATA_URL, "RING PER BOX")
        
        # 2. Parse base data
        raw_demand = get_zeroset_demand(zeroset_df, req.target_date)
        weights = get_weights(weights_df)
        box_caps = get_box_capacities(box_df)
        
        # 3. Apply Buffers (Convert UI Buffer input -> Rings -> subtract from raw demand)
        net_demand = raw_demand.copy()
        for buf in req.buffers:
            part = buf.part_type.upper()
            if part in net_demand:
                comp_code = '120' if buf.component == 'IR' else '100'
                ring_qty = 0
                
                if buf.unit == 'Boxes':
                    ring_qty = buf.quantity * box_caps.get(part, {}).get(comp_code, 500)
                elif buf.unit == 'Days':
                    # 1 Day buffer = that day's full requirement
                    ring_qty = buf.quantity * raw_demand[part] 
                else:
                    ring_qty = buf.quantity # Already in rings
                    
                net_demand[part] = max(0, net_demand[part] - ring_qty)

        # 4. Generate Sub-Schedules
        ht_schedule = schedule_heat_treatment(net_demand, weights)
        grinding_schedule = schedule_face_od_grinding(net_demand, box_caps)
        
        return {
            "date": req.target_date,
            "face_od_grinding": grinding_schedule,
            "heat_treatment": [f for f in ht_schedule if f["jobs"]] # Only return active furnaces
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- MANDATORY BLOCK FOR RENDER PORT BINDING ---
if __name__ == "__main__":
    # Render assigns the port dynamically. If it fails, default to 8000.
    port = int(os.environ.get("PORT", 8000))
    # Listen on 0.0.0.0 to allow external connections from Render's load balancer
    uvicorn.run("sho_scheduling_backend:app", host="0.0.0.0", port=port)
