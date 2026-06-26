import os
import re
import math
import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

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
    if pd.isna(value) or value is None: return 0.0
    val_str = str(value).replace(',', '').strip()
    if not val_str or val_str.lower() in ["nan", "none", "na"]: return 0.0
    try: return float(val_str)
    except: return 0.0

def fetch_sheet_raw(base_url: str, sheet_name: str) -> pd.DataFrame:
    if not base_url: return pd.DataFrame()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", base_url)
    if not match: return pd.DataFrame()
    csv_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name.strip())}"
    try:
        res = requests.get(csv_url, timeout=20)
        if res.status_code == 200 and "<html" not in res.text[:20].lower():
            return pd.read_csv(StringIO(res.text), header=None, dtype=str)
    except: pass
    return pd.DataFrame()

# NEW ENDPOINT: Fetch specific date to repopulate or blank out the grid
@router.get("/api/v1/get-buffer")
def get_buffer(date: str):
    if date in SAVED_BUFFERS:
        return {"status": "success", "data": SAVED_BUFFERS[date]}
    return {"status": "empty", "data": None}

@router.post("/api/v1/save-buffer")
def save_buffer(payload: BufferPayload):
    SAVED_BUFFERS[payload.date] = payload.dict()
    return {"status": "success", "message": f"Buffer synced for {payload.date}"}

@router.post("/api/v1/generate-schedule")
def generate_schedule(payload: ScheduleRequest):
    target_date = payload.target_date
    try: day_num = str(int(target_date.split('-')[2]))
    except: return {"status": "error", "message": "Invalid date format."}

    user_matrix = SAVED_BUFFERS.get(target_date, {"dgbb_unit": "Days", "trb_unit": "Days", "dgbb": {}, "trb": {}})

    try:
        # MAP COMPILATION
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

        # DEMAND CALCULATION
        demands = []
        all_channels = ['CH01','CH02','CH03','CH04','CH05','CH06','CH07','CH08','CH11','SABB CH 5','T01','T02','T03','T04','T05','T06','T07','T08','T09','T10']

        for ch in all_channels:
            df_z = fetch_sheet_raw(ZEROSET_URL, ch)
            if df_z.empty: continue

            h_row, c_idx = None, None
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
                is_dgbb = ch.startswith("CH") or "SABB" in ch
                ch_grid = user_matrix["dgbb"].get(ch, {}) if is_dgbb else user_matrix["trb"].get(ch, {})
                unit_type = user_matrix["dgbb_unit"] if is_dgbb else user_matrix["trb_unit"]

                for r_pos in range(h_row + 1, len(df_z)):
                    p_cell = str(df_z.iloc[r_pos, 0]).strip()
                    if p_cell and p_cell.startswith(("MF", "FV")):
                        part_family = p_cell.replace("MF", "").replace("FV", "")
                        qty_val = clean_nan(df_z.iloc[r_pos, c_idx])
                        net_req = qty_val * 1000
                        if net_req <= 0: continue

                        for pc, pt in [("100", "OR"), ("120", "IR")]:
                            b_cap = box_cap_map.get(f"{part_family}_{pc}", 1000)
                            part_grid = ch_grid.get(pt, {})
                            
                            face_val = clean_nan(part_grid.get("face_buf"))
                            od_val = clean_nan(part_grid.get("od_buf"))
                            
                            face_days, od_days = face_val, od_val
                            if unit_type == "No. of Rings":
                                face_days = face_val / net_req if net_req > 0 else 5.0
                                od_days = od_val / net_req if net_req > 0 else 5.0
                            elif unit_type == "Boxes":
                                face_days = (face_val * b_cap) / net_req if net_req > 0 else 5.0
                                od_days = (od_val * b_cap) / net_req if net_req > 0 else 5.0

                            route = ["HT"]
                            if face_days < 1.5: route.append("FACE")
                            if od_days < 1.5: route.append("OD")
                            demands.append({"channel": ch, "part": part_family, "part_code": pc, "part_text": pt, "qty": net_req, "route": route, "box_cap": b_cap})

        # EXACT SCHEDULE BUCKETING (BY SHIFT 1, 2, 3)
        schedule = {
            "DDS (544)": {"type": "Face Grinding", "shifts": {"1": [], "2": [], "3": []}},
            "CL-46 Cell 2 ( 0945 + 0839 )": {"type": "OD Grinding", "shifts": {"1": [], "2": [], "3": []}}
        }
        hours = {"DDS (544)": 0.0, "CL-46 Cell 2 ( 0945 + 0839 )": 0.0}

        for j in demands:
            lbl = f"{j['part']} {j['part_text']}"
            p_key = f"{j['part']}_{j['part_code']}"
            priority = "P1" if j['channel'].startswith("CH") else "P2"
            boxes = max(1, math.ceil(j['qty'] / j['box_cap']))

            if "FACE" in j["route"]:
                m = "DDS (544)"
                r = grind_rates["544"].get(p_key, 1300)
                if r > 0 and hours[m] + (j['qty'] / r) <= 24.0:
                    shift = "1" if hours[m] <= 8 else ("2" if hours[m] <= 16 else "3")
                    schedule[m]["shifts"][shift].append({"qty": boxes, "job": lbl, "priority": priority})
                    hours[m] += (j['qty'] / r)

            if "OD" in j["route"]:
                m = "CL-46 Cell 2 ( 0945 + 0839 )"
                r = grind_rates["1125+661"].get(p_key, 850)
                if r > 0 and hours[m] + (j['qty'] / r) <= 24.0:
                    shift = "1" if hours[m] <= 8 else ("2" if hours[m] <= 16 else "3")
                    schedule[m]["shifts"][shift].append({"qty": boxes, "job": lbl, "priority": priority})
                    hours[m] += (j['qty'] / r)

        return {"status": "success", "data": schedule}

    except Exception as e:
        return {"status": "error", "message": f"Server logic failed: {str(e)}"}
