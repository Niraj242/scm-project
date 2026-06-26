import os
import re
import math
import traceback
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote

router = APIRouter()

SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL")
ZEROSET_URL = os.getenv("ZEROSET_URL")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL")

# --- MOCK DATABASE FOR SAVED BUFFERS ---
# In production, this connects to your Neon PostgreSQL DB
SAVED_BUFFERS = {} 

class BufferData(BaseModel):
    date: str
    grinding_unit: str  # 'Boxes', 'Days', 'Rings'
    ht_unit: str        # 'Boxes', 'Days', 'Rings'
    entries: List[Dict[str, Any]]

class ScheduleRequest(BaseModel):
    target_date: str

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

# --- ENDPOINTS ---

@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferData):
    """Saves the Daily Buffer inputted from the frontend UI."""
    # Prevent double entries by overwriting the date key
    SAVED_BUFFERS[payload.date] = payload.dict()
    return {"status": "success", "message": f"Buffer for {payload.date} saved successfully."}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    try:
        target_date = payload.target_date
        day_num = str(int(target_date.split('-')[2]))
        
        buffer_state = SAVED_BUFFERS.get(target_date)
        if not buffer_state:
            raise Exception(f"No Buffer data saved for {target_date}. Please fill and save the Buffer UI first.")

        # 1. LOAD MASTER DATA
        weights = {}
        rings_per_box = {}
        machine_rates = {}
        
        # Load Weights
        df_w = fetch_sheet(SHO_PRODUCTION_URL, "WEIGHTS")
        for _, r in df_w.iterrows():
            try: weights[f"{str(r[0]).strip().replace('MF', '')}_{str(r[1]).strip()}"] = float(r[2])
            except: pass
            
        # Load Rings Per Box
        df_box = fetch_sheet(BOX_RING_DATA_URL, "RING PER BOX.")
        for _, r in df_box.iterrows():
            try:
                fam = str(r[0]).strip().replace("MF", "")
                pcode = "100" if "O" in str(r[1]).upper() else "120"
                rings_per_box[f"{fam}_{pcode}"] = float(r[3])
            except: pass

        # Load Machine Rates (Grinding)
        for tab in ["544", "1125+661"]:
            df = fetch_sheet(SHO_PRODUCTION_URL, tab)
            m_name = "DDS (544)" if tab == "544" else "CL-46 Cell 1 ( 0661 + 1125 )"
            machine_rates[m_name] = {}
            for i in range(len(df)):
                try: machine_rates[m_name][f"{str(df.iloc[i,0]).strip()}_{str(df.iloc[i,1]).strip()}"] = float(df.iloc[i,4])
                except: pass

        # 2. EXTRACT ZEROSET DEMAND & APPLY BUFFER
        demands = []
        for ch in ["5", "T4", "CH01"]:
            df_z = fetch_sheet(ZEROSET_URL, ch)
            if df_z.empty: continue
            
            header_idx, col_idx = None, None
            for idx, row in df_z.iterrows():
                vals = [str(x).strip().upper().split('.')[0] for x in row.values if pd.notna(x)]
                if "PKWIP" in vals and day_num in vals:
                    header_idx, col_idx = idx, vals.index(day_num)
                    break
            
            if not header_idx: continue

            for i in range(header_idx + 1, len(df_z)):
                row_vals = [str(x).strip() for x in df_z.iloc[i].values]
                if m := re.search(r'(?:MF|FV)?(\d{4,5})', row_vals[0]):
                    fam = m.group(1)
                    try:
                        qty = float(row_vals[col_idx].replace(',','')) * 1000 # 5 means 5000
                        if qty > 0:
                            for p_code, p_name in [("100", "OR"), ("120", "IR")]:
                                # Check UI Buffer for Skipping Logic
                                route = ["HT", "FACE", "OD"]
                                # If buffer for this channel/part was completely blank in UI, skip Face/OD
                                channel_buffer = [b for b in buffer_state["entries"] if b["channel"] == ch and b["part"] == p_name]
                                if channel_buffer:
                                    cb = channel_buffer[0]
                                    if not cb.get("face_val") and not cb.get("od_val"):
                                        route = ["HT"] # Route directly to channel
                                
                                demands.append({
                                    "family": fam, "part": p_name, "part_code": p_code,
                                    "req_qty": qty, "route": route
                                })
                    except: pass

        # 3. GENERATE SIMPLE SCHEDULE
        face_macs = ["DDS (544)", "Gardner ( 1016 + USA 1996 )"]
        od_macs = ["CL-46 Cell 1 ( 0661 + 1125 )", "CL-46 Cell 2 ( 0945 + 0839 )"]
        ht_macs = ["AICHELIN.(896)", "CASTLINK FURNACE( 1018 )", "SHOEI FURNACE ( 1062 )"]
        ht_caps = {"AICHELIN.(896)": 350, "CASTLINK FURNACE( 1018 )": 250, "SHOEI FURNACE ( 1062 )": 350}
        
        state = {"face": {m: 0.0 for m in face_macs}, "od": {m: 0.0 for m in od_macs}, "ht": {m: 0.0 for m in ht_macs}}
        sched = {"face": {m: [] for m in face_macs}, "od": {m: [] for m in od_macs}, "ht": {m: [] for m in ht_macs}}

        for job in demands:
            fam, pcode, qty = job["family"], job["part_code"], job["req_qty"]
            lbl = f"{fam} ({job['part']})"

            # HT Assignment
            if "HT" in job["route"]:
                best_ht = min(ht_macs, key=lambda x: state["ht"][x])
                wt = weights.get(f"{fam}_{pcode}", 0.25)
                rate = ht_caps[best_ht] / wt if wt > 0 else 1000
                start = state["ht"][best_ht] + 0.5 # 30m reset
                end = min(start + (qty / rate) + 3.5, 24.0) # 3.5h cycle
                state["ht"][best_ht] = end
                sched["ht"][best_ht].append({"job": lbl, "qty": int(qty), "start": round(start,1), "end": round(end,1)})

            # Face Grinding
            if "FACE" in job["route"]:
                best_f = min(face_macs, key=lambda x: state["face"][x])
                rate = machine_rates.get(best_f, {}).get(f"{fam}_{pcode}", 1200)
                state["face"][best_f] = min(state["face"][best_f] + (qty / rate), 24.0)
                sched["face"][best_f].append({"job": lbl, "qty": int(qty)})

            # OD Grinding
            if "OD" in job["route"]:
                best_o = min(od_macs, key=lambda x: state["od"][x])
                rate = machine_rates.get(best_o, {}).get(f"{fam}_{pcode}", 850)
                state["od"][best_o] = min(state["od"][best_o] + (qty / rate), 24.0)
                sched["od"][best_o].append({"job": lbl, "qty": int(qty)})

        return {"status": "success", "data": sched}
    except Exception as e:
        return {"status": "error", "message": str(e)}
