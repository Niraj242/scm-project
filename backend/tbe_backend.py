from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import math
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
# CLEANING & PARSING HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 2: return None
    return val

def get_mo_group(clean_mo_str):
    if clean_mo_str and len(clean_mo_str) >= 4: return clean_mo_str[:4]
    return clean_mo_str

def normalize_text(value):
    # No longer stripping "IM/OM" or other tags here. 
    # This keeps the exact name as it appears in your sheet.
    if pd.isna(value): return ""
    return str(value).strip().upper()

def clean_channel(value):
    if pd.isna(value): return ""
    return str(value).strip().upper().replace(" ", "")

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except: return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        return None if pd.isna(parsed) else parsed.date()
    except: return None

def download_excel(url):
    response = requests.get(url)
    if response.status_code != 200: raise Exception(f"Failed downloading excel from {url}")
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
            except Exception as e: print(f"Error reading sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"Failed to load workbook from {url}: {str(e)}")
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_tbe_dashboard_data():
    global MASTER_CACHE, FLOW_CACHE, LAST_REFRESH, IS_UPDATING
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        transit_buffer_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        # STEP 1: TARGET QUANTITY LOOKUP MAP
        target_qty_lookup = {}
        for _, df in mo_sheets.items():
            mo_col = next((c for c in ["mo#", "mo"] if c in df.columns), None)
            qty_col = next((c for c in ["qty req", "qty", "target qty"] if c in df.columns), None)
            if not mo_col or not qty_col: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get(mo_col))
                if raw_mo:
                    mo_grp = get_mo_group(raw_mo)
                    qty_val = clean_nan(row.get(qty_col))
                    target_qty_lookup[mo_grp] = target_qty_lookup.get(mo_grp, 0.0) + qty_val
                    target_qty_lookup[raw_mo] = target_qty_lookup.get(raw_mo, 0.0) + qty_val

        # STEP 2: PROCESS TRB & DGBB MASTERS
        tbe_aggregation = {}
        channel_timeline = []

        for sheet_dict in [trb_sheets, dgbb_sheets]:
            for _, df in sheet_dict.items():
                mo_col = next((c for c in ["mo", "mo#"] if c in df.columns), None)
                type_col = next((c for c in ["type", "product", "product variant"] if c in df.columns), None)
                channel_col = next((c for c in ["channel", "ch#", "channel no"] if c in df.columns), None)
                if not mo_col or not type_col: continue

                for _, row in df.iterrows():
                    raw_mo = clean_mo(row.get(mo_col))
                    if not raw_mo: continue

                    # USE EXACT PRODUCT NAME
                    raw_product = normalize_text(row.get(type_col))
                    ch_id = clean_channel(row.get(channel_col)) if channel_col else ""
                    row_date = parse_date_safe(row.get("date"))
                    cum_production = clean_nan(row.get("cumulative production"))

                    # AGGREGATION KEY USES RAW PRODUCT NAME
                    agg_key = (raw_mo, raw_product)
                    if agg_key not in tbe_aggregation:
                        tbe_aggregation[agg_key] = {
                            "mo": raw_mo,
                            "mo_group": get_mo_group(raw_mo),
                            "product_name": raw_product,
                            "qty_req": target_qty_lookup.get(raw_mo, target_qty_lookup.get(get_mo_group(raw_mo), 0.0)),
                            "tb_qty": 0.0, "tb_out": None,
                            "ch_qty": 0.0, "ch_in": None, "ch_out": None
                        }

                    meta = tbe_aggregation[agg_key]
                    if cum_production > meta["ch_qty"]:
                        meta["ch_qty"] = cum_production
                        if row_date: 
                            meta["ch_out"] = row_date
                            if meta["ch_in"] is None or row_date < meta["ch_in"]:
                                meta["ch_in"] = row_date

                    if ch_id and row_date:
                        channel_timeline.append({
                            "channel": ch_id,
                            "date": row_date,
                            "mo": raw_mo,
                            "product": raw_product
                        })

        # STEP 3: MAP TRANSIT BUFFER
        for _, df in transit_buffer_sheets.items():
            ch_col = next((c for c in ["ch#", "channel", "ch"] if c in df.columns), None)
            type_col = "type" if "type" in df.columns else None
            qty_col = "no of rings" if "no of rings" in df.columns else None
            date_col = "date" if "date" in df.columns else None
            if not ch_col or not type_col or not qty_col: continue

            for _, row in df.iterrows():
                tb_channel = clean_channel(row.get(ch_col))
                tb_product = normalize_text(row.get(type_col))
                tb_date = parse_date_safe(row.get(date_col))
                tb_qty = clean_nan(row.get(qty_col))

                if not tb_channel or tb_qty <= 0: continue

                # Match by Channel and Exact Product Name
                possible_matches = [x for x in channel_timeline if x["channel"] == tb_channel and x["product"] == tb_product]

                if possible_matches:
                    best_match = min(possible_matches, key=lambda x: abs((x["date"] - (tb_date or datetime.now().date())).days)) if tb_date else possible_matches[-1]
                    agg_key = (best_match["mo"], best_match["product"])
                    if agg_key in tbe_aggregation:
                        tbe_aggregation[agg_key]["tb_qty"] += tb_qty
                        if tb_date:
                            curr_out = tbe_aggregation[agg_key]["tb_out"]
                            if not curr_out or tb_date > curr_out:
                                tbe_aggregation[agg_key]["tb_out"] = tb_date

        # STEP 4: OUTPUT
        compiled_summary = []
        mo_flow_records = {}

        for _, meta in tbe_aggregation.items():
            record = {
                "mo": meta["mo"],
                "product_name": meta["product_name"],
                "qty_req": meta["qty_req"],
                "sho_qty": meta["ch_qty"],
                "tb_qty": meta["tb_qty"],
                "tb_out": str(meta["tb_out"]) if meta["tb_out"] else "-",
                "ch_qty": meta["ch_qty"],
                "ch_in": str(meta["ch_in"]) if meta["ch_in"] else "-",
                "ch_out": str(meta["ch_out"]) if meta["ch_out"] else "-",
                "status": "In Process" if meta["ch_qty"] > 0 and meta["tb_qty"] > 0 else "Completed"
            }
            compiled_summary.append(record)
            
            for lookup_key in [meta["mo"], meta["mo_group"]]:
                if lookup_key not in mo_flow_records: mo_flow_records[lookup_key] = {"mo": meta["mo"], "timeline": []}
                mo_flow_records[lookup_key]["timeline"].append(record)

        MASTER_CACHE = compiled_summary
        FLOW_CACHE = mo_flow_records
        LAST_REFRESH = datetime.now()

    except Exception as e: print(f"CRITICAL OVERHAUL ERROR: {str(e)}")
    finally: IS_UPDATING = False

def background_refresh_loop():
    while True:
        process_tbe_dashboard_data()
        time.sleep(CACHE_DURATION_MINUTES * 60)

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/traceability_all_mos")
def get_all_mos():
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    search_mo = clean_mo(mo)
    search_grp = get_mo_group(search_mo)
    if search_mo in FLOW_CACHE: return {"status": "success", "data": FLOW_CACHE[search_mo]}
    if search_grp in FLOW_CACHE: return {"status": "success", "data": FLOW_CACHE[search_grp]}
    raise HTTPException(status_code=404, detail="Not found")
