import os
import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote

router = APIRouter()

SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
DAILY_STORE_STOCK_URL = os.getenv("DAILY_STORE_STOCK_URL")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL") # NEW URL ADDED

class MachineOverride(BaseModel):
    machine_id: str
    priority_type: Optional[str] = None

class DirectChannelOverride(BaseModel):
    item_code: str
    direct_qty: float

class SchedulePayload(BaseModel):
    target_date: str  
    buffer_unit: str  # "Boxes", "Rings", or "Days"
    temp_change_furnaces: List[str] = []
    overrides: List[MachineOverride] = []
    direct_arrivals: List[DirectChannelOverride] = []

def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    try:
        res = requests.get(csv_url, timeout=15)
        if res.status_code == 200 and "<html" not in res.text[:20].lower():
            return pd.read_csv(StringIO(res.text), header=None, dtype=str)
    except: pass
    return pd.DataFrame()

class SHOScheduler:
    def __init__(self, payload: SchedulePayload):
        self.payload = payload
        date_parts = payload.target_date.split('-')
        self.target_day = str(int(date_parts[2])) 
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        self.formatted_date_sheet = f"{self.target_day.zfill(2)} {months[int(date_parts[1])-1]} {date_parts[0]}"
        
        self.physical_stock = {}
        self.rings_per_box = {} # Map containing: {"6310_OR": 80}
        self.shortage_matrix = []
        self.demands = []
        
        # FULL MACHINE LIST - Guaranteed exact mapping to physical layout
        self.face_machines = ["DDS (544)", "Gardner ( 1016 + USA 1996 )", "DDS Cell ( 709 + 1186 )", "Gardner (1601)"]
        self.od_machines = ["CL-46 Cell 2 ( 0945 + 0839 )", "CL-46 Cell 1 ( 0661 + 1125 )", "CL-46 Cell 3 ( 1600 + 1903 )", "CL-46 Cell 4 ( 170 + 1904 )", "AMHD OD ( 2021 )"]
        self.ht_machines = ["AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )", "SIMPLICITY FURNACE(1238)", "BIRLEC FURNACE ( 1158 )", "SHOEI FURNACE ( 1062 )", "AICHELIN UNITHERM ( 2033 )"]
        
        self.machine_state = {
            "face": {m: {"hours": 0.0, "last_family": None} for m in self.face_machines},
            "od": {m: {"hours": 0.0, "last_family": None} for m in self.od_machines},
            "ht": {m: {"hours": 0.0, "last_family": None} for m in self.ht_machines}
        }
        
    def load_consumption_master(self):
        # Fetch the Box/Ring quantity definitions
        df_boxes = fetch_sheet(BOX_RING_DATA_URL, "RING PER BOX.")
        if not df_boxes.empty:
            for idx, row in df_boxes.iterrows():
                try:
                    fam = str(row[0]).strip().replace("MF", "")
                    part = "OR" if str(row[1]).strip() == "100" else "IR"
                    box_qty = float(row[3]) if pd.notna(row[3]) else 0
                    if box_qty > 0:
                        self.rings_per_box[f"{fam}_{part}"] = box_qty
                except: pass

        # Fetch Store Stock
        df_stock = fetch_sheet(DAILY_STORE_STOCK_URL, self.formatted_date_sheet)
        if not df_stock.empty:
            for col in df_stock.columns:
                col_data = df_stock[col].dropna().astype(str).str.upper().tolist()
                if any("PHYSICAL" in val for val in col_data):
                    for idx, row in df_stock.iterrows():
                        try:
                            item_type = str(row[col-1]).strip() # Type usually precedes physical stk
                            stk = str(row[col]).strip().replace(',', '')
                            if item_type and stk.replace('.', '', 1).isdigit():
                                self.physical_stock[item_type] = float(stk)
                        except: pass

    def calculate_consumption_priority(self):
        direct_map = {d.item_code: d.direct_qty for d in self.payload.direct_arrivals}
        capped_demands = []

        for job in self.demands:
            item_key = f"{job['family']} {job['part']}"
            dict_key = f"{job['family']}_{job['part']}"
            req_qty_rings = job["qty"]
            
            # 1. Determine Box Size and Daily Consumption Rate
            box_size = self.rings_per_box.get(dict_key, 100) # Fallback 100 rings/box if missing
            daily_box_consumption = req_qty_rings / box_size
            
            # 2. Extract Available Buffer and Normalize to "Days of Cover"
            store_avail_raw = self.physical_stock.get(item_key, 0.0)
            direct_avail_raw = direct_map.get(item_key, 0.0)
            total_avail_raw = store_avail_raw + direct_avail_raw

            if self.payload.buffer_unit == "Boxes":
                total_rings_avail = total_avail_raw * box_size
            elif self.payload.buffer_unit == "Days":
                total_rings_avail = total_avail_raw * req_qty_rings
            else: # "Rings"
                total_rings_avail = total_avail_raw

            days_of_cover = total_rings_avail / req_qty_rings if req_qty_rings > 0 else 999
            job["cover_days"] = days_of_cover

            # 3. Calculate Ordering Shortages
            shortage_rings = req_qty_rings - total_rings_avail
            req_today = "no material required"
            if shortage_rings > 0:
                req_today = str(int(shortage_rings))
                job["qty"] = total_rings_avail # Cap production to what we physically have

            self.shortage_matrix.append({
                "item": item_key,
                "req_qty": int(req_qty_rings),
                "daily_box_burn": round(daily_box_consumption, 1),
                "store_avail": int(store_avail_raw),
                "req_today": req_today,
                "req_tomorrow": "0" 
            })
            
            if job["qty"] > 0:
                capped_demands.append(job)
                
        # 4. SORT BY CRITICAL PRIORITY: Lowest Days of Cover goes first!
        capped_demands.sort(key=lambda x: x["cover_days"])
        self.demands = capped_demands

    def execute_scheduling(self):
        # Pre-fill matrix explicitly so ALL machines render on UI, even if empty
        matrices = {
            "face": {m: [] for m in self.face_machines}, 
            "od": {m: [] for m in self.od_machines}, 
            "ht": {m: [] for m in self.ht_machines}
        }
        
        for job in self.demands:
            lbl = f"{job['family']} ({job['part']})"
            
            # HT
            best_ht = min(self.ht_machines, key=lambda m: self.machine_state["ht"][m]["hours"])
            if self.machine_state["ht"][best_ht]["hours"] < 24.0:
                start_h = self.machine_state["ht"][best_ht]["hours"]
                run_time = job["qty"] / 1500 # Default rate 
                end_h = min(start_h + run_time, 24.0)
                self.machine_state["ht"][best_ht]["hours"] = end_h
                matrices["ht"][best_ht].append({"job": lbl, "qty": int(job["qty"]), "start": round(start_h,1), "end": round(end_h,1)})
            
            # FACE & OD
            for zone, machines in [("face", self.face_machines), ("od", self.od_machines)]:
                best_m = min(machines, key=lambda m: self.machine_state[zone][m]["hours"])
                if self.machine_state[zone][best_m]["hours"] < 24.0:
                    st = self.machine_state[zone][best_m]
                    run_g = job["qty"] / 1000 
                    st["hours"] = min(st["hours"] + run_g, 24.0)
                    shift = "Shift 1" if st["hours"] <= 8.0 else "Shift 2" if st["hours"] <= 16.0 else "Shift 3"
                    matrices[zone][best_m].append({"job": lbl, "shift": shift, "priority": f"Cover: {round(job['cover_days'],1)}D"})
        
        return matrices

@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        engine = SHOScheduler(payload=payload)
        # Mocking Zeroset demand extraction for brevity
        engine.demands = [
            {"family": "6310", "part": "OR", "qty": 16000, "is_trb": False},
            {"family": "32211", "part": "IR", "qty": 12000, "is_trb": True},
            {"family": "32217", "part": "OR", "qty": 8000, "is_trb": True},
            {"family": "6311", "part": "IR", "qty": 4500, "is_trb": False}
        ]
        engine.load_consumption_master()
        engine.calculate_consumption_priority()
        
        sched_data = engine.execute_scheduling()
        return {
            "status": "success", 
            "data": sched_data, 
            "shortage_matrix": engine.shortage_matrix
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compiler Error: {str(e)}")
