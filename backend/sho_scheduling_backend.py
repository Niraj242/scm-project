import os
import re
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import requests
from io import StringIO
import math

router = APIRouter()

# --- ENV VARIABLES ---
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
AVAILABLE_BUFFER_URL = os.getenv("AVAILABLE_BUFFER_URL")

class SchedulePayload(BaseModel):
    target_date: str  # e.g., "01 APR 2026"

def fetch_sheet_as_df(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Robustly fetches Google Sheets as CSV, ignoring URL formatting issues."""
    if not base_url: 
        return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: 
        return pd.DataFrame()
    
    file_id = match.group(1)
    from urllib.parse import quote
    safe_sheet_name = quote(sheet_name.strip())
    csv_url = f"https://docs.google.com/spreadsheets/d/{file_id}/gviz/tq?tqx=out:csv&sheet={safe_sheet_name}"
    
    response = requests.get(csv_url)
    if response.status_code != 200 or "<html" in response.text[:20].lower():
        return pd.DataFrame() 
    
    try:
        return pd.read_csv(StringIO(response.text))
    except:
        return pd.DataFrame()

def extract_family(raw_val) -> str:
    """Extracts base family from messy string (e.g., 'MF6310' -> '6310')"""
    if pd.isna(raw_val): 
        return ""
    val_str = str(raw_val).strip()
    match = re.search(r'(?:MF)?(\d+)', val_str)
    return match.group(1) if match else val_str.split()[0]

class SHOScheduler:
    def __init__(self, target_date: str):
        self.target_date = target_date
        self.weights = {}
        self.furnace_flex = {}
        self.channel_routings = {}
        self.demands = {}
        
        # Hardcoded Machine Arrays matching your exact Excel Layout format
        self.ht_machines = [
            "AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )", 
            "SIMPLICITY FURNACE(1238)", "BIRLEC FURNACE ( 1158 )", "SHOEI FURNACE ( 1062 )", 
            "AICHELIN UNITHERM ( 2033 )"
        ]
        self.face_machines = [
            "DDS (544)", "Gardner ( 1016 + USA 1996 )", "DDS Cell ( 709 + 1186 )", "Gardner (1601)"
        ]
        self.od_machines = [
            "CL-46 Cell 2 ( 0945 + 0839 )", "CL-46 Cell 1 ( 0661 + 1125 )", 
            "CL-46 Cell 3 ( 1600 + 1903 )", "CL-46 Cell 4 ( 170 + 1904 )", "AMHD OD ( 2021 )"
        ]

    def load_master_data(self):
        """Loads weights and Furnace Flex rules"""
        df_w = fetch_sheet_as_df(SHO_PRODUCTION_URL, "WEIGHTS")
        if not df_w.empty:
            for _, row in df_w.dropna(subset=['types', 'ir/or']).iterrows():
                fam = str(row['types']).strip()
                part = "OR" if str(row['ir/or']).strip() == "100" else "IR"
                self.weights[(fam, part)] = float(row.get('weight per ring', 0.2))

        df_f = fetch_sheet_as_df(SHO_PRODUCTION_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for _, row in df_f.dropna(subset=['Comp Level 1']).iterrows():
                comp = str(row['Comp Level 1']).strip()
                primary = str(row.get('Primary Furnace', '')).strip().upper()
                self.furnace_flex[comp] = primary

    def parse_routing(self):
        """Reads your daily buffer to figure out if HT, Face, OD are needed"""
        df_b = fetch_sheet_as_df(AVAILABLE_BUFFER_URL, self.target_date)
        if df_b.empty: 
            return
        
        channel_cols = [col for col in df_b.columns if "CH" in str(col).upper() or "T" in str(col).upper()]
        face_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("Face Buffer", case=False, na=False)].index
        od_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("OD Buffer", case=False, na=False)].index
        
        for col in channel_cols:
            has_face = False
            has_od = False
            if len(face_idx) > 0 and pd.notna(df_b.at[face_idx[0], col]): 
                has_face = True
            if len(od_idx) > 0 and pd.notna(df_b.at[od_idx[0], col]): 
                has_od = True
            
            if has_face and has_od: 
                self.channel_routings[col] = ["HT", "FACE", "OD"]
            elif has_face: 
                self.channel_routings[col] = ["HT", "FACE"]
            elif has_od: 
                self.channel_routings[col] = ["HT", "OD"]
            else: 
                self.channel_routings[col] = ["HT"]

    def extract_demand(self):
        """Combines 2 Days Demand to minimize changeovers"""
        try:
            day_idx = int(self.target_date.split()[0])
        except:
            day_idx = 1

        for ch in self.channel_routings.keys():
            df_z = fetch_sheet_as_df(ZEROSET_URL, ch)
            if df_z.empty: 
                continue
            
            for _, row in df_z.iterrows():
                raw_mf = row.get('MF') or row.get('mf') or row.get('FV')
                if pd.notna(raw_mf):
                    family = extract_family(raw_mf)
                    # Convert parts from 'k' to actual qty
                    d1 = float(row.get(str(day_idx), 0)) * 1000
                    d2 = float(row.get(str(day_idx + 1), 0)) * 1000
                    if d1 > 0:
                        part_type = "OR" if "OR" in str(row.get('PART', '')).upper() else "IR"
                        if ch not in self.demands: 
                            self.demands[ch] = []
                        self.demands[ch].append({"family": family, "part": part_type, "qty": d1 + d2})

    def generate_matrix_schedule(self) -> Dict[str, Any]:
        """Builds the final nested dictionary matching your specific shop floor template"""
        
        # Initialize the output matrix structure
        schedule = {
            "face": {m: [] for m in self.face_machines},
            "od": {m: [] for m in self.od_machines},
            "ht": {m: [] for m in self.ht_machines}
        }
        
        for ch, demands in self.demands.items():
            route = self.channel_routings.get(ch, ["HT"])
            
            for d in demands:
                fam = d["family"]
                part = d["part"]
                qty = d["qty"]
                job_name = f"{fam}---{part}"
                
                # --- HEAT TREATMENT ---
                # Default logic: assign to CASTLINK if missing flex rule
                furnace_target = "CASTLINK FURNACE( 1018 )"
                if fam in self.furnace_flex:
                    f_flex = self.furnace_flex[fam]
                    for hm in self.ht_machines:
                        if f_flex in hm:
                            furnace_target = hm
                            break
                
                schedule["ht"][furnace_target].append({
                    "job": job_name,
                    "qty": qty,
                    "channel": ch
                })
                
                # --- FACE GRINDING ---
                if "FACE" in route:
                    target_face = self.face_machines[0] # Default DDS 544
                    if "T" in ch: 
                        target_face = self.face_machines[1] # Gardner for TRB
                    schedule["face"][target_face].append({"job": job_name, "shift": "1", "priority": "P1"})
                    
                # --- OD GRINDING ---
                if "OD" in route:
                    target_od = self.od_machines[0] # Default Cell 2
                    if "T" in ch: 
                        target_od = self.od_machines[1] # Cell 1 for TRB
                    schedule["od"][target_od].append({"job": job_name, "shift": "1", "priority": "P1"})
                    
        return schedule

@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        engine = SHOScheduler(target_date=payload.target_date)
        engine.load_master_data()
        engine.parse_routing()
        engine.extract_demand()
        
        matrix_data = engine.generate_matrix_schedule()
        return {"status": "success", "data": matrix_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
