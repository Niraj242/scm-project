import os
import re
import math
import pandas as pd
import requests
import io
import time
import gc
import json
import uvicorn
from datetime import datetime, timedelta
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List

# --- APP SETUP & CORS ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows your React app to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

# --- ENV VARIABLES ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

FAM_REGEX = re.compile(r'(\d{3,5})')
BUFFER_DB_FILE = "buffer_db.json"

class BufferPayload(BaseModel):
    sector: str
    date: str
    unit_mode: str
    ht_unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

class ScheduleRequest(BaseModel):
    sector: str
    date: str
    unit_mode: str
    ht_unit_mode: str
    entries: Dict[str, Any]
    unlocked_blocks: List[str]

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

# --- BUFFER DB LOGIC ---
def load_buffer_db():
    if os.path.exists(BUFFER_DB_FILE):
        with open(BUFFER_DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_buffer_db(data):
    with open(BUFFER_DB_FILE, "w") as f:
        json.dump(data, f)

@router.get("/api/buffer")
def get_buffer(sector: str, date: str):
    db = load_buffer_db()
    key = f"{sector}_{date}"
    return db.get(key, {"entries": {}, "unlocked_blocks": [], "unit_mode": "Days", "ht_unit_mode": "Rings"})

@router.post("/api/buffer")
def save_buffer(payload: BufferPayload):
    db = load_buffer_db()
    key = f"{payload.sector}_{payload.date}"
    db[key] = {
        "entries": payload.entries,
        "unlocked_blocks": payload.unlocked_blocks,
        "unit_mode": payload.unit_mode,
        "ht_unit_mode": payload.ht_unit_mode,
        "updated_at": datetime.now().isoformat()
    }
    save_buffer_db(db)
    return {"status": "success"}

# --- UTILS ---
def parse_family(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", "", "UNKNOWN"]: return None
    
    if "HUB" in text:
        match_hub = re.search(r'(T?\s*HUB\s*\d+\.?\d*)', text)
        if match_hub: return match_hub.group(1).replace(" ", "")
        return "HUB"
        
    if text.startswith("T ") or re.match(r'^T\d+', text):
        match_t = re.search(r'(T\s*\d+)', text)
        if match_t: return match_t.group(1).replace(" ", "")
        return "T"

    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    return base

def safe_float(val):
    if pd.isna(val) or val is None: return 0.0
    try:
        return float(str(val).replace(',', '').strip().lower())
    except Exception:
        return 0.0

def load_excel_all_sheets(url, file_label="Unknown"):
    logs = []
    if not url or url.strip() == "": return None, logs
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return None, logs
        content = io.BytesIO(resp.content)
        return pd.read_excel(content, sheet_name=None, header=None), logs
    except Exception as e:
        return None, [f"[{file_label}] ERR: {str(e)}"]

@router.post("/api/schedule")
def generate_schedule(payload: ScheduleRequest):
    debug_logs = []
    try:
        req_date = datetime.strptime(payload.date, "%Y-%m-%d")
        
        # 1. PARSE ZEROSET (Demands)
        channel_demands = {} 
        sheets_zero, _ = load_excel_all_sheets(ZEROSET_URL, "ZEROSET")
        
        if sheets_zero:
            for sheet_name, df_zero in sheets_zero.items():
                for r in range(len(df_zero)):
                    row_strs = [str(x).strip().upper() for x in df_zero.iloc[r].values]
                    if any("TYPE" in x or "PART" in x for x in row_strs):
                        for idx_r in range(r + 1, len(df_zero)):
                            row_vals = df_zero.iloc[idx_r].values
                            fam = parse_family(row_vals[0])
                            if not fam: continue
                            
                            qty = 0.0
                            for val in row_vals[1:]:
                                v = safe_float(val)
                                if v > 0 and v < 50000:
                                    qty = max(qty, v)
                            
                            if qty > 0:
                                # "5" means 5000 logic
                                if qty <= 70: qty = qty * 1000 
                                if fam not in channel_demands:
                                    channel_demands[fam] = {'IR': qty, 'OR': qty, 'channel': str(sheet_name)}
                                else:
                                    channel_demands[fam]['IR'] = max(channel_demands[fam]['IR'], qty)
                                    channel_demands[fam]['OR'] = max(channel_demands[fam]['OR'], qty)
            del sheets_zero

        # 2. BOX MATRIX (FIXED TO READ ACROSS WHOLE ROW)
        box_matrix = {}
        sheets_box, _ = load_excel_all_sheets(BOX_RING_DATA_URL, "BOX_MATRIX")
        if sheets_box and 'RING PER BOX.' in sheets_box:
            df_box = sheets_box['RING PER BOX.'].fillna('')
            for idx in range(1, len(df_box)):
                row_vals = list(df_box.iloc[idx])
                # Jump in chunks of 3 (TYPE | O/R | I/R)
                for i in range(0, len(row_vals) - 2, 3):
                    fam_raw = str(row_vals[i]).strip()
                    if not fam_raw: continue
                    fam = parse_family(fam_raw)
                    if fam:
                        or_qty = safe_float(row_vals[i+1])
                        ir_qty = safe_float(row_vals[i+2])
                        box_matrix[fam] = {
                            'OR': or_qty if or_qty > 0 else 100,
                            'IR': ir_qty if ir_qty > 0 else 100
                        }
            del sheets_box

        # 3. PRODUCTION RATES & MACHINES
        weight_matrix, furnace_rates = {}, {}
        machines_data = {'FACE': {}, 'OD': {}}
        
        sheets_prod, _ = load_excel_all_sheets(SHO_PRODUCTION_URL, "SHO_PRODUCTION")
        if sheets_prod:
            if 'WEIGHTS' in sheets_prod:
                df_w = sheets_prod['WEIGHTS'].fillna('')
                for _, r in df_w.iterrows():
                    fam = parse_family(r.iloc[0])
                    if fam:
                        weight_matrix[f"{fam}_IR"] = safe_float(r.iloc[2]) or 0.15
                        weight_matrix[f"{fam}_OR"] = safe_float(r.iloc[1]) or 0.15
                        # Furnace capacity fallback (Assume 400kg/hr if not listed)
                        furnace_rates[fam] = safe_float(r.iloc[3]) or 400.0 

            for sheet_name, df_m in sheets_prod.items():
                str_matrix = df_m.fillna('').astype(str).values
                for r in range(str_matrix.shape[0]):
                    row_text = " ".join(str_matrix[r]).upper()
                    if 'MACHINE' in row_text:
                        m_num = next((c for c in str_matrix[r] if c.strip() and c.strip().upper() != 'MACHINE'), f"MC_{r}")
                        m_type = "FACE" if "FACE" in row_text else "OD"
                        
                        if m_num not in machines_data[m_type]:
                            machines_data[m_type][m_num] = {'name': m_num, 'rates': {}, 'avail_hours': 24.0, 'rows': []}
                        
                        for offset in range(2, 20):
                            if r + offset >= str_matrix.shape[0]: break
                            vals = str_matrix[r + offset]
                            fam = parse_family(vals[0])
                            if fam:
                                rate = safe_float(vals[3]) 
                                if rate > 0:
                                    rpb = safe_float(vals[6]) or 100 
                                    machines_data[m_type][m_num]['rates'][f"{fam}_IR"] = rate / rpb
                                    machines_data[m_type][m_num]['rates'][f"{fam}_OR"] = rate / rpb
            del sheets_prod

        # 4. BUFFER DEDUCTIONS (Full Restored Logic)
        for fam, qty in channel_demands.items():
            rpb_ir = box_matrix.get(fam, {}).get('IR', 100)
            rpb_or = box_matrix.get(fam, {}).get('OR', 100)
            
            # Extract inputs from UI payload matching the family's channel
            cha = qty.get('channel', '')
            ui_ir_buf = safe_float(payload.entries.get(f"ch_buffer_1_{cha}_IR", 0))
            ui_or_buf = safe_float(payload.entries.get(f"ch_buffer_1_{cha}_OR", 0))
            ui_ht_ir = safe_float(payload.entries.get(f"ht_buffer_1_{cha}_IR", 0))
            ui_ht_or = safe_float(payload.entries.get(f"ht_buffer_1_{cha}_OR", 0))

            # Deduct Standard Buffer (OD/FACE)
            if payload.unit_mode == 'Days':
                qty['IR'] = max(0, qty['IR'] - (ui_ir_buf * qty['IR'] / 30))
                qty['OR'] = max(0, qty['OR'] - (ui_or_buf * qty['OR'] / 30))
            elif payload.unit_mode == 'Boxes':
                qty['IR'] = max(0, qty['IR'] - (ui_ir_buf * rpb_ir))
                qty['OR'] = max(0, qty['OR'] - (ui_or_buf * rpb_or))
            elif payload.unit_mode == 'Rings':
                qty['IR'] = max(0, qty['IR'] - ui_ir_buf)
                qty['OR'] = max(0, qty['OR'] - ui_or_buf)

            # Store HT explicit buffer needs
            qty['HT_IR_REQ'] = qty['IR']
            qty['HT_OR_REQ'] = qty['OR']
            
            if payload.ht_unit_mode == 'Days':
                qty['HT_IR_REQ'] = max(0, qty['HT_IR_REQ'] - (ui_ht_ir * qty['HT_IR_REQ'] / 30))
                qty['HT_OR_REQ'] = max(0, qty['HT_OR_REQ'] - (ui_ht_or * qty['HT_OR_REQ'] / 30))
            elif payload.ht_unit_mode == 'Boxes':
                qty['HT_IR_REQ'] = max(0, qty['HT_IR_REQ'] - (ui_ht_ir * rpb_ir))
                qty['HT_OR_REQ'] = max(0, qty['HT_OR_REQ'] - (ui_ht_or * rpb_or))
            elif payload.ht_unit_mode == 'Rings':
                qty['HT_IR_REQ'] = max(0, qty['HT_IR_REQ'] - ui_ht_ir)
                qty['HT_OR_REQ'] = max(0, qty['HT_OR_REQ'] - ui_ht_or)

        # 5. SCHEDULING - FACE & OD GRINDING
        def schedule_machines(m_type, demands):
            result = []
            for m_num, m_info in machines_data.get(m_type, {}).items():
                hours = m_info['avail_hours']
                rows = []
                for fam, qty in list(demands.items()):
                    if hours <= 0: break
                    
                    for p_type in ['IR', 'OR']:
                        req = qty.get(p_type, 0)
                        if req > 0 and hours > 0:
                            # Fallback rate if not found precisely in sheet
                            rate = m_info['rates'].get(f"{fam}_{p_type}", 15.0) 
                            assigned_boxes = min((req / box_matrix.get(fam, {}).get(p_type, 100)), hours * rate)
                            
                            if assigned_boxes > 0:
                                hours -= (assigned_boxes / rate)
                                qty[p_type] -= (assigned_boxes * box_matrix.get(fam, {}).get(p_type, 100))
                                
                                # Shift distribution logic restored
                                p_2nd = math.ceil(assigned_boxes * 0.4)
                                p_3rd = math.ceil(assigned_boxes * 0.6)
                                
                                rows.append({
                                    "part": f"{fam} {p_type}", 
                                    "std_box": str(int(rate)), 
                                    "p_2nd": str(p_2nd), 
                                    "p_3rd": str(p_3rd)
                                })
                                
                if rows: result.append({"machine": m_num, "rows": rows})
            return result

        final_face = schedule_machines('FACE', channel_demands)
        final_od = schedule_machines('OD', channel_demands)

        # 6. SCHEDULING - HEAT TREATMENT (FULL LOOP RESTORED)
        ht_formatted = []
        default_furnaces = ["AICHELIN.(896)", "IPSEN-1", "IPSEN-2", "IPSEN-3", "IPSEN-4"]
        furnace_clocks = {f: {"avail_hours": 24.0, "current_fam": None, "rows": []} for f in default_furnaces}

        for fam, demands in channel_demands.items():
            w_ir = weight_matrix.get(f"{fam}_IR", 0.15)
            w_or = weight_matrix.get(f"{fam}_OR", 0.15)
            kg_hr = furnace_rates.get(fam, 400.0)

            for p_code, rings, weight in [('IR', demands.get('HT_IR_REQ', 0), w_ir), ('OR', demands.get('HT_OR_REQ', 0), w_or)]:
                if rings > 10: # Only schedule if meaningful qty
                    time_needed = (rings * weight) / kg_hr
                    
                    # Find best furnace (Prioritize one already running this family to save setup, else max time)
                    best_fur = None
                    setup_penalty = 1.0 # 1 hour setup
                    
                    for fur, ctx in furnace_clocks.items():
                        if ctx["current_fam"] == fam:
                            best_fur = fur
                            setup_penalty = 0.0
                            break
                            
                    if not best_fur:
                        best_fur = max(furnace_clocks.keys(), key=lambda k: furnace_clocks[k]["avail_hours"])

                    furnace_clocks[best_fur]["avail_hours"] -= (time_needed + setup_penalty)
                    furnace_clocks[best_fur]["current_fam"] = fam
                    
                    furnace_clocks[best_fur]["rows"].append({
                        "part": f"{fam}-{p_code}",
                        "qty": str(int(rings)),
                        "cha": demands.get('channel', 'N/A'),
                        "rate": str(int(kg_hr)),
                        "alert": furnace_clocks[best_fur]["avail_hours"] < 0 # Flag if overbooked
                    })

        for fur, f_data in furnace_clocks.items():
            if f_data["rows"]:
                ht_formatted.append({
                    "furnace": fur, 
                    "capacity": f_data["rows"][0]["rate"], 
                    "rows": f_data["rows"]
                })

        return {
            "status": "success",
            "debug_logs": debug_logs,
            "data": {
                "face_grinding": final_face,
                "od_grinding": final_od,
                "heat_treatment": ht_formatted
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "debug_logs": debug_logs, "detail": str(e), "trace": traceback.format_exc()}

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
