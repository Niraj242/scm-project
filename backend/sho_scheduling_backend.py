import os
import re
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")
MASTER_URL = os.getenv("MASTER_URL", "")

# Central memory state tracking the buffer configs submitted per date
SAVED_BUFFERS = {}

class BufferPayload(BaseModel):
    date: str
    dgbb_unit: str
    trb_unit: str
    dgbb: Dict[str, Any]
    trb: Dict[str, Any]

class ScheduleRequest(BaseModel):
    target_date: str

def fetch_sheet_raw(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Downloads Google Sheets directly into clean positional row matrices."""
    if not base_url: 
        return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: 
        return pd.DataFrame()
    csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    try:
        res = requests.get(csv_url, timeout=15)
        if res.status_code == 200 and "<html" not in res.text[:20].lower():
            return pd.read_csv(StringIO(res.text), header=None, dtype=str)
    except Exception as e:
        print(f"Error reading tab {sheet_name}: {str(e)}")
    return pd.DataFrame()

@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferPayload):
    # Overwrites or establishes state for the targeted date index
    SAVED_BUFFERS[payload.date] = {
        "dgbb_unit": payload.dgbb_unit,
        "trb_unit": payload.trb_unit,
        "dgbb": payload.dgbb,
        "trb": payload.trb
    }
    return {"status": "success", "message": f"Persisted specifications for {payload.date}"}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    target_date = payload.target_date
    # '2026-04-01' -> extract day integer component '1'
    try:
        day_num = str(int(target_date.split('-')[2]))
    except:
        return {"status": "error", "message": "Malformed Date Stamp format."}

    user_matrix = SAVED_BUFFERS.get(target_date, {"dgbb_unit": "Days", "trb_unit": "Days", "dgbb": {}, "trb": {}})

    try:
        # 1. POSITIONAL SHEET PARSING TO AVOID NON-UNIQUE KEY ERROR
        # ---------------------------------------------------------------------
        weights = {}
        df_w = fetch_sheet_raw(MASTER_URL, "WEIGHTS")
        if not df_w.empty:
            for idx in range(len(df_w)):
                try:
                    pname = str(df_w.iloc[idx, 0]).strip()
                    pcode = str(df_w.iloc[idx, 1]).strip()
                    w_val = float(df_w.iloc[idx, 2])
                    weights[f"{pname}_{pcode}"] = w_val
                except: pass

        rings_per_box = {}
        df_box = fetch_sheet_raw(BOX_RING_DATA_URL, "RING PER BOX.")
        if not df_box.empty:
            for idx in range(len(df_box)):
                try:
                    fam = str(df_box.iloc[idx, 0]).strip().replace("MF", "")
                    pcode = "100" if "O" in str(df_box.iloc[idx, 1]).upper() else "120"
                    rings_per_box[f"{fam}_{pcode}"] = float(df_box.iloc[idx, 3])
                except: pass

        grind_rates = {"544": {}, "1125+661": {}}
        for tab, m_id in [("544", "544"), ("1125+661", "1125+661")]:
            df_m = fetch_sheet_raw(SHO_PRODUCTION_URL, tab)
            if not df_m.empty:
                for idx in range(len(df_m)):
                    try:
                        pname = str(df_m.iloc[idx, 0]).strip()
                        pcode = str(df_m.iloc[idx, 1]).strip()
                        rate = float(df_m.iloc[idx, 4])
                        grind_rates[m_id][f"{pname}_{pcode}"] = rate
                    except: pass

        furnace_map = {}
        df_f = fetch_sheet_raw(MASTER_URL, "Furnace Type Flexibility")
        if not df_f.empty:
            for idx in range(len(df_f)):
                try:
                    comp = str(df_f.iloc[idx, 1]).strip()
                    furnace = str(df_f.iloc[idx, 2]).strip().upper()
                    if comp: furnace_map[comp] = furnace
                except: pass

        # 2. RUN EXTRACTION ACROSS CHANNELS WITH SCALE CONVERSIONS
        # ---------------------------------------------------------------------
        demands = []
        all_channels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5',
                        'T01','T02','T03','T04','T05','T06','T07','T08','T09','T10']

        for ch in all_channels:
            df_z = fetch_sheet_raw(ZEROSET_URL, ch)
            if df_z.empty: continue

            # Track down row containing PKWIP header string positionally
            h_row, c_idx = None, None
            for idx in range(min(20, len(df_z))):
                row_list = [str(x).strip().upper().split('.')[0] for x in df_z.iloc[idx].values if pd.notna(x)]
                if "PKWIP" in row_list and day_num in row_list:
                    h_row = idx
                    # Direct match coordinate tracking
                    for col_pos in range(len(df_z.iloc[idx])):
                        if str(df_z.iloc[idx, col_pos]).strip().split('.')[0] == day_num:
                            c_idx = col_pos
                            break
                    break

            if h_row is not None and c_idx is not None:
                # Map configuration input references
                ch_grid = user_matrix["dgbb"].get(ch) or user_matrix["trb"].get(ch) or {}
                unit_type = user_matrix["dgbb_unit"] if ch.startswith("CH") or "SABB" in ch else user_matrix["trb_unit"]

                for r_pos in range(h_row + 1, len(df_z)):
                    p_cell = str(df_z.iloc[r_pos, 0]).strip()
                    if p_cell and p_cell.startswith(("MF", "FV")):
                        part_family = p_cell.replace("MF", "").replace("FV", "")
                        
                        try:
                            val_raw = str(df_z.iloc[r_pos, c_idx]).replace(',', '')
                            if val_raw and val_raw.lower() != 'nan':
                                # Core standard scaling conversion rule (5 values = 5000 units)
                                net_requirement = float(val_raw) * 1000
                                if net_requirement <= 0: continue

                                for pc, pt in [("100", "OR"), ("120", "IR")]:
                                    # Establish conversion standard divisors
                                    box_capacity = rings_per_box.get(f"{part_family}_{pc}", 1000)
                                    
                                    # 3. CONVERT USER INPUTS DYNAMICALLY TO STANDARD SCALE (DAYS)
                                    # ---------------------------------------------------------
                                    raw_face_buf = float(ch_grid.get("face_buf") or 0)
                                    raw_od_buf = float(ch_grid.get("od_buf") or 0)

                                    face_days = raw_face_buf
                                    od_days = raw_od_buf

                                    if unit_type == "No. of Rings":
                                        face_days = raw_face_buf / net_requirement if net_requirement > 0 else 5.0
                                        od_days = raw_od_buf / net_requirement if net_requirement > 0 else 5.0
                                    elif unit_type == "Boxes":
                                        face_days = (raw_face_buf * box_capacity) / net_requirement if net_requirement > 0 else 5.0
                                        od_days = (raw_od_buf * box_capacity) / net_requirement if net_requirement > 0 else 5.0

                                    # Routing trigger evaluation based on scale thresholds
                                    route = ["HT"] # Heat treatment is mandatory
                                    if face_days < 1.5: route.append("FACE")
                                    if od_days < 1.5:  route.append("OD")

                                    demands.append({
                                        "channel": ch, "part": part_family, "part_code": pc,
                                        "part_text": pt, "qty": net_requirement, "route": route,
                                        "box_cap": box_capacity
                                    })
                        except: pass

        # 4. MASTER MACHINE DISPATCH SCHEDULER
        # ---------------------------------------------------------------------
        schedule = {
            "face": {"DDS (544)": []},
            "od": {"CL-46 Cell 2 ( 0945 + 0839 )": []},
            "ht": {"AICHELIN.(896)": [], "CASTLINK FURNACE( 1018 )": []}
        }
        
        hours_logged = {
            "face": {"DDS (544)": 0.0},
            "od": {"CL-46 Cell 2 ( 0945 + 0839 )": 0.0},
            "ht": {"AICHELIN.(896)": 0.0, "CASTLINK FURNACE( 1018 )": 0.0}
        }

        for j in demands:
            label = f"{j['part']}---{j['part_text']}"
            p_key = f"{j['part']}_{j['part_code']}"
            priority = "P1" if j['channel'].startswith("CH") else "P2"
            boxes_needed = max(1, int(j['qty'] / j['box_cap']))

            if "FACE" in j["route"]:
                m = "DDS (544)"
                rate = grind_rates["544"].get(p_key, 1300)
                h_req = j['qty'] / rate
                if hours_logged["face"][m] + h_req <= 24.0:
                    shift = "1" if hours_logged["face"][m] <= 8 else ("2" if hours_logged["face"][m] <= 16 else "3")
                    schedule["face"][m].append({"job": label, "qty": boxes_needed, "shift": shift, "priority": priority})
                    hours_logged["face"][m] += h_req

            if "OD" in j["route"]:
                m = "CL-46 Cell 2 ( 0945 + 0839 )"
                rate = grind_rates["1125+661"].get(p_key, 850)
                h_req = j['qty'] / rate
                if hours_logged["od"][m] + h_req <= 24.0:
                    shift = "1" if hours_logged["od"][m] <= 8 else ("2" if hours_logged["od"][m] <= 16 else "3")
                    schedule["od"][m].append({"job": label, "qty": boxes_needed, "shift": shift, "priority": priority})
                    hours_logged["od"][m] += h_req

            if "HT" in j["route"]:
                f_pref = "OM" if j['part_code'] == "100" else "IM"
                f_target = furnace_map.get(f"{f_pref}{j['part']}", "AICHELIN")
                m = "CASTLINK FURNACE( 1018 )" if "CASTLINK" in f_target else "AICHELIN.(896)"
                
                weight_factor = weights.get(p_key, 0.32)
                tot_weight = j['qty'] * weight_factor
                cap_hr = 250 if "CASTLINK" in m else 350
                h_req = tot_weight / cap_hr

                if hours_logged["ht"][m] + h_req <= 24.0:
                    schedule["ht"][m].append({"job": label, "qty": f"{int(tot_weight)} kg", "channel": j['channel']})
                    hours_logged["ht"][m] += h_req

        # Standardizing output sizes to 8 rows to preserve empty tracking lines
        for sect in schedule:
            for mach in schedule[sect]:
                while len(schedule[sect][mach]) < 8:
                    if sect == "ht": 
                        schedule[sect][mach].append({"job": "", "qty": "", "channel": ""})
                    else: 
                        schedule[sect][mach].append({"job": "", "qty": "", "shift": "", "priority": ""})

        return {"status": "success", "data": schedule}
    except Exception as e:
        return {"status": "error", "message": f"Pipeline failure exception: {str(e)}"}
