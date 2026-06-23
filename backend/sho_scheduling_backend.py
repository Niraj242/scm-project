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

router = APIRouter()

# --- ENV VARIABLES ---
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
AVAILABLE_BUFFER_URL = os.getenv("AVAILABLE_BUFFER_URL")

class MachineOverride(BaseModel):
    machine_id: str
    priority_type: Optional[str] = None

class SchedulePayload(BaseModel):
    target_date: str
    temp_change_furnaces: List[str] = []
    overrides: List[MachineOverride] = []

def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Robustly fetches a Google Sheet tab as a CSV."""
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
            # Clean column names
            df.columns = [str(c).strip() for c in df.columns]
            return df
    except Exception as e:
        print(f"Fetch Error for {sheet_name}: {e}")
    return pd.DataFrame()

def extract_family(raw_val) -> str:
    """Extracts base family from 'MF32211' or '32211 J2/Q'"""
    if pd.isna(raw_val): return ""
    val_str = str(raw_val).strip()
    match = re.search(r'(?:MF)?(\d+)', val_str)
    return match.group(1) if match else val_str.split()[0]

class SHOScheduler:
    def __init__(self, payload: SchedulePayload):
        self.payload = payload
        self.target_date = payload.target_date
        self.debug_logs = []
        
        self.weights = {}
        self.furnace_flex = {}
        self.channel_routings = {}
        self.demands = []
        
        # Exact Machine Rate Mapping (Tab names to check based on your files)
        self.machine_rates = {}
        
        self.ht_machines = [
            "AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "ROLLER FURNACE ( 148 )", 
            "SIMPLICITY FURNACE(1238)", "BIRLEC FURNACE ( 1158 )", "SHOEI FURNACE ( 1062 )", 
            "AICHELIN UNITHERM ( 2033 )"
        ]
        self.face_machines = ["DDS (544)", "Gardner ( 1016 + USA 1996 )", "DDS Cell ( 709 + 1186 )", "Gardner (1601)"]
        self.od_machines = ["CL-46 Cell 2 ( 0945 + 0839 )", "CL-46 Cell 1 ( 0661 + 1125 )", "CL-46 Cell 3 ( 1600 + 1903 )", "CL-46 Cell 4 ( 170 + 1904 )", "AMHD OD ( 2021 )"]

        self.machine_state = {
            "face": {m: {"last_fam": None, "hours": 0.0} for m in self.face_machines},
            "od": {m: {"last_fam": None, "hours": 0.0} for m in self.od_machines},
            "ht": {m: {"last_fam": None, "hours": 0.0} for m in self.ht_machines}
        }

    def log(self, msg: str):
        print(msg)
        self.debug_logs.append(msg)

    def load_master_data(self):
        self.log("1. Loading Master Weights & Flexibility...")
        df_w = fetch_sheet(SHO_PRODUCTION_URL, "WEIGHTS")
        if not df_w.empty:
            for _, row in df_w.dropna(subset=['types', 'ir/or']).iterrows():
                fam = extract_family(str(row['types']))
                part = "OR" if str(row['ir/or']).strip() == "100" else "IR"
                self.weights[(fam, part)] = float(row.get('weight per ring', 0.2))
        else:
            self.log("WARNING: WEIGHTS sheet could not be loaded or is empty.")

        df_f = fetch_sheet(SHO_PRODUCTION_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for _, row in df_f.dropna(subset=['Comp Level 1']).iterrows():
                comp = extract_family(str(row['Comp Level 1']))
                self.furnace_flex[comp] = str(row.get('Primary Furnace', '')).strip().upper()

        self.log("2. Loading Machine Production Rates...")
        # Load machine specific rates like 544 and 1125+661
        machine_tabs_to_check = ["544", "1125+661"] 
        for tab in machine_tabs_to_check:
            df_m = fetch_sheet(SHO_PRODUCTION_URL, tab)
            if df_m.empty:
                self.log(f"WARNING: Machine sheet '{tab}' not found.")
                continue
            
            # Find header row dynamically
            header_idx = None
            for idx, row in df_m.iterrows():
                if 'STD/HR' in str(row.values) and 'TYPE' in str(row.values).upper():
                    header_idx = idx
                    break
            
            if header_idx is not None:
                df_m.columns = [str(c).strip().upper() for c in df_m.iloc[header_idx]]
                df_m = df_m.drop(index=list(range(header_idx + 1)))
                for _, row in df_m.dropna(subset=['TYPE']).iterrows():
                    fam = extract_family(row['TYPE'])
                    part = "OR" if str(row.get('PART', '')).strip() == "100" else "IR"
                    try:
                        rate = float(str(row['STD/HR']).replace(',', ''))
                        self.machine_rates[(tab, fam, part)] = rate
                    except:
                        pass
                self.log(f"Loaded {len(df_m)} rates from {tab}.")

    def parse_routing(self):
        self.log(f"3. Loading Buffer Sheet for Date: {self.target_date}")
        df_b = fetch_sheet(AVAILABLE_BUFFER_URL, self.target_date)
        if df_b.empty:
            self.log(f"WARNING: Buffer sheet named '{self.target_date}' not found. Defaulting routes.")
            # Default routes to continue testing if buffer sheet is missing
            self.channel_routings = {"5": ["HT", "FACE", "OD"], "T4": ["HT", "FACE", "OD"]}
            return
        
        channel_cols = [col for col in df_b.columns if "CH" in str(col).upper() or "T" in str(col).upper() or col.isdigit()]
        face_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("Face Buffer", case=False, na=False)].index
        od_idx = df_b[df_b.iloc[:, 0].astype(str).str.contains("OD Buffer", case=False, na=False)].index
        
        for col in channel_cols:
            has_face = len(face_idx) > 0 and pd.notna(df_b.at[face_idx[0], col])
            has_od = len(od_idx) > 0 and pd.notna(df_b.at[od_idx[0], col])
            if has_face and has_od: self.channel_routings[col] = ["HT", "FACE", "OD"]
            elif has_face: self.channel_routings[col] = ["HT", "FACE"]
            elif has_od: self.channel_routings[col] = ["HT", "OD"]
            else: self.channel_routings[col] = ["HT"]
        self.log(f"Identified {len(self.channel_routings)} active channels from buffer.")

    def extract_demand(self):
        self.log("4. Extracting Zeroset Demands...")
        # Parse '01 APR 2026' into '1'
        try:
            day_num = str(int(self.target_date.split()[0]))
            next_day_num = str(int(day_num) + 1)
        except:
            day_num = "1"
            next_day_num = "2"
        
        self.log(f"Looking for columns '{day_num}' and '{next_day_num}' in Zeroset files.")

        # If channel routings are empty, force check sample sheets 5 and T4
        channels_to_check = list(self.channel_routings.keys()) if self.channel_routings else ["5", "T4"]

        for ch in channels_to_check:
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: 
                self.log(f"Skipping Zeroset '{ch}': Not found.")
                continue
            
            # Locate true header
            header_idx = None
            for idx, row in df_z.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                if ("MF" in row_str or "FV" in row_str) and (day_num in row_str):
                    header_idx = idx
                    break
            
            if header_idx is None:
                self.log(f"WARNING: Could not find header with MF/FV and '{day_num}' in '{ch}'.")
                continue

            df_z.columns = [str(c).strip() for c in df_z.iloc[header_idx]]
            df_z = df_z.drop(index=list(range(header_idx + 1)))

            found_count = 0
            for _, row in df_z.iterrows():
                raw_mf = row.get('MF') or row.get('FV')
                if pd.notna(raw_mf) and str(raw_mf).strip() != "":
                    fam = extract_family(raw_mf)
                    try:
                        d1 = float(str(row.get(day_num, 0)).replace(',', '')) * 1000
                        d2 = float(str(row.get(next_day_num, 0)).replace(',', '')) * 1000
                        tot = d1 + d2
                        if tot > 0:
                            part = "OR" if "OR" in str(row.get('PART', '')).upper() else "IR"
                            self.demands.append({
                                "channel": ch, "family": fam, "part": part, "qty": tot, 
                                "route": self.channel_routings.get(ch, ["HT", "FACE", "OD"])
                            })
                            found_count += 1
                    except Exception as e:
                        continue
            self.log(f"Extracted {found_count} jobs from Zeroset '{ch}'.")

        self.demands.sort(key=lambda x: x["family"])
        self.log(f"Total jobs ready for scheduling: {len(self.demands)}")

    def get_machine_rate(self, machine_name: str, fam: str, part: str) -> float:
        """Retrieves exact rate from Machine excel, or falls back to standard averages"""
        if "544" in machine_name:
            return self.machine_rates.get(("544", fam, part), 1200.0)
        if "1125+661" in machine_name:
            return self.machine_rates.get(("1125+661", fam, part), 900.0)
        return 1000.0 # Default fallback

    def assign_grinding(self, group: str, fam: str, part: str, qty: float, is_trb: bool):
        machines = self.face_machines if group == "face" else self.od_machines
        eligible = [m for m in machines if "1016" in m or "Cell 1" in m] if is_trb else machines
        best_m = eligible[0]
        min_end = float('inf')
        best_rate = 1000.0

        for m in eligible:
            st = self.machine_state[group][m]
            rate = self.get_machine_rate(m, fam, part)
            setup = 2.0 if st["last_fam"] and st["last_fam"] != fam else 0.0
            proj = st["hours"] + setup + (qty / rate)
            if proj < min_end:
                min_end = proj
                best_m = m
                best_rate = rate

        st = self.machine_state[group][best_m]
        st["hours"] += (2.0 if st["last_fam"] and st["last_fam"] != fam else 0.0)
        shift = math.floor(st["hours"] / 8) + 1
        st["hours"] += (qty / best_rate)
        st["last_fam"] = fam
        return best_m, f"Shift {min(int(shift), 3)}"

    def generate_schedule(self) -> Dict[str, Any]:
        schedule = {"face": {m: [] for m in self.face_machines}, "od": {m: [] for m in self.od_machines}, "ht": {m: [] for m in self.ht_machines}}
        
        for d in self.demands:
            fam, part, qty, ch, route = d["family"], d["part"], d["qty"], d["channel"], d["route"]
            job_name = f"{fam} ({part})"
            is_trb = "T" in ch.upper()

            # 1. HEAT TREATMENT
            furnace = "CASTLINK FURNACE( 1018 )"
            for hm in self.ht_machines:
                if self.furnace_flex.get(fam, "NONE") in hm.upper():
                    furnace = hm; break

            f_st = self.machine_state["ht"][furnace]
            quench_pen = 1.5 if furnace in self.payload.temp_change_furnaces else 0.0
            setup_pen = 0.5 if f_st["last_fam"] and f_st["last_fam"] != fam else 0.0
            
            # Kg/Hr to Rings/Hr
            cap_kg = 250.0 
            if "896" in furnace or "1062" in furnace: cap_kg = 350.0
            elif "1238" in furnace or "1158" in furnace: cap_kg = 170.0
            
            ring_wt = self.weights.get((fam, part), 0.25)
            rings_hr = cap_kg / ring_wt
            
            start_time = f_st["hours"] + setup_pen + quench_pen
            end_time = start_time + (qty / rings_hr) + 3.5 
            f_st["hours"] = end_time
            f_st["last_fam"] = fam

            schedule["ht"][furnace].append({
                "job": job_name, "qty": int(qty), "channel": ch, "start": round(start_time, 1), "end": round(end_time, 1)
            })

            # 2. FACE & OD
            if "FACE" in route:
                m, s = self.assign_grinding("face", fam, part, qty, is_trb)
                schedule["face"][m].append({"job": job_name, "shift": s, "priority": "P1"})
            
            if "OD" in route:
                m, s = self.assign_grinding("od", fam, part, qty, is_trb)
                schedule["od"][m].append({"job": job_name, "shift": s, "priority": "P1"})

        return {"matrices": schedule, "logs": self.debug_logs}

@router.post("/api/v1/generate-schedule")
def process_production_schedule(payload: SchedulePayload):
    try:
        engine = SHOScheduler(payload=payload)
        engine.load_master_data()
        engine.parse_routing()
        engine.extract_demand()
        
        result = engine.generate_schedule()
        return {"status": "success", "data": result["matrices"], "logs": result["logs"]}
    except Exception as e:
        error_trace = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}\n\nTraceback:\n{error_trace}")
