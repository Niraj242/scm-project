import os
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI()

# CORS configuration to prevent frontend fetch errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with your Vercel URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment Variables for Google Sheets
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

class BufferEntry(BaseModel):
    part_type: str
    unit: str  # 'Boxes', 'Rings', 'Days'
    quantity: float
    component: str # 'IR' or 'OR'
    channel: str

class ScheduleRequest(BaseModel):
    target_date: str
    buffers: List[BufferEntry]

def fetch_sheet_data(url: str, sheet_name: str = None) -> pd.DataFrame:
    """Fetches sheet positionally to avoid duplicate column errors."""
    try:
        # Using header=None strictly avoids duplicate column name crashes
        df = pd.read_excel(url, sheet_name=sheet_name, header=None)
        # Clean empty/NaN/commas to 0.0 for numeric operations
        df = df.fillna(0.0)
        return df
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return pd.DataFrame()

def parse_zeroset_demand(df: pd.DataFrame, target_date: str) -> Dict[str, float]:
    """Finds MTD/PKWIP row, extracts date column, and parses family/type demands."""
    demand = {}
    # Find the row containing 'MTD' or 'PKWIP'
    target_col_idx = None
    for row_idx, row in df.iterrows():
        row_values = [str(val).strip().upper() for val in row.values]
        if 'MTD' in row_values or 'PKWIP' in row_values:
            # Assuming dates are in this row, find target_date column
            if target_date in row_values:
                target_col_idx = row_values.index(target_date)
            break
            
    if target_col_idx is None:
        return demand

    # Extract Families (MFXXXX -> XXXX) and Quantities (* 1000)
    for row_idx in range(len(df)):
        cell_val = str(df.iloc[row_idx, 0]).strip()
        if cell_val.startswith("MF"):
            family = cell_val.replace("MF", "")
            qty = float(df.iloc[row_idx, target_col_idx]) * 1000
            demand[family] = qty
            
    return demand

def calculate_shifts(required_qty: float, rate_per_hour: float, changeover_hrs: float) -> List[Dict]:
    """Buckets required production into 8-hour shifts (A, B, C)."""
    shifts = []
    remaining_qty = required_qty
    current_shift_capacity = 8.0 - changeover_hrs # Deduct setup time for the first shift
    
    shift_names = ["Shift 1 (A)", "Shift 2 (B)", "Shift 3 (C)"]
    shift_idx = 0
    
    while remaining_qty > 0 and shift_idx < 3:
        max_qty_in_shift = current_shift_capacity * rate_per_hour
        if remaining_qty <= max_qty_in_shift:
            shifts.append({"shift": shift_names[shift_idx], "qty": remaining_qty})
            remaining_qty = 0
        else:
            shifts.append({"shift": shift_names[shift_idx], "qty": max_qty_in_shift})
            remaining_qty -= max_qty_in_shift
            shift_idx += 1
            current_shift_capacity = 8.0 # Next shift has full 8 hours (unless another changeover occurs)
            
    return shifts

@app.post("/api/schedule")
async def generate_schedule(req: ScheduleRequest):
    """Core routing and calculation engine."""
    # 1. Fetch Data (Mocked URLs here for architecture demonstration)
    # zeroset_df = fetch_sheet_data(ZEROSET_URL)
    # weights_df = fetch_sheet_data(SHO_PRODUCTION_URL, "WEIGHTS")
    # ring_box_df = fetch_sheet_data(BOX_RING_DATA_URL, "RING PER BOX")
    
    # 2. Base Scheduling Logic
    # Calculate deficit = (ZeroSet Demand) - (Buffer converted to Rings)
    
    # 3. Dummy Response matching the requested Master Schedule shape
    return {
        "date": req.target_date,
        "face_od_grinding": [
            {
                "machine": "Gardner ( 1016 + USA 1996 )",
                "type": "Face",
                "std_box": 12,
                "shift_1": {"qty": 2000, "job": "6306---OR", "priority": "P1"},
                "shift_2": {"qty": 1500, "job": "6311---OR APQ", "priority": "P1"},
                "shift_3": {"qty": 0, "job": "", "priority": ""}
            },
            {
                "machine": "CL-46 Cell 2 ( 0945 + 0839 )",
                "type": "OD",
                "std_box": 8,
                "shift_1": {"qty": 3500, "job": "6306---OR TOTE BOX", "priority": "P1"},
                "shift_2": {"qty": 1000, "job": "2820---OR", "priority": "P2"},
                "shift_3": {"qty": 1000, "job": "6307---OR BLUE BOX", "priority": "P3"}
            }
        ],
        "heat_treatment": [
            {
                "furnace": "AICHELIN.(896)",
                "capacity": "350 kg/hr",
                "jobs": [
                    {"qty_kg": 72.00, "job": "72487---OR", "channel": "T3"},
                    {"qty_kg": 73.04, "job": "32212---IR", "channel": "T5"}
                ]
            },
            {
                "furnace": "CASTLINK FURNACE( 1018 )",
                "capacity": "250 kg/hr",
                "jobs": [
                    {"qty_kg": 12000, "job": "BT11366---OR", "channel": "T1"},
                    {"qty_kg": 15000, "job": "BB10596---OR", "channel": "CH01"}
                ]
            }
        ]
    }
