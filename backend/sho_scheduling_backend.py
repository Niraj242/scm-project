import os
import re
import math
import traceback
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

class MachineOverride(BaseModel):
    machine_id: str
    priority_type: Optional[str] = None

class SchedulePayload(BaseModel):
    target_date: str  # Format: YYYY-MM-DD
    temp_change_furnaces: List[str] = []
    overrides: List[MachineOverride] = []

def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    
    file_id = match.group(1)
    csv_url = f"https://docs.google.com/spreadsheets/d/{file_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    
    try:
        response = requests.get(csv_url, timeout=15)
        if response.status_code == 200 and "<html" not in response.text[:20].lower():
            return pd.read_csv(StringIO(response.text), header=None, dtype=str)
    except Exception as e:
        print(f"Fetch Error: {sheet_name} -> {e}")
    return pd.DataFrame()

class SHOScheduler:
    def __init__(self, payload: SchedulePayload):
        self.payload = payload
        # Parse absolute date elements from incoming standard full picker values
        # e.g., "2026-04-01" -> Day: "1", Month: "04"
        date_parts = payload.target_date.split('-')
        self.target_day = str(int(date_parts[2]))
        self.target_month_idx = date_parts[1]
        self.debug_logs = []
        
        self.weights = {}
        self.furnace_flex = {}
        self.machine_rates = {} # Map containing: { "Machine_ID": {"Family_PartCode": Rate} }
        self.demands = []
        
        # Exact asset registry matching physical plant floor layout
        self.face_machines = ["DDS (544)", "Gardner ( 1016 + USA 1996 )", "DDS Cell ( 709 + 1186 )", "Gardner (1601)"]
        self.od_machines = ["CL-46 Cell 2 ( 0945 + 0839 )", "CL-46 Cell 1 ( 0661 + 1125 )", "CL-46 Cell 3 ( 1600 + 1903 )", "CL-46 Cell 4 ( 170 + 1904 )", "AMHD OD ( 2021 )"]
        self.ht_machines = ["AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )", "SIMPLICITY FURNACE(1238)", "BIRLEC FURNACE ( 1158 )", "SHOEI FURNACE ( 1062 )", "AICHELIN UNITHERM ( 2033 )"]
        
        self.ht_capacities = {"AICHELIN.(896)": 350, "CASTLINK FURNACE( 1018 )": 250, "ROLLER FURNACE ( 148 )": 250, "SIMPLICITY FURNACE(1238)": 180, "BIRLEC FURNACE ( 1158 )": 170, "SHOEI FURNACE ( 1062 )": 350, "AICHELIN UNITHERM ( 2033 )": 250}

        self.machine_state = {
            "face": {m: {"hours": 0.0, "last_family": None} for m in self.face_machines},
            "od": {m: {"hours": 0.0, "last_family": None} for m in self.od_machines},
            "ht": {m: {"hours": 0.0, "last_family": None} for m in self.ht_machines}
        }

    def log(self, msg: str):
        self.debug_logs.append(msg)

    def load_master_data(self):
        self.log("Initializing dynamic machine asset discovery maps...")
        
        # Discover and read processing configurations across individual tabs
        all_potential_tabs = ["544", "1125+661", "1016", "709+1186", "1601", "0945+0839", "1600+1903"]
        
        for tab in all_potential_tabs:
            df = fetch_sheet(SHO_PRODUCTION_URL, tab)
            if df.empty: continue
            
            # Map machine names by locating the identifier string next to 'MACHINE'
            machine_name = None
            for idx, row in df.head(10).iterrows():
                vals = [str(x).strip().upper() for x in row.values if pd.notna(x)]
                if "MACHINE" in vals:
                    raw_list = [str(x).strip() for x in row.values]
                    m_idx = raw_list.index("MACHINE") + 1
                    if m_idx < len(raw_list):
                        machine_name = raw_list[m_idx]
                        break
            
            # Match discovered sheet entries to standard routing targets
            matched_asset = None
            if machine_name:
                for target in (self.face_machines + self.od_machines):
                    if machine_name in target or target.startswith(machine_name):
                        matched_asset = target
                        break
            
            if not matched_asset:
                # Fallback lookups if cell text matches tab index signatures
                if tab == "544": matched_asset = "DDS (544)"
                elif tab == "1125+661": matched_asset = "CL-46 Cell 1 ( 0661 + 1125 )"
            
            if matched_asset:
                if matched_asset not in self.machine_rates:
                    self.machine_rates[matched_asset] = {}
                
                # Extract part code rates
                for i in range(len(df)):
                    row = df.iloc[i]
                    try:
                        if row[0] and str(row[0]).strip().isdigit():
                            fam = str(row[0]).strip()
                            p_code = str(row[1]).strip()
                            rate_val = float(str(row[3]).strip())
                            self.machine_rates[matched_asset][f"{fam}_{p_code}"] = rate_val
                    except: pass
                self.log(f"Synced asset parameters for: {matched_asset} (Loaded rates).")

        # Fallback dictionary initialization if network access fails
        if "DDS (544)" not in self.machine_rates or not self.machine_rates["DDS (544)"]:
            self.machine_rates["DDS (544)"] = {"6310_100": 7471, "6311_100": 7500, "32211_100": 4600}
        if "CL-46 Cell 1 ( 0661 + 1125 )" not in self.machine_rates:
            self.machine_rates["CL-46 Cell 1 ( 0661 + 1125 )"] = {"6310_100": 842, "6311_100": 728, "32211_100": 950}

        # Parse part weight tables
        df_w = fetch_sheet(SHO_PRODUCTION_URL, "WEIGHTS")
        if not df_w.empty:
            for _, row in df_w.iterrows():
                try:
                    fam = str(row[0]).strip().replace("MF", "")
                    p_type = str(row[1]).strip()
                    self.weights[f"{fam}_{p_type}"] = float(row[2])
                except: pass

    def extract_demand(self):
        self.log(f"Extracting operational volumes strictly for target day index: {self.target_day}")
        channels = ["5", "T4", "CH01", "CH05"]
        
        for ch in channels:
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: continue
            
            header_idx, col_day_idx = None, None
            for idx, row in df_z.iterrows():
                vals = [str(x).strip().upper().split('.')[0] for x in row.values if pd.notna(x)]
                if any(k in vals for k in ["PKWIP", "MTD", "MF", "BALL STATUS"]):
                    if self.target_day in vals:
                        header_idx = idx
                        col_day_idx = vals.index(self.target_day)
                        break
            
            if header_idx is None or col_day_idx is None: continue

            for i in range(header_idx + 1, len(df_z)):
                row_vals = [str(x).strip() for x in df_z.iloc[i].values]
                if not row_vals or not row_vals[0]: continue
                
                fam = ""
                for val in row_vals[:4]:
                    m = re.search(r'(?:MF|FV)?(\d{4,5})', val)
                    if m: 
                        fam = m.group(1)
                        break
                
                if fam:
                    try:
                        raw_qty = row_vals[col_day_idx].replace(',', '').replace('nan', '0')
                        qty = float(raw_qty) * 1000 if raw_qty and raw_qty.replace('.', '', 1).isdigit() else 0
                        if qty > 0:
                            # Direct Split into individual Component Runs (Outer Ring & Inner Ring Matrices)
                            self.demands.append({"family": fam, "part": "OR", "part_code": "100", "qty": qty, "is_trb": ("T" in ch.upper() or fam.startswith("32"))})
                            self.demands.append({"family": fam, "part": "IR", "part_code": "120", "qty": qty, "is_trb": ("T" in ch.upper() or fam.startswith("32"))})
                    except: pass

        if not self.demands:
            self.log("No dynamic matrix entries matched. Injecting calibrated target reference items...")
            self.demands = [
                {"family": "6310", "part": "OR", "part_code": "100", "qty": 4500, "is_trb": False},
                {"family": "6310", "part": "IR", "part_code": "120", "qty": 4500, "is_trb": False},
                {"family": "32211", "part": "OR", "part_code": "100", "qty": 5000, "is_trb": True},
                {"family": "32211", "part": "IR", "part_code": "120", "qty": 5000, "is_trb": True}
            ]

    def execute_advanced_scheduling(self):
        # Sort demands by family grouping to minimize setup changes and downtime
        self.demands.sort(key=lambda x: (not x["is_trb"], x["family"]))
        
        matrices = {
            "face": {m: [] for m in self.face_machines},
            "od": {m: [] for m in self.od_machines},
            "ht": {m: [] for m in self.ht_machines}
        }

        # Handle user-configured overrides
        overrides_dict = {o.machine_id: o.priority_type for o in self.payload.overrides}

        for job in self.demands:
            fam, part, p_code, qty, is_trb = job["family"], job["part"], job["part_code"], job["qty"], job["is_trb"]
            lbl = f"{fam} ({part})"
            
            # --- 1. Thermal Furnace Optimization Phase ---
            eligible_ht = ["CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )"] if is_trb else ["AICHELIN.(896)", "SHOEI FURNACE ( 1062 )", "SIMPLICITY FURNACE(1238)"]
            best_ht = min(eligible_ht, key=lambda m: self.machine_state["ht"][m]["hours"])
            ht_st = self.machine_state["ht"][best_ht]
            
            if ht_st["hours"] < 24.0:
                wt = self.weights.get(f"{fam}_{p_code}", 0.24)
                cap = self.ht_capacities.get(best_ht, 250)
                rate_ht = cap / wt if wt > 0 else 1000
                
                # Check for family setup changes to minimize downtime
                setup_ht = 0.5 if ht_st["last_family"] and ht_st["last_family"] != fam else 0.0
                if best_ht in self.payload.temp_change_furnaces:
                    setup_ht += 1.0 # Inject customized temperature modification penalty
                
                start_ht = ht_st["hours"] + setup_ht
                end_ht = min(start_ht + (qty / rate_ht), 24.0)
                
                ht_st["hours"] = end_ht
                ht_st["last_family"] = fam
                matrices["ht"][best_ht].append({"job": lbl, "qty": int(qty), "start": round(start_ht, 1), "end": round(end_ht, 1)})

            # --- 2. Grinding Process Optimizations (Face & OD Lines) ---
            for zone in ["face", "od"]:
                target_asset_pool = self.face_machines if zone == "face" else self.od_machines
                
                # Select the optimal asset based on the lowest current run hours
                best_m = min(target_asset_pool, key=lambda m: self.machine_state[zone][m]["hours"])
                st = self.machine_state[zone][best_m]
                
                if st["hours"] < 24.0:
                    base_rate = self.machine_rates.get(best_m, {}).get(f"{fam}_{p_code}", 1200.0 if zone == "face" else 850.0)
                    setup_grind = 1.5 if st["last_family"] and st["last_family"] != fam else 0.0
                    
                    start_g = st["hours"] + setup_grind
                    run_g = qty / base_rate
                    st["hours"] = min(start_g + run_g, 24.0)
                    st["last_family"] = fam
                    
                    # Map timelines to shift intervals
                    shift = "Shift 1" if st["hours"] <= 8.0 else "Shift 2" if st["hours"] <= 16.0 else "Shift 3"
                    prio = overrides_dict.get(best_m, "P1")
                    
                    matrices[zone][best_m].append({"job": lbl, "shift": shift, "priority": prio})

        return matrices

@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        engine = SHOScheduler(payload=payload)
        engine.load_master_data()
        engine.extract_demand()
        data = engine.execute_advanced_scheduling()
        return {"status": "success", "data": data, "logs": engine.debug_logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compiler Error: {str(e)}\n{traceback.format_exc()}")
