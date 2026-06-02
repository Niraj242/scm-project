from fastapi import APIRouter, HTTPException, Query
import pandas as pd
import requests
import io
import threading
import time
import re
import math
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE, DATA ENGINE & THREADING STORAGE
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 5

# High-speed memory tables for fine-grained drilldown rendering
GLOBAL_JW_RECORDS = []
GLOBAL_CH_RECORDS = []

HTTP_SESSION = requests.Session()

# =========================================================
# UTILITY CLEANERS & LOGIC HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value):
        return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 4:
        return None
    return val

def get_mo_group(clean_mo_str):
    if clean_mo_str and len(clean_mo_str) >= 4:
        return clean_mo_str[:4]
    return clean_mo_str

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']:
            return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]:
            return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except:
        return None

def parse_product_details(prod_text):
    text = normalize_text(prod_text).upper()
    component = "IM" if "IM" in text or "IR" in text else ("OM" if "OM" in text or "OR" in text else "Assembly")
    base_product = text if text else "Gen Product"
    return base_product, component

def load_excel_sheets(url):
    try:
        resp = HTTP_SESSION.get(url, timeout=30)
        if resp.status_code != 200:
            return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        sheets = {}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"⚠️ Error reading sheet [{sheet}]: {e}")
        return sheets
    except Exception as e:
        print(f"❌ Failed to download workbook stream from {url}: {e}")
        return {}

# =========================================================
# CORE EXTRACTION PIPELINE
# =========================================================
def process_traceability_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED
    global GLOBAL_JW_RECORDS, GLOBAL_CH_RECORDS
    
    if IS_UPDATING:
        return
    
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING BACKGROUND TRACEABILITY PIPELINE SYNC...")

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        summary_aggregation = {}
        local_jw_collector = []
        local_ch_collector = []

        # ---------------------------------------------------------
        # 0. MAP PRIMARY GROUND-TRUTH RECORD MATRIX
        # ---------------------------------------------------------
        for sheet_name, df in mo_sheets.items():
            if "mo#" not in df.columns or "comp item" not in df.columns:
                continue
            
            pdiv_col = "pdiv" if "pdiv" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)
            
            for _, row in df.iterrows():
                if pdiv_col:
                    pdiv_val = normalize_text(row.get(pdiv_col)).upper()
                    if pdiv_val not in ["227D", "227T"]:
                        continue

                comp_item_str = normalize_text(row.get("comp item")).upper()
                if not comp_item_str.startswith(("IM", "OM")):
                    continue
                
                comp_type = "IM" if comp_item_str.startswith("IM") else "OM"
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo:
                    continue
                
                mo_group = get_mo_group(raw_mo)
                qty_req = clean_nan(row.get("qty req"))
                final_variant = normalize_text(row.get("finalvariant"))
                base_prod, _ = parse_product_details(final_variant)
                
                sum_key = (mo_group, base_prod, comp_type)
                if sum_key not in summary_aggregation:
                    summary_aggregation[sum_key] = {
                        "mo": mo_group, "base_product": base_prod, "final_variant": final_variant,
                        "component_type": comp_type, "qty_req": qty_req,
                        "sho_qty": 0.0, "sho_in_date": None,
                        "tb_qty": 0.0, "tb_out_date": None,
                        "ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None,
                    }
                else:
                    summary_aggregation[sum_key]["qty_req"] += qty_req

        # ---------------------------------------------------------
        # 1. PARSE JOBWORK REPORTS (SHO & Transit Buffer)
        # ---------------------------------------------------------
        for sheet_name, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns:
                continue

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: 
                    continue
                
                mo_group = get_mo_group(raw_mo)
                product_str = normalize_text(row.get("product"))
                base_prod, comp_type = parse_product_details(product_str)
                
                jw_challan_date = parse_date_safe(row.get("jw challan date"))
                last_challan_date = parse_date_safe(row.get("last challan date"))
                qty_approved = clean_nan(row.get("qty approved"))
                qty_returned = clean_nan(row.get("qty returned"))
                status = normalize_text(row.get("current status"))

                # Track down into raw lookup cache for deep drilldown
                local_jw_collector.append({
                    "mo_group": mo_group, "full_mo": raw_mo, "product": product_str,
                    "base_product": base_prod, "component_type": comp_type,
                    "jw_challan_date": jw_challan_date, "last_challan_date": last_challan_date,
                    "qty_approved": qty_approved, "qty_returned": qty_returned, "status": status
                })

                sum_key = (mo_group, base_prod, comp_type)
                if sum_key in summary_aggregation:
                    s_agg = summary_aggregation[sum_key]
                    s_agg["sho_qty"] += qty_approved
                    s_agg["tb_qty"] += qty_returned

                    if jw_challan_date:
                        s_agg["sho_in_date"] = min(s_agg["sho_in_date"], jw_challan_date) if s_agg["sho_in_date"] else jw_challan_date
                    if last_challan_date:
                        s_agg["tb_out_date"] = max(s_agg["tb_out_date"], last_challan_date) if s_agg["tb_out_date"] else last_challan_date
                else:
                    summary_aggregation[sum_key] = {
                        "mo": mo_group, "base_product": base_prod, "final_variant": product_str,
                        "component_type": comp_type, "qty_req": 0,
                        "sho_qty": qty_approved, "sho_in_date": jw_challan_date,
                        "tb_qty": qty_returned, "tb_out_date": last_challan_date,
                        "ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None,
                    }

        # ---------------------------------------------------------
        # 2. PARSE PRODUCTION CHANNELS WITH SUMMED MAXIMUMS
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_variant_maxes = {}

        for channel_name, df in all_channels.items():
            if "mo" not in df.columns:
                continue

            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            if not type_col:
                continue

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo:
                    continue
                
                mo_group = get_mo_group(raw_mo)
                prod_str = normalize_text(row.get(type_col))
                base_prod, comp_type = parse_product_details(prod_str)
                
                cumulative = clean_nan(row.get("cumulative production"))
                production = clean_nan(row.get("production"))
                date_val = parse_date_safe(row.get("date"))

                # Track down into raw channel memory store
                local_ch_collector.append({
                    "mo_group": mo_group, "full_mo": raw_mo, "channel": channel_name,
                    "product": prod_str, "base_product": base_prod, "component_type": comp_type,
                    "cumulative": cumulative, "production": production, "date": date_val
                })

                v_key = (mo_group, base_prod, prod_str)
                if v_key not in channel_variant_maxes:
                    channel_variant_maxes[v_key] = {"max_cum": 0.0, "min_date": None, "max_date": None}
                
                v_meta = channel_variant_maxes[v_key]
                if cumulative > v_meta["max_cum"]:
                    v_meta["max_cum"] = cumulative
                if date_val:
                    v_meta["min_date"] = min(v_meta["min_date"], date_val) if v_meta["min_date"] else date_val
                    v_meta["max_date"] = max(v_meta["max_date"], date_val) if v_meta["max_date"] else date_val

        family_channel_totals = {}
        for (mo_group, base_prod, prod_str), v_meta in channel_variant_maxes.items():
            f_key = (mo_group, base_prod)
            if f_key not in family_channel_totals:
                family_channel_totals[f_key] = {"ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None}
            
            f_meta = family_channel_totals[f_key]
            f_meta["ch_qty"] += v_meta["max_cum"]
            if v_meta["min_date"]:
                f_meta["ch_in_date"] = min(f_meta["ch_in_date"], v_meta["min_date"]) if f_meta["ch_in_date"] else v_meta["min_date"]
            if v_meta["max_date"]:
                f_meta["ch_out_date"] = max(f_meta["ch_out_date"], v_meta["max_date"]) if f_meta["ch_out_date"] else v_meta["max_date"]

        for (mo_group, base_prod), f_meta in family_channel_totals.items():
            for comp in ["IM", "OM"]:
                sum_key = (mo_group, base_prod, comp)
                if sum_key in summary_aggregation:
                    s_agg = summary_aggregation[sum_key]
                    s_agg["ch_qty"] = f_meta["ch_qty"]
                    s_agg["ch_in_date"] = f_meta["ch_in_date"]
                    s_agg["ch_out_date"] = f_meta["ch_out_date"]
                else:
                    summary_aggregation[sum_key] = {
                        "mo": mo_group, "base_product": base_prod, "final_variant": "Combined Family Channel Grouping",
                        "component_type": comp, "qty_req": 0,
                        "sho_qty": 0.0, "sho_in_date": None,
                        "tb_qty": 0.0, "tb_out_date": None,
                        "ch_qty": f_meta["ch_qty"], "ch_in_date": f_meta["ch_in_date"], "ch_out_date": f_meta["ch_out_date"],
                    }

        # ---------------------------------------------------------
        # 3. COMPILING GLOBAL DASHBOARD KPI MAPS
        # ---------------------------------------------------------
        compiled_summary = []
        for (mo_group, base_prod, comp_type), s_agg in summary_aggregation.items():
            if s_agg["sho_qty"] == 0 and s_agg["ch_qty"] == 0:
                calc_status = "Yet to Start"
            elif s_agg["ch_qty"] >= s_agg["sho_qty"] and s_agg["sho_qty"] > 0:
                calc_status = "Completed"
            else:
                calc_status = "In Process"

            compiled_summary.append({
                "mo": mo_group,
                "base_product": s_agg["base_product"],
                "final_variant": s_agg["final_variant"],
                "component_type": comp_type,
                "qty_req": int(s_agg["qty_req"]),
                "sho_qty": math.ceil(s_agg["sho_qty"]),
                "sho_in": str(s_agg["sho_in_date"]) if s_agg["sho_in_date"] else "-",
                "sho_out": "-",
                "tb_qty": math.ceil(s_agg["tb_qty"]),
                "tb_in": "-",
                "tb_out": str(s_agg["tb_out_date"]) if s_agg["tb_out_date"] else "-",
                "ch_qty": math.ceil(s_agg["ch_qty"]),
                "ch_in": str(s_agg["ch_in_date"]) if s_agg["ch_in_date"] else "-",
                "ch_out": str(s_agg["ch_out_date"]) if s_agg["ch_out_date"] else "-",
                "status": calc_status
            })

        compiled_summary.sort(key=lambda x: (x["mo"], x["base_product"], x["component_type"]))
        
        # Commit safely into memory variables
        GLOBAL_JW_RECORDS = local_jw_collector
        GLOBAL_CH_RECORDS = local_ch_collector
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        INITIALIZED = True
        print(f"[{datetime.now()}] TRACEABILITY MATRIX RE-CALCULATED SUCCESSFULLY.")

    except Exception as e:
        print(f"❌ PIPELINE ERROR GENERATING MATRICES: {str(e)}")
    finally:
        IS_UPDATING = False

def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

# =========================================================
# ROUTER API ENDPOINTS
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():
    if not INITIALIZED:
        return {"status": "initializing", "message": "Downloading production schemas...", "data": []}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_traceability_flow(mo: str):
    """
    Generates structured routing components mirroring the layout logic of the TBE module.
    SHO & TB stay aggregated at the variant level, while the Channel items split by Exact Single MO.
    """
    search_group = get_mo_group(clean_mo(mo))
    
    # Filter global memory tracking stores
    jw_filtered = [r for r in GLOBAL_JW_RECORDS if r["mo_group"] == search_group]
    ch_filtered = [r for r in GLOBAL_CH_RECORDS if r["mo_group"] == search_group]

    if not jw_filtered and not ch_filtered:
        raise HTTPException(status_code=404, detail=f"No matching trace history records for order prefix: '{mo}'")

    # Establish fallback string of unique full production order numbers
    unique_full_mos = sorted(list(set([str(r["full_mo"]) for r in jw_filtered if r.get("full_mo")])))
    mo_group_reference = ", ".join(unique_full_mos) if unique_full_mos else search_group

    sho_map = {}
    tb_map = {}
    ch_map = {}

    # Gather SHO & Transit Buffer rows (Grouped cleanly by Variant string)
    for r in jw_filtered:
        prod_name = r["product"]
        norm_key = str(prod_name).upper().replace("-", "").replace(" ", "")
        if not norm_key: 
            continue
        
        # Aggregate SHO
        if norm_key not in sho_map:
            sho_map[norm_key] = {"label": prod_name, "qty": 0.0, "dates": [], "status": r["status"]}
        sho_map[norm_key]["qty"] += r["qty_approved"]
        if r["jw_challan_date"]: 
            sho_map[norm_key]["dates"].append(r["jw_challan_date"])

        # Aggregate Transit Buffer
        if norm_key not in tb_map:
            tb_map[norm_key] = {"label": prod_name, "qty": 0.0, "dates": [], "status": r["status"]}
        tb_map[norm_key]["qty"] += r["qty_returned"]
        if r["last_challan_date"]: 
            tb_map[norm_key]["dates"].append(r["last_challan_date"])

    # Gather Channels (Grouped explicitly by Channel Name AND Variant AND Exact Single MO)
    for r in ch_filtered:
        prod_name = r["product"]
        exact_mo = r["full_mo"]
        ch_name = r["channel"]
        norm_v = str(prod_name).upper().replace("-", "").replace(" ", "")
        if not norm_v: 
            continue
        
        # Unique tuple key maps separate rows for distinct production orders on the same channel
        norm_key = (ch_name, norm_v, exact_mo)
        if norm_key not in ch_map:
            ch_map[norm_key] = {
                "channel_name": ch_name, "label": prod_name, 
                "exact_mo": exact_mo, "max_cum": 0.0, "dates": []
            }
        
        if r["cumulative"] > ch_map[norm_key]["max_cum"]:
            ch_map[norm_key]["max_cum"] = r["cumulative"]
        if r["date"]: 
            ch_map[norm_key]["dates"].append(r["date"])

    sequential_rows = []

    # Emit SHO rows
    for k, data in sho_map.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        sequential_rows.append({
            "mo_ref": mo_group_reference,
            "department": "SHO Department",
            "product": data["label"],
            "in_date": in_d,
            "out_date": "-",
            "qty": math.ceil(data["qty"]),
            "status": data["status"] if data["status"] else "Allocated"
        })

    # Emit Transit Buffer rows
    for k, data in tb_map.items():
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        sequential_rows.append({
            "mo_ref": mo_group_reference,
            "department": "Transit Buffer",
            "product": data["label"],
            "in_date": "-",
            "out_date": out_d,
            "qty": math.ceil(data["qty"]),
            "status": "In Transit"
        })

    # Emit Channel Section rows split by Exact Single Full MO
    for k, data in ch_map.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        sequential_rows.append({
            "mo_ref": data["exact_mo"],  # Displays exact single full MO
            "department": f"Channel Section ({data['channel_name']})",
            "product": data["label"],
            "in_date": in_d,
            "out_date": out_d,
            "qty": math.ceil(data["max_cum"]),
            "status": "Completed" if data["max_cum"] > 0 else "Running"
        })

    return {
        "status": "success",
        "data": {
            "mo": search_group,
            "rows": sequential_rows
        }
    }
