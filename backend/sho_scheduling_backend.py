import os
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

# --- ENVIRONMENT VARIABLES FOR GOOGLE SHEET STREAM EXPORTS ---
ZEROSET_URL = os.getenv("ZEROSET_URL", "")
SHO_PRODUCTION_URL = os.getenv("SHO_PRODUCTION_URL", "")
BOX_RING_DATA_URL = os.getenv("BOX_RING_DATA_URL", "")

# --- DATA TRANSITION MODELS ---
class BufferRow(BaseModel):
    part_type: str
    component: str  # "IR" (120) or "OR" (100)
    channel: str
    channel_buffer: float
    next_type_buffer: float
    od_buffer: Optional[float] = 0.0
    face_buffer: Optional[float] = 0.0
    ht_buffer: Optional[float] = 0.0

class ScheduleRequest(BaseModel):
    target_date: str
    unit_mode: str  # "Days", "Boxes", "Rings"
    buffers: List[BufferRow]

# --- ROBUST RAW ROW DATA EXTRACTION ENGINE ---
def read_sheet_positional(url: str, sheet_name: Any = 0) -> pd.DataFrame:
    """Reads spreadsheets by sequence indexes to eliminate duplicate column collisions."""
    if not url:
        return pd.DataFrame()
    try:
        df = pd.read_excel(url, sheet_name=sheet_name, header=None)
        return df.fillna(0.0)
    except Exception as e:
        print(f"Extraction exception on sheet '{sheet_name}': {e}")
        return pd.DataFrame()

def parse_zeroset_plan(df: pd.DataFrame, target_date: str) -> Dict[str, float]:
    """Scans the demand table to isolate columns matching target timeline keys."""
    demands = {}
    if df.empty: return demands

    date_col_idx = None
    for idx, row in df.iterrows():
        row_str = [str(cell).strip().upper() for cell in row.values]
        if "MTD" in row_str or "PKWIP" in row_str:
            for c_idx, cell in enumerate(row_str):
                if target_date.upper() in cell:
                    date_col_idx = c_idx
                    break
            if date_col_idx is not None: break

    if date_col_idx is None: return demands

    for idx, row in df.iterrows():
        raw_type = str(row.iloc[0]).strip().upper()
        if not raw_type or raw_type in ["0.0", "TYPE", "MTD", "PKWIP", "TOTAL"]:
            continue
        
        cleaned_type = raw_type.replace("MF", "").strip() if raw_type.startswith("MF") else raw_type
        try:
            val = float(row.iloc[date_col_idx])
            if val > 0:
                demands[cleaned_type] = val * 1000.0
        except:
            continue
            
    return demands

def parse_weights_and_flex(url: str) -> tuple:
    """Extracts material component configuration parameters and furnace priorities."""
    weights_df = read_sheet_positional(url, sheet_name="WEIGHTS")
    flex_df = read_sheet_positional(url, sheet_name="Furnace Type Flexibility")
    
    weight_map = {}
    if not weights_df.empty:
        for idx, row in weights_df.iterrows():
            if idx == 0: continue
            t = str(row.iloc[0]).strip().upper()
            comp = str(row.iloc[1]).strip()
            try:
                w = float(row.iloc[2])
                if t not in weight_map: weight_map[t] = {}
                weight_map[t][comp] = w
            except: continue

    flex_map = {}
    if not flex_df.empty:
        for idx, row in flex_df.iterrows():
            if idx == 0: continue
            t = str(row.iloc[0]).strip().upper()
            primary = str(row.iloc[1]).strip().upper()
            alt1 = str(row.iloc[2]).strip().upper() if len(row) > 2 else ""
            flex_map[t] = {"primary": primary, "alt1": alt1}

    return weight_map, flex_map

def parse_box_capacities(url: str) -> Dict[str, Dict[str, int]]:
    """Generates structural dictionary translation layers for box volumetric counts."""
    df = read_sheet_positional(url, sheet_name=0)
    caps = {}
    if df.empty: return caps
    
    for idx, row in df.iterrows():
        for col_idx in [0, 3]:
            if col_idx >= len(row): continue
            t = str(row.iloc[col_idx]).strip().upper()
            if not t or t in ["TYPE", "0.0"]: continue
            try:
                or_val = int(row.iloc[col_idx + 1])
                ir_val = int(row.iloc[col_idx + 2])
                caps[t] = {"100": or_val, "120": ir_val}
            except: continue
    return caps

# --- OPTIMIZED CAPACITY ROUTING ALGORITHMS ---
def dispatch_heat_treatment(net_demand: Dict[str, float], weights: Dict, flex: Dict) -> List[Dict]:
    """Distributes system components across thermal units checking for changeovers."""
    furnaces = {
        "AICHELIN.(896)": {"cap": 350, "jobs": [], "load": 0.0},
        "CASTLINK FURNACE( 1018 )": {"cap": 250, "jobs": [], "load": 0.0},
        "ROLLER FURNACE ( 148 )": {"cap": 250, "jobs": [], "load": 0.0},
        "SIMPLICITY FURNACE(1238)": {"cap": 180, "jobs": [], "load": 0.0},
        "BIRLEC FURNACE  ( 1158 )": {"cap": 170, "jobs": [], "load": 0.0},
        "SHOEI FURNACE   ( 1062 )": {"cap": 350, "jobs": [], "load": 0.0},
        "AICHELIN UNITHERM ( 2033 )": {"cap": 250, "jobs": [], "load": 0.0}
    }
    
    HT_CHANGEOVER = 0.5 # 30-minute changeover time constraint
    
    for part, qty in net_demand.items():
        if qty <= 0: continue
        w_or = weights.get(part, {}).get("100", 0.2)
        w_ir = weights.get(part, {}).get("120", 0.18)
        
        total_kg = (qty * w_or) + (qty * w_ir)
        pref = flex.get(part, {}).get("primary", "AICHELIN.(896)")
        alt = flex.get(part, {}).get("alt1", "CASTLINK FURNACE( 1018 )")
        
        target = pref if pref in furnaces else "AICHELIN.(896)"
        hrs_req = (total_kg / furnaces[target]["cap"]) + HT_CHANGEOVER
        
        if furnaces[target]["load"] + hrs_req > 24.0:
            target = alt if alt in furnaces else "CASTLINK FURNACE( 1018 )"
            hrs_req = (total_kg / furnaces[target]["cap"]) + HT_CHANGEOVER
            
        if furnaces[target]["load"] + hrs_req <= 24.0:
            furnaces[target]["jobs"].append({
                "type": part,
                "qty_kg": round(total_kg, 1),
                "channel": "Combined Line"
            })
            furnaces[target]["load"] += hrs_req
            
    return [{"furnace": k, "capacity": f"{v['cap']} kg/h", "jobs": v["jobs"]} for k, v in furnaces.items()]

def dispatch_grinding(net_demand: Dict[str, float]) -> List[Dict]:
    """Splits target output into continuous 8-hour shift groups with 2-hour changeovers."""
    machines = [
        {"name": "544 Machine", "type": "Face", "std_hr": 7771, "box_hr": 12.0},
        {"name": "Gardner BG1", "type": "Face", "std_hr": 7200, "box_hr": 10.0},
        {"name": "1904+170 Line", "type": "OD", "std_hr": 6986, "box_hr": 17.0}
    ]
    
    G_CHANGEOVER = 2.0 # 2-hour changeover constraint
    schedule_out = []
    
    for m in machines:
        avail_hrs = [8.0, 8.0, 8.0]
        shifts_res = [
            {"qty": 0, "job": "", "priority": ""},
            {"qty": 0, "job": "", "priority": ""},
            {"qty": 0, "job": "", "priority": ""}
        ]
        
        for part, qty in net_demand.items():
            if qty <= 0: continue
            needed_rings = qty
            
            for s_idx in range(3):
                if needed_rings <= 0: break
                
                net_hrs = avail_hrs[s_idx] - (G_CHANGEOVER if shifts_res[s_idx]["job"] else 0)
                if net_hrs <= 0: continue
                
                run_rings = min(needed_rings, net_hrs * m["std_hr"])
                if run_rings > 0:
                    shifts_res[s_idx]["qty"] += int(run_rings)
                    shifts_res[s_idx]["job"] = f"{part}-OR/IR"
                    shifts_res[s_idx]["priority"] = "P1"
                    
                    needed_rings -= run_rings
                    avail_hrs[s_idx] -= (run_rings / m["std_hr"])
                    
        schedule_out.append({
            "machine": m["name"],
            "type": m["type"],
            "std_box": int(m["box_hr"]),
            "shift_1": shifts_res[0],
            "shift_2": shifts_res[1],
            "shift_3": shifts_res[2]
        })
        
    return schedule_out

# --- MAIN ROUTER SCHEDULING DISPATCH ENDPOINT ---
@router.post("/api/schedule")
async def generate_schedule(req: ScheduleRequest):
    try:
        zeroset_df = read_sheet_positional(ZEROSET_URL)
        weights, flex = parse_weights_and_flex(SHO_PRODUCTION_URL)
        box_caps = parse_box_capacities(BOX_RING_DATA_URL)
        
        base_demand = parse_zeroset_plan(zeroset_df, req.target_date)
        net_demand = base_demand.copy()
        
        for row in req.buffers:
            pt = row.part_type.upper()
            if pt not in net_demand: continue
            
            comp_code = "120" if row.component == "IR" else "100"
            box_capacity = box_caps.get(pt, {}).get(comp_code, 500)
            
            total_input_units = (
                row.channel_buffer + row.next_type_buffer + 
                row.od_buffer + row.face_buffer + row.ht_buffer
            )
            
            deduction_rings = 0.0
            if req.unit_mode == "Boxes":
                deduction_rings = total_input_units * box_capacity
            elif req.unit_mode == "Days":
                deduction_rings = total_input_units * base_demand.get(pt, 0.0)
            else:
                deduction_rings = total_input_units
                
            net_demand[pt] = max(0.0, net_demand[pt] - deduction_rings)
            
        return {
            "date": req.target_date,
            "unit_mode_processed": req.unit_mode,
            "face_od_grinding": dispatch_grinding(net_demand),
            "heat_treatment": dispatch_heat_treatment(net_demand, weights, flex)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
