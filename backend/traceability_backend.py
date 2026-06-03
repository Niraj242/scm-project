from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import math
import re
from datetime import datetime
from settings import settings

router = APIRouter()

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 5

GLOBAL_RAW_RECORDS = {"mo_data": [], "jw_data": [], "ch_data": []}
HTTP_SESSION = requests.Session()

def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "")
    if val.endswith(".0"): 
        val = val[:-2]
    if val in ["NAN", "-", "...", "", "NAT", "NONE"]: 
        return None
    return val

def get_mo_group(clean_mo_str):
    if not clean_mo_str: return clean_mo_str
    # Restored Original Grouping: Match numeric MOs, or group by first 4 characters (e.g. M0QQ)
    match = re.match(r'^(\d{4,})', clean_mo_str)
    return match.group(1) if match else clean_mo_str[:4] if len(clean_mo_str) >= 4 else clean_mo_str

def clean_family_name(text):
    if pd.isna(text) or str(text).strip().upper() in ["NAN", "NONE", "", "GENERIC PRODUCT"]:
        return "Unknown Bearing"
    
    t = str(text)
    
    # 1. Clean attached modifiers (e.g. 6007/NormalIM -> 6007/Normal)
    t = re.sub(r'(?i)NormalIM', 'Normal', t)
    t = re.sub(r'(?i)NormalOM', 'Normal', t)
    
    # 2. Clean prefixes/suffixes directly touching numbers (IM6007 -> 6007, 6007IM -> 6007)
    t = re.sub(r'(?i)^IM(?=\d)', '', t)
    t = re.sub(r'(?i)^OM(?=\d)', '', t)
    t = re.sub(r'(?i)(?<=\d)IM$', '', t)
    t = re.sub(r'(?i)(?<=\d)OM$', '', t)
    
    # 3. Clean standalone indicator words
    t = re.sub(r'(?i)\b(?:IM|OM|INNER|OUTER)\b', '', t)
    
    # Clean up any leftover punctuation at the ends
    t = t.strip(' /-_')
    return t if t else "Unknown Bearing"

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        return parsed.date() if not pd.isna(parsed) else None
    except:
        return None

def determine_component(text):
    text = str(text).strip().upper()
    if "OM" in text or "OUTER" in text: return "OM"
    return "IM" 

def load_excel_sheets(url):
    try:
        resp = HTTP_SESSION.get(url, timeout=30)
        if resp.status_code != 200: return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        sheets = {}
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df.columns = [str(c).strip().lower() for c in df.columns]
            sheets[sheet] = df
        return sheets
    except:
        return {}

def ensure_mo_in_summary(summary_map, mo_group, potential_family="Unknown Bearing"):
    if mo_group not in summary_map:
        summary_map[mo_group] = {
            "mo": mo_group, 
            "base_product": potential_family, 
            "ch_qty": 0.0, 
            "ch_date_max": None,
            "components": {
                "IM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"},
                "OM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"}
            }
        }
    else:
        if potential_family != "Unknown Bearing" and summary_map[mo_group]["base_product"] == "Unknown Bearing":
            summary_map[mo_group]["base_product"] = potential_family
            
    return summary_map[mo_group]

def process_traceability_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_RAW_RECORDS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        summary_map = {}
        raw_mo_data = []
        raw_jw_data = []
        raw_ch_data = []

        # 1. MO Data
        for _, df in mo_sheets.items():
            if "mo#" not in df.columns: continue
            
            if "pdiv" in df.columns:
                df["pdiv"] = df["pdiv"].fillna("").astype(str).str.strip().str.upper()
                df = df[df["pdiv"].isin(["227D", "227T"])]

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                qty_req = clean_nan(row.get("qty req") if "qty req" in df.columns else 0)
                
                final_variant = clean_family_name(row.get("finalvariant"))
                comp_raw = row.get("comp item") if "comp item" in df.columns else ""
                comp_type = determine_component(comp_raw)
                
                raw_mo_data.append({"mo_group": mo_group, "variant": final_variant, "comp_type": comp_type, "qty_req": qty_req})

                data = ensure_mo_in_summary(summary_map, mo_group, final_variant)
                data["components"][comp_type]["qty_req"] += qty_req

        # 2. JobWork Data
        for _, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                raw_product = row.get("product") if "product" in df.columns else ""
                
                variant = clean_family_name(raw_product)
                comp_type = determine_component(raw_product)

                sho_qty = clean_nan(row.get("qty approved") if "qty approved" in df.columns else 0)
                tb_qty = clean_nan(row.get("qty returned") if "qty returned" in df.columns else 0)
                sho_date = parse_date_safe(row.get("jw challan date") if "jw challan date" in df.columns else None)
                tb_date = parse_date_safe(row.get("last challan date") if "last challan date" in df.columns else None)

                raw_jw_data.append({
                    "mo_group": mo_group, "variant": variant, "comp_type": comp_type,
                    "sho_qty": sho_qty, "tb_qty": tb_qty, "sho_date": sho_date, "tb_date": tb_date
                })

                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                data["components"][comp_type]["sho"] += sho_qty
                data["components"][comp_type]["tb"] += tb_qty
                if sho_date: data["components"][comp_type]["sho_d"] = str(sho_date)
                if tb_date: data["components"][comp_type]["tb_d"] = str(tb_date)

        # 3. Channel Data 
        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            if "mo" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant = clean_family_name(row.get(type_col))
                ch_qty = clean_nan(row.get("production") if "production" in df.columns else 0)
                ch_date = parse_date_safe(row.get("date") if "date" in df.columns else None)

                raw_ch_data.append({"mo_group": mo_group, "variant": variant, "ch_qty": ch_qty, "ch_date": ch_date})

                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                data["ch_qty"] += ch_qty
                
                if ch_date:
                    if not data["ch_date_max"] or ch_date > data["ch_date_max"]:
                        data["ch_date_max"] = ch_date

        compiled_summary = []
        for mo, data in summary_map.items():
            im = data["components"]["IM"]
            om = data["components"]["OM"]
            req = max(im["qty_req"], om["qty_req"])
            
            status = "Completed" if (data["ch_qty"] >= req and req > 0) else ("In Process" if (im["sho"] > 0 or om["sho"] > 0) else "Yet to Start")
            latest_ch_date = str(data["ch_date_max"]) if data["ch_date_max"] else "-"

            if im["qty_req"] > 0 or im["sho"] > 0 or data["ch_qty"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "IM",
                    "qty_req": math.ceil(im["qty_req"]), "sho_qty": math.ceil(im["sho"]), "sho_date": im["sho_d"],
                    "tb_qty": math.ceil(im["tb"]), "tb_date": im["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": latest_ch_date, "status": status
                })
            
            if om["qty_req"] > 0 or om["sho"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "OM",
                    "qty_req": math.ceil(om["qty_req"]), "sho_qty": math.ceil(om["sho"]), "sho_date": om["sho_d"],
                    "tb_qty": math.ceil(om["tb"]), "tb_date": om["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": latest_ch_date, "status": status
                })

        compiled_summary.sort(key=lambda x: (x["mo"], x["component"]))
        MASTER_CACHE = compiled_summary
        GLOBAL_RAW_RECORDS = {"mo_data": raw_mo_data, "jw_data": raw_jw_data, "ch_data": raw_ch_data}
        LAST_REFRESH = datetime.now()
        INITIALIZED = True

    except Exception as e:
        print(f"❌ PIPELINE ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/traceability_all_mos")
def get_all_mos():
    if not INITIALIZED:
        return {"status": "initializing", "data": []}
    return {"status": "success", "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_traceability_flow(mo: str):
    search_group = get_mo_group(clean_mo(mo))
    
    # Dictionaries to aggregate Variant logs cleanly
    jw_sho_agg, jw_tb_agg, ch_agg = {}, {}, {}

    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            
            if r["sho_qty"] > 0:
                if v_name not in jw_sho_agg: jw_sho_agg[v_name] = {"qty": 0, "dates": []}
                jw_sho_agg[v_name]["qty"] += r["sho_qty"]
                if r["sho_date"]: jw_sho_agg[v_name]["dates"].append(r["sho_date"])
                
            if r["tb_qty"] > 0:
                if v_name not in jw_tb_agg: jw_tb_agg[v_name] = {"qty": 0, "dates": []}
                jw_tb_agg[v_name]["qty"] += r["tb_qty"]
                if r["tb_date"]: jw_tb_agg[v_name]["dates"].append(r["tb_date"])

    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            if r["ch_qty"] > 0:
                if v_name not in ch_agg: ch_agg[v_name] = {"qty": 0, "dates": []}
                ch_agg[v_name]["qty"] += r["ch_qty"]
                if r["ch_date"]: ch_agg[v_name]["dates"].append(r["ch_date"])

    rows = []

    # Format Jobwork SHO Rows
    for v_name, data in jw_sho_agg.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "SHO Department", 
            "variant": v_name, "in_date": in_d, "out_date": "-", 
            "qty": math.ceil(data["qty"]), "status": "Allocated"
        })
        
    # Format Jobwork Transit Buffer Rows
    for v_name, data in jw_tb_agg.items():
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Transit Buffer", 
            "variant": v_name, "in_date": "-", "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "In Transit"
        })

    # Format Channel Rows (Single row per variant, displaying Start and End Date)
    for v_name, data in ch_agg.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Channel Section", 
            "variant": v_name, "in_date": in_d, "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "Completed"
        })

    return {"status": "success", "data": {"mo": search_group, "rows": rows}}
