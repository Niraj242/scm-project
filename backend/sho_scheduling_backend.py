import os
import re
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

# ---------------------------------------------------------
# ENVIRONMENT CONFIGURATION (Your Google Sheet Links)
# ---------------------------------------------------------
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")
MASTER_URL = os.getenv("MASTER_URL", "")

# In-memory storage for buffer data coming from the React frontend
SAVED_BUFFERS = {}

# ---------------------------------------------------------
# PYDANTIC MODELS (Matching your React Frontend exact payload)
# ---------------------------------------------------------
class BufferPayload(BaseModel):
    date: str
    dgbb: Dict[str, Any]
    trb: Dict[str, Any]

class ScheduleRequest(BaseModel):
    target_date: str

# ---------------------------------------------------------
# HELPER: FETCH GOOGLE SHEETS
# ---------------------------------------------------------
def fetch_sheet(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Fetches Google Sheets as CSV into a Pandas DataFrame."""
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

# ---------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------
@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferPayload):
    # Save the exact DGBB and TRB buffer matrix submitted from the UI
    SAVED_BUFFERS[payload.date] = {
        "dgbb": payload.dgbb,
        "trb": payload.trb
    }
    return {"status": "success", "message": "Buffer state saved"}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    target_date = payload.target_date
    day_num = str(int(target_date.split('-')[2])) # '2026-04-01' -> '1'
    
    # Get the buffer data saved for this date
    # If none saved, default to empty dicts so logic still runs
    day_buffer = SAVED_BUFFERS.get(target_date, {"dgbb": {}, "trb": {}})
    
    try:
        # 1. LOAD ALL MASTER DATA
        # ---------------------------------------------------------
        weights = {}
        df_w = fetch_sheet(MASTER_URL, "WEIGHTS")
        if not df_w.empty:
            for _, r in df_w.iterrows():
                try: weights[f"{str(r[0]).strip()}_{str(r[1]).strip()}"] = float(r[2])
                except: pass

        grind_rates = {"544": {}, "1125+661": {}}
        for machine_tab in ["544", "1125+661"]:
            df_m = fetch_sheet(SHO_PRODUCTION_URL, machine_tab)
            if not df_m.empty:
                for i in range(len(df_m)):
                    try:
                        part = str(df_m.iloc[i, 0]).strip()
                        pcode = str(df_m.iloc[i, 1]).strip()
                        grind_rates[machine_tab][f"{part}_{pcode}"] = float(df_m.iloc[i, 4])
                    except: pass

        furnace_map = {}
        df_f = fetch_sheet(MASTER_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for i in range(len(df_f)):
                try:
                    comp = str(df_f.iloc[i, 1]).strip()
                    primary = str(df_f.iloc[i, 2]).strip().upper()
                    if comp and primary: furnace_map[comp] = primary
                except: pass

        # 2. PARSE ZEROSET AND APPLY BUFFER LOGIC
        # ---------------------------------------------------------
        demands = []
        channels_to_check = ["CH01", "CH02", "CH03", "CH04", "CH05", "T01", "T02", "T03"] 
        
        for ch in channels_to_check:
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: continue
            
            # Find the PKWIP row for the specific day
            header_idx, col_idx = None, None
            for idx, row in df_z.iterrows():
                vals = [str(x).strip().upper().split('.')[0] for x in row.values if pd.notna(x)]
                if "PKWIP" in vals and day_num in vals:
                    header_idx = idx
                    if day_num in list(row.values): col_idx = list(row.values).index(day_num)
                    break
            
            if header_idx is not None and col_idx is not None:
                # Get the buffer data for this specific channel from the UI payload
                # E.g., check if it's a DGBB or TRB channel
                ch_buffer = day_buffer["dgbb"].get(ch) or day_buffer["trb"].get(ch) or {}
                
                # Buffer Thresholds (Days) - Adjust these based on your actual business rules
                face_buffer_days = float(ch_buffer.get("face_buf") or 0)
                od_buffer_days = float(ch_buffer.get("od_buf") or 0)
                ht_buffer_days = float(ch_buffer.get("ht_buf") or 0)

                for i in range(header_idx + 1, len(df_z)):
                    row_vals = [str(x).strip() for x in df_z.iloc[i].values]
                    if row_vals[0] and row_vals[0].startswith(("MF", "FV")):
                        part_name = row_vals[0].replace("MF", "").replace("FV", "")
                        qty_val = str(row_vals[col_idx]).replace(',', '')
                        
                        if qty_val and qty_val.lower() != 'nan':
                            qty = float(qty_val) * 1000  # 5 in sheet = 5000 rings
                            
                            if qty > 0:
                                for pcode, ptext in [("100", "OR"), ("120", "IR")]:
                                    
                                    # --- THE ROUTING LOGIC BASED ON BUFFER ---
                                    # If buffer is high enough, we skip that machine operation for the day.
                                    needs_face = face_buffer_days < 2.0  # e.g., if we have less than 2 days buffer, schedule Face
                                    needs_od = od_buffer_days < 2.0
                                    needs_ht = ht_buffer_days < 3.0
                                    
                                    route = []
                                    if needs_face: route.append("FACE")
                                    if needs_od: route.append("OD")
                                    if needs_ht: route.append("HT")

                                    if route:
                                        demands.append({
                                            "channel": ch,
                                            "part": part_name,
                                            "part_code": pcode,
                                            "part_text": ptext,
                                            "qty": qty,
                                            "route": route
                                        })

        # 3. SCHEDULE TO MACHINES & CALCULATE SHIFTS
        # ---------------------------------------------------------
        ht_caps = {"AICHELIN.(896)": 350, "CASTLINK FURNACE( 1018 )": 250}
        
        schedule = {
            "face": {"DDS (544)": []},
            "od": {"CL-46 Cell 2 ( 0945 + 0839 )": []},
            "ht": {"AICHELIN.(896)": [], "CASTLINK FURNACE( 1018 )": []}
        }
        
        # Track accumulated hours per machine
        time_state = {
            "face": {"DDS (544)": 0.0},
            "od": {"CL-46 Cell 2 ( 0945 + 0839 )": 0.0},
            "ht": {"AICHELIN.(896)": 0.0, "CASTLINK FURNACE( 1018 )": 0.0}
        }

        # Dynamic Shift Logic
        def get_shift(accumulated_hours):
            if accumulated_hours <= 8: return "1"
            if accumulated_hours <= 16: return "2"
            return "3"

        for job in demands:
            fam = job["part"]
            pcode = job["part_code"]
            qty = job["qty"]
            lbl = f"{fam}---{job['part_text']}"
            priority = "P1" if "CH" in job["channel"] else "P2"

            # -----------------
            # FACE GRINDING
            # -----------------
            if "FACE" in job["route"]:
                mach = "DDS (544)"
                rate = grind_rates["544"].get(f"{fam}_{pcode}", 1300) 
                hrs_needed = qty / rate
                
                # Check if machine has time left in the 24h day
                if time_state["face"][mach] + hrs_needed <= 24.0:
                    shift = get_shift(time_state["face"][mach])
                    schedule["face"][mach].append({
                        "job": lbl, 
                        "qty": str(int(qty/1300)) + " (BOX)", # Assuming ~1300 rings per box for visual
                        "shift": shift, 
                        "priority": priority
                    })
                    time_state["face"][mach] += hrs_needed

            # -----------------
            # OD GRINDING
            # -----------------
            if "OD" in job["route"]:
                mach = "CL-46 Cell 2 ( 0945 + 0839 )"
                rate = grind_rates["1125+661"].get(f"{fam}_{pcode}", 850)
                hrs_needed = qty / rate
                
                if time_state["od"][mach] + hrs_needed <= 24.0:
                    shift = get_shift(time_state["od"][mach])
                    schedule["od"][mach].append({
                        "job": lbl, 
                        "qty": str(int(qty/80)) + " (BOX)",
                        "shift": shift, 
                        "priority": priority
                    })
                    time_state["od"][mach] += hrs_needed

            # -----------------
            # HEAT TREATMENT
            # -----------------
            if "HT" in job["route"]:
                prefix = "OM" if pcode == "100" else "IM"
                mapped_furnace_raw = furnace_map.get(f"{prefix}{fam}", "AICHELIN")
                mach = "CASTLINK FURNACE( 1018 )" if "CASTLINK" in mapped_furnace_raw else "AICHELIN.(896)"
                
                wt_per_ring = weights.get(f"{fam}_{pcode}", 0.25)
                total_kg = qty * wt_per_ring
                hrs_needed = total_kg / ht_caps[mach]
                
                if time_state["ht"][mach] + hrs_needed <= 24.0:
                    schedule["ht"][mach].append({
                        "job": lbl,
                        "qty": f"{total_kg:.1f} kg", # Passing formatted weight to UI
                        "channel": job["channel"]
                    })
                    time_state["ht"][mach] += hrs_needed

        # 4. PAD OUTPUT FOR UI CONSISTENCY
        # Ensure there are at least 5 rows so the UI table looks solid and matches your screenshot
        for cat in schedule:
            for m in schedule[cat]:
                while len(schedule[cat][m]) < 5:
                    if cat == "ht":
                        schedule[cat][m].append({"job": "", "qty": "", "channel": ""})
                    else:
                        schedule[cat][m].append({"job": "", "qty": "", "shift": "", "priority": ""})

        return {"status": "success", "data": schedule}

    except Exception as e:
        return {"status": "error", "message": f"Server Logic Error: {str(e)}"}
