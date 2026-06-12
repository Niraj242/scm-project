from fastapi import APIRouter, HTTPException, Query
import pandas as pd
import requests
import io
import threading
import time
import math
import re
import concurrent.futures
from datetime import datetime
from settings import settings

router = APIRouter()

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 5

EXACT_JOBWORK_SHEET_NAME = "Worksheet" 

GLOBAL_RAW_RECORDS = {"mo_data": [], "jw_data": [], "ch_data": []}

MO_GROUP_REGEX = re.compile(r'^(\d{4,})')
FAM_GARBAGE_REGEX = re.compile(r'(?i)(NORMAL|INNER|OUTER|GENERIC PRODUCT)')
FAM_CORE_REGEX = re.compile(r'(\d{3,}[A-Z0-9\-]*)')
FAM_SUFFIX_REGEX = re.compile(r'(?i)(IM|OM)$')

def format_dt(dt):
    """Standardizes all dates sent to the frontend to DD-MM-YYYY"""
    if dt and not pd.isna(dt):
        return dt.strftime("%d-%m-%Y")
    return "-"

def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "")
    if val.endswith(".0"): 
        val = val[:-2]
    if not val or val in ["NAN", "-", "...", "", "NAT", "NONE", "NA", "NULL"]: 
        return None
    if len(val) < 4: 
        return None 
    return val

def get_mo_group(clean_mo_str):
    if not clean_mo_str: return None
    match = MO_GROUP_REGEX.match(clean_mo_str)
    group = match.group(1) if match else clean_mo_str[:4] if len(clean_mo_str) >= 4 else clean_mo_str
    if not group or group.strip() == "": return None
    return group

def clean_family_name(text):
    if pd.isna(text): return "Unknown Bearing"
    t = str(text).upper()
    t = FAM_GARBAGE_REGEX.sub('', t)
    match = FAM_CORE_REGEX.search(t)
    if match:
        core = match.group(1)
        core = FAM_SUFFIX_REGEX.sub('', core)
        return core.strip('- ')
    return "Unknown Bearing"

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except:
        return 0.0

# Fixed: Added dayfirst explicit control for MM-DD vs DD-MM standardizing
def parse_date_safe(value, dayfirst=True):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=dayfirst)
        return parsed.date() if not pd.isna(parsed) else None
    except:
        return None

def determine_component(text):
    text = str(text).strip().upper()
    if "OM" in text or "OUTER" in text: return "OM"
    return "IM" 

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        
        try:
            xls = pd.ExcelFile(content, engine='calamine')
        except ImportError:
            xls = pd.ExcelFile(content)
            
        time.sleep(0.05) 
        
        sheets = {}
        for sheet in xls.sheet_names:
            time.sleep(0.01)
            df = xls.parse(sheet)
            df.columns = [str(c).strip().lower() for c in df.columns]
            sheets[sheet] = df
        return sheets
    except Exception as e:
        print(f"Error loading {url}: {e}")
        return {}

def fetch_all_data_concurrently():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_mo = executor.submit(load_excel_sheets, settings.MO_DATA_URL)
        f_jw = executor.submit(load_excel_sheets, settings.JOBWORK_REPORT_URL)
        f_trb = executor.submit(load_excel_sheets, settings.TRB_MASTER_URL)
        f_dgbb = executor.submit(load_excel_sheets, settings.DGBB_MASTER_URL)
        
        return f_mo.result(), f_jw.result(), f_trb.result(), f_dgbb.result()

def ensure_mo_in_summary(summary_map, mo_group, potential_family="Unknown Bearing"):
    if mo_group not in summary_map:
        summary_map[mo_group] = {
            "mo": mo_group, 
            "base_product": potential_family, 
            "ch_qty": 0.0, 
            "ch_dates": [],
            "components": {
                "IM": {"qty_req": 0, "sho": 0, "sho_dates": [], "tb": 0, "tb_dates": []},
                "OM": {"qty_req": 0, "sho": 0, "sho_dates": [], "tb": 0, "tb_dates": []}
            }
        }
    else:
        if potential_family != "Unknown Bearing" and summary_map[mo_group]["base_product"] == "Unknown Bearing":
            summary_map[mo_group]["base_product"] = potential_family
            
    return summary_map[mo_group]

def compile_summary_data(start_date_str=None, end_date_str=None):
    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str and start_date_str.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str and end_date_str.strip() not in ["", "null", "None"] else None
    
    summary_map = {}
    
    for r in GLOBAL_RAW_RECORDS["mo_data"]:
        data = ensure_mo_in_summary(summary_map, r["mo_group"], r["variant"])
        data["components"][r["comp_type"]]["qty_req"] = r["qty_req"]
        
    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        sho_valid = True
        if s_dt or e_dt:
            d = r["sho_date"]
            if not d: sho_valid = False 
            else:
                if s_dt and e_dt: sho_valid = (s_dt <= d <= e_dt)
                elif s_dt: sho_valid = (d >= s_dt)
                elif e_dt: sho_valid = (d <= e_dt)
        
        tb_valid = True
        if s_dt or e_dt:
            d = r["tb_date"]
            if not d: tb_valid = False
            else:
                if s_dt and e_dt: tb_valid = (s_dt <= d <= e_dt)
                elif s_dt: tb_valid = (d >= s_dt)
                elif e_dt: tb_valid = (d <= e_dt)

        data = ensure_mo_in_summary(summary_map, r["mo_group"], r["variant"])
        comp = r["comp_type"]
        
        if sho_valid and r["sho_qty"] > 0:
            data["components"][comp]["sho"] += r["sho_qty"]
            if r["sho_date"]: data["components"][comp]["sho_dates"].append(r["sho_date"])
            
        if tb_valid and r["tb_qty"] > 0:
            data["components"][comp]["tb"] += r["tb_qty"]
            if r["tb_date"]: data["components"][comp]["tb_dates"].append(r["tb_date"])
            
    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        ch_valid = True
        if s_dt or e_dt:
            d = r["ch_date"]
            if not d: ch_valid = False
            else:
                if s_dt and e_dt: ch_valid = (s_dt <= d <= e_dt)
                elif s_dt: ch_valid = (d >= s_dt)
                elif e_dt: ch_valid = (d <= e_dt)
                
        if ch_valid and r["ch_qty"] > 0:
            data = ensure_mo_in_summary(summary_map, r["mo_group"], r["variant"])
            data["ch_qty"] += r["ch_qty"]
            if r["ch_date"]: data["ch_dates"].append(r["ch_date"])

    compiled_summary = []
    for mo, data in summary_map.items():
        im = data["components"]["IM"]
        om = data["components"]["OM"]
        req = max(im["qty_req"], om["qty_req"])
        
        status = "Completed" if (data["ch_qty"] >= req and req > 0) else ("In Process" if (im["sho"] > 0 or om["sho"] > 0) else "Yet to Start")
        
        # Format explicitly to DD-MM-YYYY after true minimum calculation
        ch_d = format_dt(max(data["ch_dates"])) if data["ch_dates"] else "-"
        
        if im["qty_req"] > 0 or im["sho"] > 0 or data["ch_qty"] > 0:
            sho_d = format_dt(min(im["sho_dates"])) if im["sho_dates"] else "-"
            tb_d = format_dt(max(im["tb_dates"])) if im["tb_dates"] else "-"
            compiled_summary.append({
                "mo": mo, "base_product": data["base_product"], "component": "IM",
                "qty_req": math.ceil(im["qty_req"]), "sho_qty": math.ceil(im["sho"]), "sho_date": sho_d,
                "tb_qty": math.ceil(im["tb"]), "tb_date": tb_d,
                "ch_qty": math.ceil(data["ch_qty"]), "ch_date": ch_d, "status": status
            })
        
        if om["qty_req"] > 0 or om["sho"] > 0:
            sho_d = format_dt(min(om["sho_dates"])) if om["sho_dates"] else "-"
            tb_d = format_dt(max(om["tb_dates"])) if om["tb_dates"] else "-"
            compiled_summary.append({
                "mo": mo, "base_product": data["base_product"], "component": "OM",
                "qty_req": math.ceil(om["qty_req"]), "sho_qty": math.ceil(om["sho"]), "sho_date": sho_d,
                "tb_qty": math.ceil(om["tb"]), "tb_date": tb_d,
                "ch_qty": math.ceil(data["ch_qty"]), "ch_date": ch_d, "status": status
            })

    compiled_summary.sort(key=lambda x: (x["mo"], x["component"]))
    return compiled_summary


def process_traceability_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_RAW_RECORDS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets, jobwork_sheets, trb_sheets, dgbb_sheets = fetch_all_data_concurrently()

        raw_mo_data = []
        raw_jw_data = []
        raw_ch_data = []

        for _, df in mo_sheets.items():
            time.sleep(0.01) 
            if "mo#" not in df.columns: continue
            
            if "pdiv" in df.columns:
                df["pdiv"] = df["pdiv"].fillna("").astype(str).str.strip().str.upper()
                df = df[df["pdiv"].isin(["227D", "227T"])]

            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                comp_raw = str(row.get("comp item", "")).strip().upper()
                if not (comp_raw.startswith("IM") or comp_raw.startswith("OM")):
                    continue
                
                comp_type = "IM" if comp_raw.startswith("IM") else "OM"
                qty_req = clean_nan(row.get("qty req", 0))
                final_variant = clean_family_name(row.get("finalvariant"))
                
                if qty_req > 0:
                    raw_mo_data.append({"mo_group": mo_group, "variant": final_variant, "comp_type": comp_type, "qty_req": qty_req})

        for sheet_name, df in jobwork_sheets.items():
            time.sleep(0.01) 
            
            clean_sheet = str(sheet_name).strip().lower()
            if EXACT_JOBWORK_SHEET_NAME != "":
                if str(sheet_name).strip().lower() != EXACT_JOBWORK_SHEET_NAME.strip().lower():
                    continue
            else:
                if any(k in clean_sheet for k in ["summary", "pivot", "total", "history", "dash", "master"]):
                    continue
                
            if "po / pr no." not in df.columns: continue
            
            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                raw_product = row.get("product", "")
                variant = clean_family_name(raw_product)
                if mo_group == variant: continue 

                comp_type = determine_component(raw_product)
                sho_qty = clean_nan(row.get("qty approved", 0))
                tb_qty = clean_nan(row.get("qty returned", 0))
                # Jobwork handles DD-MM-YYYY natively
                sho_date = parse_date_safe(row.get("jw challan date"), dayfirst=True)
                tb_date = parse_date_safe(row.get("last challan date"), dayfirst=True)

                if sho_qty > 0 or tb_qty > 0:
                    raw_jw_data.append({
                        "mo_group": mo_group, "variant": variant, "comp_type": comp_type,
                        "sho_qty": sho_qty, "tb_qty": tb_qty, "sho_date": sho_date, "tb_date": tb_date
                    })

        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            time.sleep(0.01) 
            if "mo" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            
            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                variant = clean_family_name(row.get(type_col)) if type_col else "Unknown Bearing"
                if mo_group == variant: continue 

                ch_qty = clean_nan(row.get("production", 0))
                # Channel files natively handle MM-DD-YYYY
                ch_date = parse_date_safe(row.get("date"), dayfirst=False)

                if ch_qty > 0:
                    raw_ch_data.append({"mo_group": mo_group, "variant": variant, "ch_qty": ch_qty, "ch_date": ch_date})

        GLOBAL_RAW_RECORDS = {"mo_data": raw_mo_data, "jw_data": raw_jw_data, "ch_data": raw_ch_data}
        MASTER_CACHE = compile_summary_data()
        LAST_REFRESH = datetime.now()
        INITIALIZED = True

    except Exception as e:
        print(f"❌ PIPELINE ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

def background_refresh_loop():
    while True:
        try:
            process_traceability_data()
        except Exception as e:
            print(f"Background thread error: {e}")
        time.sleep(CACHE_DURATION_MINUTES * 60)

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/traceability_all_mos")
def get_all_mos(start_date: str = Query(None), end_date: str = Query(None)):
    if not INITIALIZED:
        return {"status": "initializing", "data": []}
        
    if start_date or end_date:
        data_slice = compile_summary_data(start_date, end_date)
    else:
        data_slice = MASTER_CACHE
        
    return {"status": "success", "data": data_slice}

@router.get("/traceability_report/{mo}")
def get_traceability_flow(mo: str, start_date: str = Query(None), end_date: str = Query(None)):
    search_group = get_mo_group(clean_mo(mo))
    if not search_group:
        return {"status": "error", "message": "Invalid MO"}
        
    s_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date and start_date.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date and end_date.strip() not in ["", "null", "None"] else None

    jw_sho_agg, jw_tb_agg, ch_agg = {}, {}, {}

    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            
            if r["sho_qty"] > 0:
                sho_valid = True
                d = r["sho_date"]
                if (s_dt or e_dt):
                    if not d: sho_valid = False
                    elif s_dt and e_dt: sho_valid = (s_dt <= d <= e_dt)
                    elif s_dt: sho_valid = (d >= s_dt)
                    elif e_dt: sho_valid = (d <= e_dt)
                    
                if sho_valid:
                    if v_name not in jw_sho_agg: jw_sho_agg[v_name] = {"qty": 0, "dates": []}
                    jw_sho_agg[v_name]["qty"] += r["sho_qty"]
                    if d: jw_sho_agg[v_name]["dates"].append(d)
                    
            if r["tb_qty"] > 0:
                tb_valid = True
                d = r["tb_date"]
                if (s_dt or e_dt):
                    if not d: tb_valid = False
                    elif s_dt and e_dt: tb_valid = (s_dt <= d <= e_dt)
                    elif s_dt: tb_valid = (d >= s_dt)
                    elif e_dt: tb_valid = (d <= e_dt)
                    
                if tb_valid:
                    if v_name not in jw_tb_agg: jw_tb_agg[v_name] = {"qty": 0, "dates": []}
                    jw_tb_agg[v_name]["qty"] += r["tb_qty"]
                    if d: jw_tb_agg[v_name]["dates"].append(d)

    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            if r["ch_qty"] > 0:
                ch_valid = True
                d = r["ch_date"]
                if (s_dt or e_dt):
                    if not d: ch_valid = False
                    elif s_dt and e_dt: ch_valid = (s_dt <= d <= e_dt)
                    elif s_dt: ch_valid = (d >= s_dt)
                    elif e_dt: ch_valid = (d <= e_dt)
                    
                if ch_valid:
                    if v_name not in ch_agg: ch_agg[v_name] = {"qty": 0, "dates": []}
                    ch_agg[v_name]["qty"] += r["ch_qty"]
                    if d: ch_agg[v_name]["dates"].append(d)

    rows = []

    for v_name, data in jw_sho_agg.items():
        in_d = format_dt(min(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "SHO Department", 
            "variant": v_name, "in_date": in_d, "out_date": "-", 
            "qty": math.ceil(data["qty"]), "status": "Allocated"
        })
        
    for v_name, data in jw_tb_agg.items():
        out_d = format_dt(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Transit Buffer", 
            "variant": v_name, "in_date": "-", "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "In Transit"
        })

    for v_name, data in ch_agg.items():
        in_d = format_dt(min(data["dates"])) if data["dates"] else "-"
        out_d = format_dt(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Channel Section", 
            "variant": v_name, "in_date": in_d, "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "Completed"
        })

    return {"status": "success", "data": {"mo": search_group, "rows": rows}}
