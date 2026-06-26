import os
import re
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

router = APIRouter()

# Environment variables for your Google Sheets CSV export links
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")
MASTER_URL = os.getenv("MASTER_URL", "") # For Furnace Flexibility & Weights

# Store saved buffer/downtime states
SAVED_BUFFERS = {}

class ScheduleRequest(BaseModel):
    target_date: str

class BufferPayload(BaseModel):
    grind_unit: str
    ht_unit: str
    data: List[Dict[str, Any]]

def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Helper to fetch Google Sheets as CSV into a Pandas DataFrame."""
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    try:
        res = requests.get(csv_url, timeout=15)
        if res.status_code == 200 and "<html" not in res.text[:20].lower():
            return pd.read_csv(StringIO(res.text), header=None, dtype=str)
    except Exception as e:
        print(f"Error fetching {sheet_name}: {e}")
    return pd.DataFrame()

@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferPayload):
    # Save the buffer/downtime grid data for routing logic later
    # Extract the target date from the first row to key the dictionary
    if payload.data:
        date_key = payload.data[0].get('date')
        if date_key:
            SAVED_BUFFERS[date_key] = payload.dict()
    return {"status": "success", "message": "Buffer saved successfully"}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        target_date = payload.target_date
        day_num = str(int(target_date.split('-')[2])) # Extract '1' from '2026-04-01'

        # 1. LOAD MASTER DATA DICTIONARIES
        # Weights (kg per ring)
        weights = {}
        df_w = fetch_sheet(MASTER_URL, "WEIGHTS")
        if not df_w.empty:
            for _, r in df_w.iterrows():
                try: weights[f"{str(r[0]).strip()}_{str(r[1]).strip()}"] = float(r[2])
                except: pass

        # Rings per Box Conversion
        rings_per_box = {}
        df_box = fetch_sheet(BOX_RING_DATA_URL, "RING PER BOX.")
        if not df_box.empty:
            for _, r in df_box.iterrows():
                try:
                    fam = str(r[0]).strip().replace("MF", "")
                    pcode = "100" if "O" in str(r[1]).upper() else "120"
                    rings_per_box[f"{fam}_{pcode}"] = float(r[3])
                except: pass

        # Machine Rates (STD/HR)
        grind_rates = {"544": {}, "1125+661": {}}
        for machine_tab in ["544", "1125+661"]:
            df_m = fetch_sheet(SHO_PRODUCTION_URL, machine_tab)
            if not df_m.empty:
                for i in range(len(df_m)):
                    try:
                        part_type = str(df_m.iloc[i, 0]).strip()
                        part_code = str(df_m.iloc[i, 1]).strip()
                        std_hr = float(df_m.iloc[i, 4])
                        grind_rates[machine_tab][f"{part_type}_{part_code}"] = std_hr
                    except: pass

        # Furnace Flexibility
        furnace_map = {}
        df_f = fetch_sheet(MASTER_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for i in range(len(df_f)):
                try:
                    comp = str(df_f.iloc[i, 1]).strip() # e.g., OM02820
                    primary = str(df_f.iloc[i, 2]).strip().upper()
                    if comp and primary:
                        furnace_map[comp] = primary
                except: pass

        # 2. EXTRACT ZEROSET DEMAND
        demands = []
        for ch in ["5", "T4", "CH01", "CH02", "CH03"]: # Add all your channels here
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: continue
            
            # Find the PKWIP row and the column for the specific day
            header_idx, col_idx = None, None
            for idx, row in df_z.iterrows():
                vals = [str(x).strip().upper().split('.')[0] for x in row.values if pd.notna(x)]
                if "PKWIP" in vals and day_num in vals:
                    header_idx = idx
                    col_idx = list(row.values).index(day_num) if day_num in list(row.values) else None
                    if not col_idx: # Fallback to fuzzy match
                        for j, val in enumerate(row.values):
                            if str(val).strip().split('.')[0] == day_num:
                                col_idx = j
                                break
                    break
            
            if header_idx is not None and col_idx is not None:
                for i in range(header_idx + 1, len(df_z)):
                    row_vals = [str(x).strip() for x in df_z.iloc[i].values]
                    if row_vals[0] and row_vals[0].startswith(("MF", "FV")):
                        part_name = row_vals[0].replace("MF", "").replace("FV", "")
                        try:
                            # 5 in sheet means 5000 rings
                            qty_val = str(row_vals[col_idx]).replace(',', '')
                            if qty_val and qty_val.lower() != 'nan':
                                qty = float(qty_val) * 1000 
                                if qty > 0:
                                    # Create jobs for both OR (100) and IR (120)
                                    for pcode, ptext in [("100", "OR"), ("120", "IR")]:
                                        # BUFFER SKIPPING LOGIC: 
                                        # Check if this channel has downtime logged in our saved UI state
                                        route = ["HT", "FACE", "OD"]
                                        if SAVED_BUFFERS.get(target_date):
                                            # Example: If channel has downtime logged, we might skip Face/OD
                                            # and build HT buffer only. Adjust condition based on your exact rule.
                                            day_data = next((d for d in SAVED_BUFFERS[target_date]['data'] if d['date'] == target_date), None)
                                            if day_data:
                                                ch_downtime = day_data.get('dgbb', {}).get(ch, "") or day_data.get('trb', {}).get(ch, "")
                                                if ch_downtime: 
                                                    route = ["HT"] # Skip grinding, just HT

                                        demands.append({
                                            "channel": ch,
                                            "part": part_name,
                                            "part_code": pcode,
                                            "part_text": ptext,
                                            "qty": qty,
                                            "route": route
                                        })
                        except Exception as e:
                            pass

        # 3. SCHEDULE TO MACHINES
        # Define capacities and machine lists matching your frontend
        ht_caps = {"AICHELIN.(896)": 350, "CASTLINK FURNACE( 1018 )": 250}
        
        schedule = {
            "face": {"DDS (544)": []},
            "od": {"CL -46 Cell 2 ( 0945 + 0839 )": []},
            "ht": {"AICHELIN.(896)": [], "CASTLINK FURNACE( 1018 )": []}
        }
        
        # Track available time (0 to 24 hours)
        time_state = {
            "face": {"DDS (544)": 0.0},
            "od": {"CL -46 Cell 2 ( 0945 + 0839 )": 0.0},
            "ht": {"AICHELIN.(896)": 0.0, "CASTLINK FURNACE( 1018 )": 0.0}
        }

        # Shift allocator logic
        def get_shift(hour):
            if hour < 8: return "1"
            if hour < 16: return "2"
            return "3"

        for job in demands:
            fam = job["part"]
            pcode = job["part_code"]
            qty = job["qty"]
            lbl = f"{fam}---{job['part_text']}"
            priority = "P1" if "CH" in job["channel"] else "P2" # Basic priority rule

            # ROUTE: FACE GRINDING
            if "FACE" in job["route"]:
                mach = "DDS (544)"
                rate = grind_rates["544"].get(f"{fam}_{pcode}", 1300) # Default to 1300 rings/hr if not found
                hrs_needed = qty / rate
                if time_state["face"][mach] + hrs_needed <= 24.0:
                    shift = get_shift(time_state["face"][mach])
                    schedule["face"][mach].append({
                        "job": lbl, 
                        "qty": int(qty), 
                        "shift": shift, 
                        "priority": priority
                    })
                    time_state["face"][mach] += hrs_needed

            # ROUTE: OD GRINDING
            if "OD" in job["route"]:
                mach = "CL -46 Cell 2 ( 0945 + 0839 )"
                rate = grind_rates["1125+661"].get(f"{fam}_{pcode}", 850)
                hrs_needed = qty / rate
                if time_state["od"][mach] + hrs_needed <= 24.0:
                    shift = get_shift(time_state["od"][mach])
                    schedule["od"][mach].append({
                        "job": lbl, 
                        "qty": int(qty), 
                        "shift": shift, 
                        "priority": priority
                    })
                    time_state["od"][mach] += hrs_needed

            # ROUTE: HEAT TREATMENT
            if "HT" in job["route"]:
                # Map furnace based on flexibility matrix. "OM" for 100, "IM" for 120.
                prefix = "OM" if pcode == "100" else "IM"
                mapped_furnace_raw = furnace_map.get(f"{prefix}{fam}", "AICHELIN")
                
                mach = "AICHELIN.(896)"
                if "CASTLINK" in mapped_furnace_raw:
                    mach = "CASTLINK FURNACE( 1018 )"
                
                wt_per_ring = weights.get(f"{fam}_{pcode}", 0.25)
                total_kg = qty * wt_per_ring
                hrs_needed = total_kg / ht_caps[mach]
                
                if time_state["ht"][mach] + hrs_needed <= 24.0:
                    schedule["ht"][mach].append({
                        "job": lbl,
                        "qty": int(qty),
                        "channel": job["channel"]
                    })
                    time_state["ht"][mach] += hrs_needed

        # Pad arrays so the Excel view always has at least 5 rows (looks clean in UI)
        for cat in schedule:
            for m in schedule[cat]:
                while len(schedule[cat][m]) < 5:
                    if cat == "ht":
                        schedule[cat][m].append({"job": "", "qty": "", "channel": ""})
                    else:
                        schedule[cat][m].append({"job": "", "qty": "", "shift": "", "priority": ""})

        return {"status": "success", "data": schedule}

    except Exception as e:
        return {"status": "error", "message": str(e)}
