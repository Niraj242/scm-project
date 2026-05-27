from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import re
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
FLOW_CACHE = {}
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# SECURITY, CLEANING & PARSING HELPERS
# =========================================================
def extract_mo_prefix(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper().replace(" ", "")[:4]

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-']:
            return 0
    except:
        pass
    try:
        return float(value)
    except:
        return 0

def parse_date_safe(value):
    try:
        if pd.isna(value):
            return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except:
        return None

def parse_product_details(prod_text):
    """
    Extracts base bearing model (e.g., 6007) and component type (IM/OM)
    Filters variations like /C3, -2RS1, (Exp)
    """
    text = normalize_text(prod_text).upper()
    component = "IM" if "IM" in text else ("OM" if "OM" in text else "Assembly")
    
    # Match first 4-5 digit sequence for bearing base identity
    match = re.search(r'\d{4,5}', text)
    base_product = match.group(0) if match else "Gen Product"
    return base_product, component

def download_excel(url):
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed downloading excel from {url}")
    return io.BytesIO(response.content)

def load_excel_sheets(url):
    try:
        excel_data = download_excel(url)
        xls = pd.ExcelFile(excel_data)
        sheets = {}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"Error reading sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"Failed to load workbook from {url}: {str(e)}")
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_traceability_data():
    global MASTER_CACHE, FLOW_CACHE, LAST_REFRESH, IS_UPDATING
    
    if IS_UPDATING:
        return
    
    # Thread block to prevent double execution triggers
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING BACKGROUND EXCEL CACHE REFRESH...")

    try:
        # Load all target data sheets (including the new ground-truth MO sheet)
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        mo_flow_records = {}
        summary_aggregation = {}

        # ---------------------------------------------------------
        # 0. INITIALIZE SUMMARY MATRIX FROM GROUND-TRUTH MO DATA
        # ---------------------------------------------------------
        for sheet_name, df in mo_sheets.items():
            if "mo#" not in df.columns or "comp item" not in df.columns:
                continue
            
            for _, row in df.iterrows():
                comp_item_str = normalize_text(row.get("comp item")).upper()
                
                # Rule 1 & 2: Strict filter – process ONLY entries starting with IM or OM
                if not comp_item_str.startswith(("IM", "OM")):
                    continue
                
                comp_type = "IM" if comp_item_str.startswith("IM") else "OM"
                raw_mo = normalize_text(row.get("mo#"))
                prefix = extract_mo_prefix(raw_mo)
                if not prefix:
                    continue
                
                # Rule 3: Extract Qty Req and FinalVariant metadata while discarding Store Channels
                qty_req = clean_nan(row.get("qty req"))
                final_variant = normalize_text(row.get("finalvariant"))
                base_prod, _ = parse_product_details(final_variant)
                
                # Setup master anchor mapping composite key
                sum_key = (prefix, raw_mo, comp_type)
                if sum_key not in summary_aggregation:
                    summary_aggregation[sum_key] = {
                        "full_mo": raw_mo,
                        "base_product": base_prod,
                        "final_variant": final_variant,
                        "component_type": comp_type,
                        "qty_req": qty_req,
                        "sho_qty": 0.0, "sho_in_date": None, "sho_out_date": None,
                        "tb_qty": 0.0, "tb_in_date": None, "tb_out_date": None,
                        "ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None,
                    }
                else:
                    # Accumulate requirements if variant splits exist across rows
                    summary_aggregation[sum_key]["qty_req"] += qty_req

        # ---------------------------------------------------------
        # 1. PROCESS JOBWORK REPORT (SHO & Transit Buffer)
        # ---------------------------------------------------------
        for sheet_name, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns:
                continue

            for _, row in df.iterrows():
                raw_mo = row.get("po / pr no.")
                prefix = extract_mo_prefix(raw_mo)
                if not prefix: 
                    continue

                if prefix not in mo_flow_records:
                    mo_flow_records[prefix] = {"full_mo": normalize_text(raw_mo), "rows": []}

                product_raw = row.get("product")
                product_str = normalize_text(product_raw)
                base_prod, comp_type = parse_product_details(product_str)
                
                jw_challan_date = parse_date_safe(row.get("jw challan date"))
                last_challan_date = parse_date_safe(row.get("last challan date"))
                qty_approved = clean_nan(row.get("qty approved"))
                qty_returned = clean_nan(row.get("qty returned"))
                status = normalize_text(row.get("current status"))

                mo_flow_records[prefix]["rows"].append({
                    "department": "SHO", "product": product_str, "in_date": "",
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_approved, "qty_out": qty_returned, "status": status
                })
                mo_flow_records[prefix]["rows"].append({
                    "department": "Transit Buffer", "product": product_str, 
                    "in_date": str(jw_challan_date) if jw_challan_date else "",
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_returned, "qty_out": qty_returned, "status": status
                })

                # Rule 4: Match to the existing ground-truth framework entries using 4-letter context
                matched_to_seed = False
                for sum_key, s_agg in summary_aggregation.items():
                    # sum_key format: (prefix, full_mo, comp_type)
                    if sum_key[0] == prefix and sum_key[2] == comp_type:
                        s_agg["sho_qty"] += qty_approved
                        s_agg["tb_qty"] += qty_returned

                        if last_challan_date:
                            s_agg["sho_out_date"] = max(s_agg["sho_out_date"], last_challan_date) if s_agg["sho_out_date"] else last_challan_date
                            s_agg["tb_out_date"] = max(s_agg["tb_out_date"], last_challan_date) if s_agg["tb_out_date"] else last_challan_date
                        if jw_challan_date:
                            s_agg["sho_in_date"] = min(s_agg["sho_in_date"], jw_challan_date) if s_agg["sho_in_date"] else jw_challan_date
                            s_agg["tb_in_date"] = min(s_agg["tb_in_date"], jw_challan_date) if s_agg["tb_in_date"] else jw_challan_date
                        matched_to_seed = True

                # Fallback safeguard structure for historic entries missing from the new MO sheet
                if not matched_to_seed:
                    fallback_mo = normalize_text(raw_mo)
                    fallback_key = (prefix, fallback_mo, comp_type)
                    if fallback_key not in summary_aggregation:
                        summary_aggregation[fallback_key] = {
                            "full_mo": fallback_mo, "base_product": base_prod, "final_variant": "",
                            "component_type": comp_type, "qty_req": 0,
                            "sho_qty": 0.0, "sho_in_date": None, "sho_out_date": None,
                            "tb_qty": 0.0, "tb_in_date": None, "tb_out_date": None,
                            "ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None,
                        }
                    s_agg = summary_aggregation[fallback_key]
                    s_agg["sho_qty"] += qty_approved
                    s_agg["tb_qty"] += qty_returned
                    if last_challan_date:
                        s_agg["sho_out_date"] = max(s_agg["sho_out_date"], last_challan_date) if s_agg["sho_out_date"] else last_challan_date
                    if jw_challan_date:
                        s_agg["sho_in_date"] = min(s_agg["sho_in_date"], jw_challan_date) if s_agg["sho_in_date"] else jw_challan_date

        # ---------------------------------------------------------
        # 2. PROCESS CHANNELS WITH SUMMED VARIANTS LOGIC
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_variant_maxes = {}

        for channel_name, df in all_channels.items():
            if "mo" not in df.columns:
                continue

            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)

            for _, row in df.iterrows():
                raw_mo = row.get("mo")
                prefix = extract_mo_prefix(raw_mo)
                if not prefix:
                    continue

                prod_raw = row.get(type_col)
                prod_str = normalize_text(prod_raw)
                base_prod, _ = parse_product_details(prod_str)
                
                cumulative = clean_nan(row.get("cumulative production"))
                production = clean_nan(row.get("production"))
                date_val = parse_date_safe(row.get("date"))

                if prefix not in mo_flow_records:
                    mo_flow_records[prefix] = {"full_mo": normalize_text(raw_mo), "rows": []}

                mo_flow_records[prefix]["rows"].append({
                    "department": channel_name, "product": prod_str,
                    "in_date": str(date_val) if production > 0 and production == cumulative else "",
                    "out_date": str(date_val) if cumulative > 0 else "",
                    "qty_in": cumulative, "qty_out": cumulative, "status": "Completed" if cumulative > 0 else "Running"
                })

                v_key = (prefix, base_prod, prod_str)
                if v_key not in channel_variant_maxes:
                    channel_variant_maxes[v_key] = {"max_cum": 0.0, "min_date": None, "max_date": None, "raw_mo": normalize_text(raw_mo)}
                
                v_meta = channel_variant_maxes[v_key]
                if cumulative > v_meta["max_cum"]:
                    v_meta["max_cum"] = cumulative
                if date_val:
                    v_meta["min_date"] = min(v_meta["min_date"], date_val) if v_meta["min_date"] else date_val
                    v_meta["max_date"] = max(v_meta["max_date"], date_val) if v_meta["max_date"] else date_val

        # Map channel totals back across IM & OM component rows using cohesive matching parameters
        for (prefix, base_prod, prod_str), v_meta in channel_variant_maxes.items():
            for comp in ["IM", "OM"]:
                matched_to_seed = False
                for sum_key, s_agg in summary_aggregation.items():
                    # Cohesion logic rule: Group 4-letter channel matches inside parent matrix rows safely
                    if sum_key[0] == prefix and sum_key[2] == comp:
                        s_agg["ch_qty"] += v_meta["max_cum"]
                        if v_meta["min_date"]:
                            s_agg["ch_in_date"] = min(s_agg["ch_in_date"], v_meta["min_date"]) if s_agg["ch_in_date"] else v_meta["min_date"]
                        if v_meta["max_date"]:
                            s_agg["ch_out_date"] = max(s_agg["ch_out_date"], v_meta["max_date"]) if s_agg["ch_out_date"] else v_meta["max_date"]
                        matched_to_seed = True

                if not matched_to_seed:
                    fallback_mo = v_meta["raw_mo"]
                    fallback_key = (prefix, fallback_mo, comp)
                    if fallback_key not in summary_aggregation:
                        summary_aggregation[fallback_key] = {
                            "full_mo": fallback_mo, "base_product": base_prod, "final_variant": prod_str,
                            "component_type": comp, "qty_req": 0,
                            "sho_qty": 0.0, "sho_in_date": None, "sho_out_date": None,
                            "tb_qty": 0.0, "tb_in_date": None, "tb_out_date": None,
                            "ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None,
                        }
                    s_agg = summary_aggregation[fallback_key]
                    s_agg["ch_qty"] += v_meta["max_cum"]
                    if v_meta["min_date"]:
                        s_agg["ch_in_date"] = min(s_agg["ch_in_date"], v_meta["min_date"]) if s_agg["ch_in_date"] else v_meta["min_date"]

        # ---------------------------------------------------------
        # 3. COMPILING FINAL CACHE DATA FRAMES & ENFORCING ADJACENCY
        # ---------------------------------------------------------
        compiled_summary = []
        for (prefix, full_mo, comp_type), s_agg in summary_aggregation.items():
            if s_agg["sho_qty"] == 0 and s_agg["ch_qty"] == 0:
                calc_status = "Yet to Start"
            elif s_agg["ch_qty"] >= s_agg["sho_qty"] and s_agg["sho_qty"] > 0:
                calc_status = "Completed"
            else:
                calc_status = "In Process"

            compiled_summary.append({
                "mo": full_mo,
                "prefix": prefix,
                "base_product": s_agg["base_product"],
                "final_variant": s_agg["final_variant"],
                "component_type": comp_type,
                "qty_req": int(s_agg["qty_req"]),
                "sho_qty": s_agg["sho_qty"],
                "sho_in": str(s_agg["sho_in_date"]) if s_agg["sho_in_date"] else "-",
                "sho_out": str(s_agg["sho_out_date"]) if s_agg["sho_out_date"] else "-",
                "tb_qty": s_agg["tb_qty"],
                "tb_in": str(s_agg["tb_in_date"]) if s_agg["tb_in_date"] else "-",
                "tb_out": str(s_agg["tb_out_date"]) if s_agg["tb_out_date"] else "-",
                "ch_qty": s_agg["ch_qty"],
                "ch_in": str(s_agg["ch_in_date"]) if s_agg["ch_in_date"] else "-",
                "ch_out": str(s_agg["ch_out_date"]) if s_agg["ch_out_date"] else "-",
                "status": calc_status
            })

        # CRITICAL LAYOUT SORT: Alphabetically sorts so IM runs immediately before OM 
        # back-to-back for the exact same parent 7-letter Manufacturing Order.
        compiled_summary.sort(key=lambda x: (x["prefix"], x["mo"], x["component_type"]))
        
        MASTER_CACHE = compiled_summary
        
        new_flow = {}
        for pfx, dataset in mo_flow_records.items():
            new_flow[pfx] = {"mo": dataset["full_mo"], "flow_data": dataset["rows"]}
        FLOW_CACHE = new_flow
        
        LAST_REFRESH = datetime.now()
        print(f"[{datetime.now()}] PIPELINE SYNCHRONIZED. CACHE INSTANCED.")

    except Exception as e:
        print(f"CRITICAL DATA ENGINE THREAD ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

# Background Daemon initialization
def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

# =========================================================
# ROUTER API SERVICE ENDPOINTS
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {
            "status": "initializing",
            "message": "System maps are being prepared. Please hold...",
            "data": []
        }
    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": MASTER_CACHE
    }

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    search_prefix = extract_mo_prefix(mo)
    if search_prefix in FLOW_CACHE:
        return {
            "status": "success",
            "last_updated": str(LAST_REFRESH),
            "data": FLOW_CACHE[search_prefix]
        }
    raise HTTPException(status_code=404, detail=f"No details tracked for variant parameters: '{mo}'")
