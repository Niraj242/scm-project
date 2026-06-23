import os
import re
import math
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import requests
from io import StringIO

router = APIRouter()

# --- ENV VARIABLES ---
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
AVAILABLE_BUFFER_URL = os.getenv("AVAILABLE_BUFFER_URL")

# Base capacities (Kg/Hr)
FURNACE_CAPACITY_KG = {
    "AICHELIN.(896)": 350.0,
    "CASTLINK FURNACE( 1018 )": 250.0,
    "ROLLER FURNACE ( 148 )": 250.0,
    "SIMPLICITY FURNACE(1238)": 180.0,
    "BIRLEC FURNACE ( 1158 )": 170.0,
    "SHOEI FURNACE ( 1062 )": 350.0,
    "AICHELIN UNITHERM ( 2033 )": 250.0
}

class SequenceRule(BaseModel):
    before_job: str
    after_job: str

class MachineOverride(BaseModel):
    machine_id: str
    priority_type: Optional[str] = None
    sequence_rules: Optional[List[SequenceRule]] = []

class SchedulePayload(BaseModel):
    target_date: str
    temp_change_furnaces: List[str] = []
    overrides: List[MachineOverride] = []

def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    
    file_id = match.group(1)
    from urllib.parse import quote
    csv_url = f"https://docs.google.com/spreadsheets/d/{file_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    
    try:
        response = requests.get(csv_url, timeout=15)
        if response.status_code == 200 and "<html" not in response.text[:20].lower():
            df = pd.read_csv(StringIO(response.text))
            df.columns = [str(c).strip() for c in df.columns]
            return df
    except:
        pass
    return pd.DataFrame()

def extract_family(raw_val) -> str:
    """Extracts family from 'MF32211' or '32211 J2/Q'"""
    if pd.isna(raw_val): return ""
    val_str = str(raw_val).strip()
    match = re.search(r'(?:MF)?(\d+)', val_str)
    return match.group(1) if match else val_str.split()[0]

class SHOScheduler:
    def __init__(self, payload: SchedulePayload):
        self.payload = payload
        self.target_date = payload.target_date
        self.weights = {}
        self.furnace_flex = {}
        self.channel_routings = {}
        self.demands = []
        
        self.ht_machines = list(FURNACE_CAPACITY_KG.keys())
        self.face_machines = ["DDS (544)", "Gardner ( 1016 + USA 1996 )", "DDS Cell ( 709 + 1186 )", "Gardner (1601)"]
        self.od_machines = ["CL-46 Cell 2 ( 0945 + 0839 )", "CL-46 Cell 1 ( 0661 + 1125 )", "CL-46 Cell 3 ( 1600 + 1903 )", "CL-46 Cell 4 ( 170 + 1904 )"]

        self.machine_state = {
            "face": {m: {"last_fam": None, "hours": 0.0} for m in self.face_machines},
            "od": {m: {"last_fam": None, "hours": 0.0} for m in self.od_machines},
            "ht": {m: {"last_fam": None, "hours": 0.0} for m in self.ht_machines}
        }

    def load_master_data(self):
        # Load Weights (100=OR, 120=IR)
        df_w = fetch_sheet(SHO_PRODUCTION_URL, "WEIGHTS")
        if not df_w.empty:
            for _, row in df_w.dropna(subset=['types', 'ir/or']).iterrows():
                fam = str(row['types']).strip()
                part = "OR" if str(row['ir/or']).strip() == "100" else "IR"
                self.weights[(fam, part)] = float(row.get('weight per ring', 0.2))

        # Load Furnace Flexibility
        df_f = fetch_sheet(SHO_PRODUCTION_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for _, row in df_f.dropna(subset=['Comp Level 1']).iterrows():
                comp = str(row['Comp Level 1']).strip()
                self.furnace_flex[comp] = str(row.get('Primary Furnace', '')).strip().upper()

    def parse_routing(self):
        """Reads daily buffer to reverse engineer required paths based on Face/OD blanks"""
        df_b = fetch_sheet(AVAILABLE_BUFFER_URL, self.target_date)
        if df_b.empty: return
        
        channel_cols = [col for col in df_b.columns if "CH" in str(col).upper() or "T" in str(col).upper()]
        face_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("Face Buffer", case=False, na=False)].index
        od_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("OD Buffer", case=False, na=False)].index
        
        for col in channel_cols:
            has_face = len(face_idx) > 0 and pd.notna(df_b.at[face_idx[0], col])
            has_od = len(od_idx) > 0 and pd.notna(df_b.at[od_idx[0], col])
            
            if has_face and has_od: self.channel_routings[col] = ["HT", "FACE", "OD"]
            elif has_face: self.channel_routings[col] = ["HT", "FACE"]
            elif has_od: self.channel_routings[col] = ["HT", "OD"]
            else: self.channel_routings[col] = ["HT"]

    def extract_demand(self):
        """Finds Zeroset headers dynamically, grabs 2-day demand, converts 'k' unit to total rings"""
        try: day_idx = int(self.target_date.split()[0])
        except: day_idx = 1

        for ch, route in self.channel_routings.items():
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: continue
            
            # Find actual header row
            header_row_idx = None
            for idx, row in df_z.iterrows():
                if any(x in str(row.values).upper() for x in [" MF", "'MF", " FV", "TYPE"]):
                    header_row_idx = idx
                    break
            
            if header_row_idx is not None:
                df_z.columns = df_z.iloc[header_row_idx]
                df_z = df_z.drop(index=list(range(header_row_idx + 1)))

            for _, row in df_z.iterrows():
                raw_mf = row.get('MF') or row.get('FV')
                if pd.notna(raw_mf):
                    fam = extract_family(raw_mf)
                    try:
                        # Values are in 'k', so multiply by 1000
                        d1 = float(str(row.get(str(day_idx), 0)).replace(',','')) * 1000
                        d2 = float(str(row.get(str(day_idx+1), 0)).replace(',','')) * 1000
                        total_qty = d1 + d2
                    except:
                        total_qty = 0

                    if total_qty > 0:
                        part = "OR" if "OR" in str(row.get('PART', '')).upper() else "IR"
                        self.demands.append({"channel": ch, "family": fam, "part": part, "qty": total_qty, "route": route})

        # Group by family to naturally batch setups together
        self.demands.sort(key=lambda x: x["family"])

    def process_grinding(self, group: str, fam: str, qty: float, is_trb: bool):
        machines = self.face_machines if group == "face" else self.od_machines
        # Simulated Rate - later replaced by STD/HR parsing logic
        rate_per_hr = 1200.0 if group == "face" else 900.0 
        
        eligible = [m for m in machines if "1016" in m or "Cell 1" in m] if is_trb else machines
        best_m = eligible[0]
        min_end = float('inf')

        for m in eligible:
            st = self.machine_state[group][m]
            setup = 2.0 if st["last_fam"] and st["last_fam"] != fam else 0.0
            proj = st["hours"] + setup + (qty / rate_per_hr)
            if proj < min_end:
                min_end = proj
                best_m = m

        st = self.machine_state[group][best_m]
        st["hours"] += (2.0 if st["last_fam"] and st["last_fam"] != fam else 0.0)
        shift = math.floor(st["hours"] / 8) + 1
        st["hours"] += (qty / rate_per_hr)
        st["last_fam"] = fam
        return best_m, f"Shift {min(int(shift), 3)}"

    def generate_schedule(self) -> Dict[str, Any]:
        schedule = {"face": {m: [] for m in self.face_machines}, "od": {m: [] for m in self.od_machines}, "ht": {m: [] for m in self.ht_machines}}
        
        for d in self.demands:
            fam, part, qty, ch, route = d["family"], d["part"], d["qty"], d["channel"], d["route"]
            job_name = f"{fam}---{part}"
            is_trb = "T" in ch.upper()

            # 1. HEAT TREATMENT
            furnace = "CASTLINK FURNACE( 1018 )"
            if fam in self.furnace_flex:
                for hm in self.ht_machines:
                    if self.furnace_flex[fam] in hm.upper(): furnace = hm; break

            f_state = self.machine_state["ht"][furnace]
            
            # Quenching Temp manual override logic (+1.5hr)
            quench_penalty = 1.5 if furnace in self.payload.temp_change_furnaces else 0.0
            setup_penalty = 0.5 if f_state["last_fam"] and f_state["last_fam"] != fam else 0.0
            
            kg_hr_cap = FURNACE_CAPACITY_KG[furnace]
            weight_per_ring = self.weights.get((fam, part), 0.25)
            rings_per_hr = kg_hr_cap / weight_per_ring
            
            start_time = f_state["hours"] + setup_penalty + quench_penalty
            end_time = start_time + (qty / rings_per_hr) + 3.5 # Adding 3.5hr exit cycle
            
            f_state["hours"] = end_time
            f_state["last_fam"] = fam

            schedule["ht"][furnace].append({
                "job": job_name, "qty": int(qty), "channel": ch, "start": round(start_time, 1), "end": round(end_time, 1)
            })

            # 2. FACE & OD GRINDING
            if "FACE" in route:
                m, s = self.process_grinding("face", fam, qty, is_trb)
                schedule["face"][m].append({"job": job_name, "shift": s, "priority": "P1"})
            
            if "OD" in route:
                m, s = self.process_grinding("od", fam, qty, is_trb)
                schedule["od"][m].append({"job": job_name, "shift": s, "priority": "P1"})

        return schedule

@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        engine = SHOScheduler(payload=payload)
        engine.load_master_data()
        engine.parse_routing()
        engine.extract_demand()
        return {"status": "success", "data": engine.generate_schedule()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
