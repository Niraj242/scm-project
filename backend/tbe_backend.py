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

def extract_ring_type(product_text):
    text = normalize_text(product_text)
    if "IM" in text or "IR" in text: return "IM"
    return "OM"

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

        # STEP 2: PROCESS TRB & DGBB MASTERS (Build Order Base & Channel Timeline)
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

                    variant_raw = normalize_text(row.get(type_col))
                    comp_type = extract_ring_type(variant_raw)
                    # Isolate exact family by stripping the IM/OM tags
                    base_variant = variant_raw.replace("IM", "").replace("IR", "").replace("OM", "").replace("OR", "").strip()

                    ch_id = clean_channel(row.get(channel_col)) if channel_col else ""
                    row_date = parse_date_safe(row.get("date"))
                    cum_production = clean_nan(row.get("cumulative production"))

                    # Ensure MO + Family + Type exists in aggregation base
                    agg_key = (raw_mo, base_variant, comp_type)
                    if agg_key not in tbe_aggregation:
                        tbe_aggregation[agg_key] = {
                            "mo": raw_mo,
                            "mo_group": get_mo_group(raw_mo),
                            "final_variant": base_variant,
                            "component_type": comp_type,
                            "qty_req": target_qty_lookup.get(raw_mo, target_qty_lookup.get(get_mo_group(raw_mo), 0.0)),
                            "sho_qty": 0.0, "sho_in": None,
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

                    # Build a searchable timeline for the Transit Buffer to hook into
                    if ch_id and row_date:
                        channel_timeline.append({
                            "channel": ch_id,
                            "date": row_date,
                            "mo": raw_mo,
                            "base_variant": base_variant,
                            "comp_type": comp_type
                        })

        # STEP 3: MAP TRANSIT BUFFER USING CHANNEL + DATE PROXIMITY
        for _, df in transit_buffer_sheets.items():
            ch_col = next((c for c in ["ch#", "channel", "ch"] if c in df.columns), None)
            type_col = "type" if "type" in df.columns else None
            qty_col = "no of rings" if "no of rings" in df.columns else None
            date_col = "date" if "date" in df.columns else None
            if not ch_col or not type_col or not qty_col: continue

            for _, row in df.iterrows():
                tb_channel = clean_channel(row.get(ch_col))
                tb_type_raw = normalize_text(row.get(type_col))
                tb_comp = extract_ring_type(tb_type_raw)
                tb_date = parse_date_safe(row.get(date_col))
                tb_qty = clean_nan(row.get(qty_col))

                if not tb_channel or tb_qty <= 0: continue

                # Look for matching channel and component type in the timeline
                possible_matches = [x for x in channel_timeline if x["channel"] == tb_channel and x["comp_type"] == tb_comp]

                best_match = None
                if possible_matches:
                    if tb_date:
                        # Find the master record with the closest date to the transit buffer date
                        best_match = min(possible_matches, key=lambda x: abs((x["date"] - tb_date).days))
                    else:
                        best_match = possible_matches[-1] # fallback to most recent

                if best_match:
                    agg_key = (best_match["mo"], best_match["base_variant"], tb_comp)
                    if agg_key in tbe_aggregation:
                        tbe_aggregation[agg_key]["tb_qty"] += tb_qty
                        if tb_date:
                            curr_out = tbe_aggregation[agg_key]["tb_out"]
                            if not curr_out or tb_date > curr_out:
                                tbe_aggregation[agg_key]["tb_out"] = tb_date

        # STEP 4: OUTPUT CLEAN UNIFIED DATA AND PREPARE DRILLDOWN
        compiled_summary = []
        mo_flow_records = {}

        for _, meta in tbe_aggregation.items():
            if meta["ch_qty"] == 0 and meta["tb_qty"] == 0:
                tracking_status = "Yet to Start"
            elif meta["ch_qty"] > 0 and meta["tb_qty"] == 0:
                tracking_status = "Completed"
            else:
                tracking_status = "In Process"

            record = {
                "mo": meta["mo"],
                "final_variant": meta["final_variant"],
                "qty_req": meta["qty_req"],
                "component_type": meta["component_type"],
                "sho_qty": meta["ch_qty"],
                "sho_in": "-",
                "tb_qty": meta["tb_qty"],
                "tb_out": str(meta["tb_out"]) if meta["tb_out"] else "-",
                "ch_qty": meta["ch_qty"],
                "ch_in": str(meta["ch_in"]) if meta["ch_in"] else "-",
                "ch_out": str(meta["ch_out"]) if meta["ch_out"] else "-",
                "status": tracking_status
            }
            compiled_summary.append(record)

            # Double index to guarantee frontend click handler always matches
            for lookup_key in [meta["mo"], meta["mo_group"]]:
                if lookup_key and lookup_key != "-":
                    if lookup_key not in mo_flow_records:
                        mo_flow_records[lookup_key] = {"mo": meta["mo"], "timeline": []}
                    if record not in mo_flow_records[lookup_key]["timeline"]:
                        mo_flow_records[lookup_key]["timeline"].append(record)

        compiled_summary.sort(key=lambda x: (x["mo"], x["final_variant"]))
        
        MASTER_CACHE = compiled_summary
        FLOW_CACHE = mo_flow_records
        LAST_REFRESH = datetime.now()

    except Exception as e: print(f"CRITICAL OVERHAUL ERROR: {str(e)}")
    finally: IS_UPDATING = False

def background_refresh_loop():
    process_tbe_dashboard_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_dashboard_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

@router.get("/traceability_all_mos")
def get_all_mos():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {"status": "initializing", "message": "Loading Data...", "data": []}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    # Safe lookup via standard clean values or groups
    search_mo = clean_mo(mo)
    search_grp = get_mo_group(search_mo)
    
    if search_mo in FLOW_CACHE:
        return {"status": "success", "last_updated": str(LAST_REFRESH), "data": FLOW_CACHE[search_mo]}
    elif search_grp in FLOW_CACHE:
        return {"status": "success", "last_updated": str(LAST_REFRESH), "data": FLOW_CACHE[search_grp]}
        
    raise HTTPException(status_code=404, detail=f"Order allocation tracking details missing for reference: '{mo}'")
