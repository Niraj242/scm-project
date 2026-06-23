import os
import re
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import requests
from io import StringIO

# CHANGE 1: Use APIRouter instead of FastAPI app
router = APIRouter()

# --- ENVIRONMENT CONFIGURATION ---
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
AVAILABLE_BUFFER_URL = os.getenv("AVAILABLE_BUFFER_URL")

# --- DATA MODELS FOR OVERRIDES ---
class JobSequenceConstraint(BaseModel):
    before_job: str  
    after_job: str   

class MachineOverride(BaseModel):
    machine_id: str
    priority_type: Optional[str] = None
    start_window: Optional[str] = None  
    sequence_rules: Optional[List[JobSequenceConstraint]] = None

class SchedulePayload(BaseModel):
    target_date: str  
    temp_change_furnaces: List[str] = []  
    overrides: Optional[List[MachineOverride]] = []

# --- GOOGLE SHEET PARSING UTILITIES ---
def fetch_sheet_as_df(base_url: str, sheet_name: str) -> pd.DataFrame:
    if not base_url:
        raise HTTPException(status_code=500, detail="Google Sheet URL environment variable is unset. Please configure Render .env")
    
    # NEW FIX: Extract the exact File ID securely, regardless of how the URL ends
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match:
        raise HTTPException(status_code=400, detail=f"Invalid Google Sheet URL format: {base_url}")
    
    file_id = match.group(1)
    
    # Construct the perfect CSV download URL
    # Note: We must safely encode the sheet name in case there are spaces
    from urllib.parse import quote
    safe_sheet_name = quote(sheet_name.strip())
    csv_url = f"https://docs.google.com/spreadsheets/d/{file_id}/gviz/tq?tqx=out:csv&sheet={safe_sheet_name}"
    
    response = requests.get(csv_url)
    
    if response.status_code != 200 or "<html" in response.text[:20].lower():
        raise HTTPException(status_code=400, detail=f"Failed to read '{sheet_name}'. Google returned a login page or error. Ensure it's 'Anyone with the link can view'.")
    
    # Optional: Catch if Google sends an empty CSV (just columns, no data)
    try:
        df = pd.read_csv(StringIO(response.text))
        if df.empty and len(df.columns) == 0:
            raise ValueError("Empty dataframe")
        return df
    except Exception as e:
         raise HTTPException(status_code=400, detail=f"Could not parse CSV for sheet '{sheet_name}'. The sheet might be completely blank or improperly formatted. Error: {str(e)}")


def extract_family(raw_val) -> str:
    if pd.isna(raw_val):
        return ""
    val_str = str(raw_val).strip()
    mf_match = re.search(r'MF(\d+)', val_str)
    if mf_match:
        return mf_match.group(1)
    fv_match = re.search(r'^(\d+)', val_str)
    if fv_match:
        return fv_match.group(1)
    return val_str.split()[0]

# --- CORE SCHEDULING LOGIC ENGINE ---
class SHOScheduler:
    def __init__(self, target_date: str):
        self.target_date = target_date
        self.weights = {}
        self.furnace_flexibility = {}
        self.machine_rates = {}
        self.channel_routings = {}
        self.demands = {}

    def load_master_production_data(self):
        df_w = fetch_sheet_as_df(SHO_PRODUCTION_URL, "WEIGHTS")
        for _, row in df_w.dropna(subset=['types', 'ir/or']).iterrows():
            fam = str(row['types']).strip()
            part = str(row['ir/or']).strip() 
            self.weights[(fam, part)] = float(row['weight per ring'])

        df_f = fetch_sheet_as_df(SHO_PRODUCTION_URL, "Furnace Type Flexibility")
        for _, row in df_f.dropna(subset=['Comp Level 1']).iterrows():
            comp = str(row['Comp Level 1']).strip()
            self.furnace_flexibility[comp] = {
                "primary": str(row.get('Primary Furnace', '')).strip(),
                "alt1": str(row.get('Alternative 1', '')).strip(),
                "alt2": str(row.get('Alternative 2', '')).strip(),
            }

    def parse_routing_and_buffers(self):
        df_b = fetch_sheet_as_df(AVAILABLE_BUFFER_URL, self.target_date)
        
        channel_cols = [col for col in df_b.columns if "CH" in str(col) or "T0" in str(col) or "T1" in str(col)]
        
        for col in channel_cols:
            has_face = False
            has_od = False
            
            face_rows = df_b[df_b[df_b.columns[0]].astype(str).str.contains("Face Buffer", case=False, na=False)]
            od_rows = df_b[df_b[df_b.columns[0]].astype(str).str.contains("OD Buffer", case=False, na=False)]
            
            if not face_rows.empty and pd.notna(face_rows[col].values[0]) and str(face_rows[col].values[0]).strip() != "":
                has_face = True
            if not od_rows.empty and pd.notna(od_rows[col].values[0]) and str(od_rows[col].values[0]).strip() != "":
                has_od = True
                
            if has_face and has_od:
                self.channel_routings[col] = ["HT", "FACE", "OD", "CHANNEL"]
            elif has_face:
                self.channel_routings[col] = ["HT", "FACE", "CHANNEL"]
            elif has_od:
                self.channel_routings[col] = ["HT", "OD", "CHANNEL"]
            else:
                self.channel_routings[col] = ["HT", "CHANNEL"]

    def extract_zeroset_demands(self, channel_list: List[str], day_idx: int):
        for ch in channel_list:
            try:
                df_z = fetch_sheet_as_df(ZEROSET_URL, ch)
                for idx, row in df_z.iterrows():
                    raw_mf = row.get('MF') or row.get('mf')
                    if pd.notna(raw_mf):
                        family = extract_family(raw_mf)
                        d1 = float(row.get(str(day_idx), 0)) * 1000
                        d2 = float(row.get(str(day_idx + 1), 0)) * 1000
                        
                        self.demands[ch] = {
                            "family": family,
                            "qty": d1 + d2,
                            "is_split": d2 == 0
                        }
            except Exception:
                continue

    def generate_optimized_timeline(self, temp_furnaces: List[str], overrides: List[MachineOverride]) -> Dict:
        ht_schedule = []
        fod_schedule = []
        
        furnaces = {
            "AICHELIN_896": {"cap_kg": 350, "time": 0.0},
            "CASTLINK_1018": {"cap_kg": 250, "time": 0.0},
            "SIMPLICITY_1238": {"cap_kg": 180, "time": 0.0},
        }

        for ch, info in self.demands.items():
            fam = info["family"]
            qty = info["qty"]
            route = self.channel_routings.get(ch, ["HT", "CHANNEL"])
            
            f_rule = self.furnace_flexibility.get(fam, {"primary": "CASTLINK_1018"})
            chosen_f = f_rule["primary"] if f_rule["primary"] in furnaces else "CASTLINK_1018"
            
            weight = self.weights.get((fam, "100"), 0.25)
            total_mass = qty * weight
            processing_hours = total_mass / furnaces[chosen_f]["cap_kg"]
            
            changeover = 0.5 
            if chosen_f in temp_furnaces:
                changeover += 1.5 
                
            start_time = furnaces[chosen_f]["time"] + changeover
            end_time = start_time + processing_hours + 3.5 
            furnaces[chosen_f]["time"] = end_time
            
            ht_schedule.append({
                "channel": ch,
                "family": fam,
                "quantity": qty,
                "furnace": chosen_f,
                "start": round(start_time, 2),
                "end": round(end_time, 2)
            })

            current_grind_clock = end_time - 1.5 
            if "FACE" in route:
                fod_schedule.append({
                    "machine": "DDS (544)",
                    "process": "Face Grinding",
                    "channel": ch,
                    "family": fam,
                    "start": round(current_grind_clock, 2),
                    "end": round(current_grind_clock + (qty / 5000), 2)
                })
                current_grind_clock += (qty / 5000)
                
            if "OD" in route:
                fod_schedule.append({
                    "machine": "CL-46 (1125+661)",
                    "process": "OD Grinding",
                    "channel": ch,
                    "family": fam,
                    "start": round(current_grind_clock, 2),
                    "end": round(current_grind_clock + (qty / 4000), 2)
                })

        return {"heat_treatment": ht_schedule, "grinding": fod_schedule}

# CHANGE 2: Use @router instead of @app
@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        day_str = payload.target_date.split()[0]
        day_idx = int(day_str)
        
        engine = SHOScheduler(target_date=payload.target_date)
        engine.load_master_production_data()
        engine.parse_routing_and_buffers()
        
        channels = list(engine.channel_routings.keys())
        engine.extract_zeroset_demands(channels, day_idx)
        
        result = engine.generate_optimized_timeline(payload.temp_change_furnaces, payload.overrides)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
