import os
import re
import math
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

# In-memory storage (Replace with DB for production persistence)
SAVED_BUFFERS = {}

class BufferPayload(BaseModel):
    date: str
    dgbb_unit: str
    trb_unit: str
    dgbb: Dict[str, Any]
    trb: Dict[str, Any]

class ScheduleRequest(BaseModel):
    target_date: str

def clean_nan(value):
    """Robust float conversion handling commas and spaces (adapted from your TBE reference)."""
    if pd.isna(value) or value is None: return 0.0
    val_str = str(value).replace(',', '').strip()
    if not val_str or val_str.lower() in ["nan", "none", "na"]: return 0.0
    try:
        return float(val_str)
    except:
        return 0.0

def fetch_sheet_raw(base_url: str, sheet_name: str) -> pd.DataFrame:
    """Safely fetches Google Sheets without triggering duplicate column errors."""
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    try:
        res = requests.get(csv_url, timeout=20)
        if res.status_code == 200 and "<html" not in res.text[:20].lower():
            # header=None prevents "Columns are not unique" warnings
            return pd.read_csv(StringIO(res.text), header=None, dtype=str)
    except Exception as e:
        print(f"Fetch Error [{sheet_name}]: {e}")
    return pd.DataFrame()

@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferPayload):
    # Store exactly how it came from the frontend's nested IR/OR state
    SAVED_BUFFERS[payload.date] = payload.dict()
    return {"status": "success", "message": f"Buffer synced for {payload.date}"}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    target_date = payload.target_date
    try:
        day_num = str(int(target_date.split('-')[2])) # Extract "1" from "2026-04-01"
    except:
        return {"status": "error", "message": "Invalid date format."}

    user_matrix = SAVED_BUFFERS.get(target_date, {"dgbb_unit": "Days", "trb_unit": "Days", "dgbb": {}, "trb": {}})

    try:
        # 1. COMPILE MASTER DATA MAPS
        # ---------------------------------------------------------
        weights_map = {}
        df_w = fetch_sheet_raw(MASTER_URL, "WEIGHTS")
        for row in df_w.values.tolist():
            try: weights_map[f"{str(row[0]).strip()}_{str(row[1]).strip()}"] = clean_nan(row[2])
            except: pass

        box_cap_map = {}
        df_box = fetch_sheet_raw(BOX_RING_DATA_URL, "RING PER BOX.")
        for row in df_box.values.tolist():
            try:
                fam = str(row[0]).strip().replace("MF", "")
                pcode = "100" if "O" in str(row[1]).upper() else "120"
                box_cap_map[f"{fam}_{pcode}"] = clean_nan(row[3])
            except: pass

        grind_rates = {"544": {}, "1125+661": {}}
        for tab, m_key in [("544", "544"), ("1125+661", "1125+661")]:
            df_m = fetch_sheet_raw(SHO_PRODUCTION_URL, tab)
            for row in df_m.values.tolist():
                try: grind_rates[m_key][f"{str(row[0]).strip()}_{str(row[1]).strip()}"] = clean_nan(row[4])
                except: pass

        furnace_map = {}
        df_f = fetch_sheet_raw(MASTER_URL, "Furnace Type Flexibility")
        for row in df_f.values.tolist():
            try:
                comp, furnace = str(row[1]).strip(), str(row[2]).strip().upper()
                if comp: furnace_map[comp] = furnace
            except: pass

        # 2. ZEROSET DEMAND & BUFFER ROUTING LOGIC
        # ---------------------------------------------------------
        demands = []
        all_channels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5',
                        'T01','T02','T03','T04','T05','T06','T07','T08','T09','T10']

        for ch in all_channels:
            df_z = fetch_sheet_raw(ZEROSET_URL, ch)
            if df_z.empty: continue

            h_row, c_idx = None, None
            # Locate PKWIP row safely
            for idx, row_vals in enumerate(df_z.values.tolist()[:20]):
                clean_row = [str(x).strip().upper().split('.')[0] for x in row_vals]
                if "PKWIP" in clean_row and day_num in clean_row:
                    h_row = idx
                    for col_pos, val in enumerate(row_vals):
                        if str(val).strip().split('.')[0] == day_num:
                            c_idx = col_pos
                            break
                    break

            if h_row is not None and c_idx is not None:
                # Grab buffer dictionary for this channel
                is_dgbb = ch.startswith("CH") or "SABB" in ch
                ch_grid = user_matrix["dgbb"].get(ch, {}) if is_dgbb else user_matrix["trb"].get(ch, {})
                unit_type = user_matrix["dgbb_unit"] if is_dgbb else user_matrix["trb_unit"]

                for r_pos in range(h_row + 1, len(df_z)):
                    p_cell = str(df_z.iloc[r_pos, 0]).strip()
                    if p_cell and p_cell.startswith(("MF", "FV")):
                        part_family = p_cell.replace("MF", "").replace("FV", "")
                        qty_val = clean_nan(df_z.iloc[r_pos, c_idx])
                        
                        net_req = qty_val * 1000 # 5.0 -> 5000 rings
                        if net_req <= 0: continue

                        for pc, pt in [("100", "OR"), ("120", "IR")]:
                            b_cap = box_cap_map.get(f"{part_family}_{pc}", 1000)
                            part_grid = ch_grid.get(pt, {}) # Access specific IR or OR UI data
                            
                            face_val = clean_nan(part_grid.get("face_buf"))
                            od_val = clean_nan(part_grid.get("od_buf"))
                            
                            # Convert everything to Days for logical routing
                            face_days, od_days = face_val, od_val
                            if unit_type == "No. of Rings":
                                face_days = face_val / net_req if net_req > 0 else 5.0
                                od_days = od_val / net_req if net_req > 0 else 5.0
                            elif unit_type == "Boxes":
                                face_days = (face_val * b_cap) / net_req if net_req > 0 else 5.0
                                od_days = (od_val * b_cap) / net_req if net_req > 0 else 5.0

                            # Decision engine
                            route = ["HT"]
                            if face_days < 1.5: route.append("FACE")
                            if od_days < 1.5: route.append("OD")

                            demands.append({
                                "channel": ch, "part": part_family, "part_code": pc, "part_text": pt,
                                "qty": net_req, "route": route, "box_cap": b_cap
                            })

        # 3. MACHINE DISPATCH GENERATION
        # ---------------------------------------------------------
        schedule = {
            "face": {"DDS (544)": []},
            "od": {"CL-46 Cell 2 ( 0945 + 0839 )": []},
            "ht": {"AICHELIN.(896)": [], "CASTLINK FURNACE( 1018 )": []}
        }
        hours = { "face": {"DDS (544)": 0.0}, "od": {"CL-46 Cell 2 ( 0945 + 0839 )": 0.0}, "ht": {"AICHELIN.(896)": 0.0, "CASTLINK FURNACE( 1018 )": 0.0} }

        for j in demands:
            lbl = f"{j['part']}---{j['part_text']}"
            p_key = f"{j['part']}_{j['part_code']}"
            priority = "P1" if j['channel'].startswith("CH") else "P2"
            boxes = max(1, math.ceil(j['qty'] / j['box_cap']))

            if "FACE" in j["route"]:
                m = "DDS (544)"
                r = grind_rates["544"].get(p_key, 1300)
                if r > 0 and hours["face"][m] + (j['qty'] / r) <= 24.0:
                    shift = "1" if hours["face"][m] <= 8 else ("2" if hours["face"][m] <= 16 else "3")
                    schedule["face"][m].append({"job": lbl, "qty": boxes, "shift": shift, "priority": priority})
                    hours["face"][m] += (j['qty'] / r)

            if "OD" in j["route"]:
                m = "CL-46 Cell 2 ( 0945 + 0839 )"
                r = grind_rates["1125+661"].get(p_key, 850)
                if r > 0 and hours["od"][m] + (j['qty'] / r) <= 24.0:
                    shift = "1" if hours["od"][m] <= 8 else ("2" if hours["od"][m] <= 16 else "3")
                    schedule["od"][m].append({"job": lbl, "qty": boxes, "shift": shift, "priority": priority})
                    hours["od"][m] += (j['qty'] / r)

            if "HT" in j["route"]:
                f_pref = "OM" if j['part_code'] == "100" else "IM"
                f_targ = furnace_map.get(f"{f_pref}{j['part']}", "AICHELIN")
                m = "CASTLINK FURNACE( 1018 )" if "CASTLINK" in f_targ else "AICHELIN.(896)"
                
                wt = weights_map.get(p_key, 0.30)
                tot_kg = j['qty'] * wt
                cap = 250 if "CASTLINK" in m else 350
                if hours["ht"][m] + (tot_kg / cap) <= 24.0:
                    schedule["ht"][m].append({"job": lbl, "qty": f"{int(tot_kg)} kg", "channel": j['channel']})
                    hours["ht"][m] += (tot_kg / cap)

        # Pad output to minimum 5 rows for stable UI rendering
        for cat in schedule:
            for m in schedule[cat]:
                while len(schedule[cat][m]) < 5:
                    if cat == "ht": schedule[cat][m].append({"job": "", "qty": "", "channel": ""})
                    else: schedule[cat][m].append({"job": "", "qty": "", "shift": "", "priority": ""})

        return {"status": "success", "data": schedule}

    except Exception as e:
        return {"status": "error", "message": f"Server logic failed: {str(e)}"}
