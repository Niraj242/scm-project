from fastapi import APIRouter, Query
import pandas as pd
import requests
import io
import threading
import time
import re
import math
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False  
CACHE_DURATION_MINUTES = 5

GLOBAL_CH_ROWS = []
GLOBAL_TB_ROWS = []
GLOBAL_SHO_ROWS = []

FAM_REGEX = re.compile(r'(\d{3,5})')
PREFIX_REGEX = re.compile(r'^(CH-|CH\.|CH|CHANNEL-|CHANNEL|SHEET-|SHEET)')
NUM_REGEX = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')

def format_dt(dt):
    if dt and pd.notna(dt): return dt.strftime("%d-%m-%Y")
    return "-"

def safe_ceil(value):
    if pd.isna(value) or value is None: return 0
    try: return math.ceil(float(value))
    except: return 0

# --- ANTI-FLIP BULLETPROOF DATE PARSER ---
def strict_dd_mm_yyyy(value):
    if pd.isna(value) or value is None: return None
    
    # Extract just the date segment to prevent timestamp mixing
    val_str = str(value).strip().split()[0]
    if val_str.lower() in ["nan", "nat", "", "-", "none"]: return None
    
    # Standardize all delimiters to dashes
    val_str = val_str.replace("/", "-").replace(".", "-")
    parts = val_str.split("-")
    
    try:
        if len(parts) == 3:
            if len(parts[0]) == 4: # Standard YYYY-MM-DD
                y = int(parts[0])
                m = int(parts[1])
                d = int(parts[2])
            elif len(parts[2]) == 4 or len(parts[2]) == 2: # Rigid DD-MM-YYYY forcing
                d = int(parts[0])
                m = int(parts[1])
                y = int(parts[2])
                if y < 100: y += 2000
            else:
                d = int(parts[0])
                m = int(parts[1])
                y = int(parts[2])
            return datetime(y, m, d).date()
    except:
        pass
        
    if isinstance(value, (datetime, pd.Timestamp)): 
        return value.date()
    return None

def parse_family_and_type(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", ""]: return "UNKNOWN", "ASSEMBLY"
    r_type = "ASSEMBLY"
    if "INNER" in text or "IM" in text or "IR" in text: r_type = "IM"
    elif "OUTER" in text or "OM" in text or "OR" in text: r_type = "OM"
    
    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    if "BT" in text: base = f"BT-{base}"
    elif "BB" in text: base = f"BB-{base}"
    return base, r_type

def normalize_channel(value, force_t_prefix=False):
    if pd.isna(value): return ""
    val_str = str(value).strip().upper()
    is_explicit_t = val_str.startswith("T")
    val_str = PREFIX_REGEX.sub('', val_str).strip()
    if val_str.startswith("T"):
        is_explicit_t = True
        val_str = val_str[1:]
    val_str = val_str.replace("-", "").replace(" ", "")
    if val_str.endswith(".0"): val_str = val_str[:-2]
    cleaned = val_str.lstrip("0")
    if not cleaned: cleaned = "0"
    if force_t_prefix or is_explicit_t: return f"T{cleaned}"
    return cleaned

def clean_nan(value):
    if pd.isna(value): return 0.0
    val_str = str(value)
    match = NUM_REGEX.search(val_str.replace(',', ''))
    if match: return float(match.group())
    return 0.0

# --- POSITION-BASED COLUMN SEARCH ENGINE ---
# Looks at headers AND row cells down to index 20 to find where data lives
def locate_column_idx(df, keywords):
    for idx, col in enumerate(df.columns):
        c_clean = str(col).lower().replace(" ", "").replace("#", "").replace("_", "")
        for kw in keywords:
            if kw in c_clean: return idx
            
    for r_idx in range(min(20, len(df))):
        row_vals = [str(x).lower().replace(" ", "").replace("#", "").replace("_", "") for x in df.iloc[r_idx].values]
        for c_idx, val in enumerate(row_vals):
            for kw in keywords:
                if kw == val or (len(kw) > 2 and kw in val):
                    return c_idx
    return None

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        try: xls = pd.ExcelFile(content, engine='calamine')
        except: xls = pd.ExcelFile(content, engine='openpyxl')
        return {sheet_name: xls.parse(sheet_name) for sheet_name in xls.sheet_names}
    except Exception as e:
        print(f"Excel load error for {url}: {e}")
        return {}

def process_master_sheets(sheets_dict, is_trb):
    ch_list = []
    for sheet_name, df in sheets_dict.items():
        if df.empty: continue
        clean_name = str(sheet_name).strip().upper()
        if not re.match(r'^(T|CH)[-\s]*\d+', clean_name): continue
            
        ch_idx = locate_column_idx(df, ["channelno", "channel", "machineno", "line", "ch"])
        mo_idx = locate_column_idx(df, ["mo", "mono", "order", "orderno"])
        type_idx = locate_column_idx(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        d_idx = locate_column_idx(df, ["date", "day", "txndate"])
        prod_idx = locate_column_idx(df, ["production", "prodqty", "shiftproduction", "qty", "quantity"])

        if type_idx is None or prod_idx is None: continue 

        for i in range(len(df)):
            row = df.iloc[i]
            qty = clean_nan(row.iloc[prod_idx])
            if qty <= 0: continue
            
            prod_str = str(row.iloc[type_idx]).strip()
            if prod_str.upper() in ["", "NAN", "TOTAL", "GRAND TOTAL"]: continue
            
            c_val = row.iloc[ch_idx] if ch_idx is not None else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.iloc[mo_idx]).strip() if mo_idx is not None else ""
            if mo_val.upper() in ["NAN", "NONE", "TOTAL"]: mo_val = ""
            
            base_family, _ = parse_family_and_type(prod_str)
            dt = strict_dd_mm_yyyy(row.iloc[d_idx]) if d_idx is not None else None
            
            ch_list.append({"ch": ch, "fam": base_family, "variant": prod_str, "mo": mo_val, "qty": qty, "date": dt})
    return ch_list

def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_CH_ROWS, GLOBAL_TB_ROWS, GLOBAL_SHO_ROWS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        from settings import settings
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_ring = executor.submit(load_excel_sheets, settings.RINGWT_TRANSITBUFFER_URL)
            future_jw = executor.submit(load_excel_sheets, settings.JOBWORK_REPORT_URL)
            future_trb = executor.submit(load_excel_sheets, settings.TRB_MASTER_URL)
            future_dgbb = executor.submit(load_excel_sheets, settings.DGBB_MASTER_URL)
            
            tb_sheets = future_ring.result()
            jw_sheets = future_jw.result()
            trb_sheets = future_trb.result()
            dgbb_sheets = future_dgbb.result()

        # 1. CHANNEL DATA
        GLOBAL_CH_ROWS = process_master_sheets(trb_sheets, is_trb=True) + process_master_sheets(dgbb_sheets, is_trb=False)

        # 2. TRANSIT BUFFER DATA (Failsafe Positional Mapping)
        tb_list = []
        for sheet_name, df in tb_sheets.items():
            if df.empty: continue
            
            ch_idx = locate_column_idx(df, ["chno", "chnum", "channel", "ch"])
            fam_idx = locate_column_idx(df, ["type", "variant", "product", "item"])
            qty_idx = locate_column_idx(df, ["noofrings", "qty", "quantity", "rings"])
            date_idx = locate_column_idx(df, ["date", "indate"])
            
            if fam_idx is None or qty_idx is None: continue

            for i in range(len(df)):
                row = df.iloc[i]
                qty = clean_nan(row.iloc[qty_idx])
                if qty <= 0: continue
                
                prod_text = str(row.iloc[fam_idx]).strip()
                if prod_text.upper() in ["", "NAN", "NONE", "TOTAL", "GRAND TOTAL"]: continue
                
                ch_val = str(row.iloc[ch_idx]) if ch_idx is not None else sheet_name
                ch_val = ch_val.strip().upper().replace("CHANNEL", "").replace("CH", "").replace("-", "").strip()
                if ch_val.startswith("T"): ch_val = ch_val[1:]
                if ch_val.upper() in ["NAN", "NONE", ""]: ch_val = str(sheet_name).strip()
                
                base_fam, r_type = parse_family_and_type(prod_text)
                dt = strict_dd_mm_yyyy(row.iloc[date_idx]) if date_idx is not None else None
                
                tb_list.append({"ch": ch_val, "fam": base_fam, "variant": prod_text, "type": r_type, "qty": qty, "date": dt})
        GLOBAL_TB_ROWS = tb_list

        # 3. SHO DATA (Failsafe 3-Column Mapping)
        sho_list = []
        for sheet_name, df in jw_sheets.items():
            if df.empty: continue
            clean_sheet = str(sheet_name).strip().lower()
            if "master" in clean_sheet or "summary" in clean_sheet: continue
            
            date_idx = locate_column_idx(df, ["jwchallandate", "challandate", "date"])
            prod_idx = locate_column_idx(df, ["product", "item", "variant"])
            qty_idx = locate_column_idx(df, ["qtysent", "sentqty", "qty", "quantity"])
            
            if prod_idx is None or qty_idx is None: continue 
                
            for i in range(len(df)):
                row = df.iloc[i]
                qty = clean_nan(row.iloc[qty_idx])
                if qty <= 0: continue
                
                raw_prod = str(row.iloc[prod_idx]).strip()
                if raw_prod.upper() in ["NAN", "NONE", "", "TOTAL", "GRAND TOTAL"]: continue
                
                base_fam, comp_type = parse_family_and_type(raw_prod)
                dt = strict_dd_mm_yyyy(row.iloc[date_idx]) if date_idx is not None else None
                
                sho_list.append({"fam": base_fam, "type": comp_type, "qty": qty, "date": dt, "label": raw_prod})
        GLOBAL_SHO_ROWS = sho_list

        MASTER_CACHE = compile_summary_data(None, None)
        LAST_REFRESH = datetime.now()

    except Exception as e:
        print(f"❌ COMPILATION FAULT: {str(e)}")
    finally:
        INITIALIZED = True 
        IS_UPDATING = False

def compile_summary_data(start_date_str, end_date_str):
    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str and start_date_str.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str and end_date_str.strip() not in ["", "null", "None"] else None

    def filter_records(records, offset_days=0):
        if not s_dt and not e_dt: return records
        filtered = []
        start_target = s_dt - timedelta(days=offset_days) if s_dt else None
        for r in records:
            d = r.get("date")
            if not d: continue
            if start_target and e_dt:
                if start_target <= d <= e_dt: filtered.append(r)
            elif start_target:
                if d >= start_target: filtered.append(r) 
            elif e_dt:
                if d <= e_dt: filtered.append(r)
        return filtered

    f_ch = filter_records(GLOBAL_CH_ROWS, 0)
    f_tb = filter_records(GLOBAL_TB_ROWS, 0)
    f_sho = filter_records(GLOBAL_SHO_ROWS, 2) 

    ch_grouped = {}
    for r in f_ch:
        k = (r["ch"], r["fam"])
        if k not in ch_grouped: ch_grouped[k] = {"qty": 0, "dates": [], "mos": set()}
        ch_grouped[k]["qty"] += r["qty"]
        if r["date"]: ch_grouped[k]["dates"].append(r["date"])
        if r["mo"]: ch_grouped[k]["mos"].add(r["mo"])

    tb_grouped = {}
    for r in f_tb:
        k = (r["ch"], r["fam"], r["type"])
        if k not in tb_grouped: tb_grouped[k] = {"qty": 0, "dates": []}
        tb_grouped[k]["qty"] += r["qty"]
        if r["date"]: tb_grouped[k]["dates"].append(r["date"])

    sho_grouped = {}
    for r in f_sho:
        k = (r["fam"], r["type"])
        if k not in sho_grouped: sho_grouped[k] = {"qty": 0, "dates": []}
        sho_grouped[k]["qty"] += r["qty"]
        if r["date"]: sho_grouped[k]["dates"].append(r["date"])

    merged_keys = set(ch_grouped.keys()).union({(c, f) for c, f, t in tb_grouped.keys()})

    rows = []
    processed_sho_keys = set()

    for ch, fam in merged_keys:
        ch_data = ch_grouped.get((ch, fam), {"qty": 0, "dates": [], "mos": set()})
        ch_qty = ch_data["qty"]
        ch_in_raw = min(ch_data["dates"]) if ch_data["dates"] else None
        ch_out_raw = max(ch_data["dates"]) if ch_data["dates"] else None
        mo_ref = ", ".join(sorted(ch_data["mos"])) if ch_data["mos"] else "-"
        
        types_found = [t for (c, f, t) in tb_grouped.keys() if c == ch and f == fam]
        if not types_found: types_found = ["ASSEMBLY"]

        for r_type in types_found:
            tb_data = tb_grouped.get((ch, fam, r_type), {"qty": 0, "dates": []})
            tb_qty = tb_data["qty"]
            tb_out_raw = max(tb_data["dates"]) if tb_data["dates"] else None

            sho_key = (fam, r_type)
            sho_qty = 0
            sho_in_raw = None
            
            if sho_key in sho_grouped:
                sho_qty = sho_grouped[sho_key]["qty"]
                sho_in_raw = min(sho_grouped[sho_key]["dates"]) if sho_grouped[sho_key]["dates"] else None
                processed_sho_keys.add(sho_key)

            if tb_qty == 0 and ch_qty > 0: calc_status = "Channel Only"
            elif tb_qty > 0 and ch_qty == 0: calc_status = "Missing Channel Data"
            elif ch_qty >= tb_qty and tb_qty > 0: calc_status = "Completed"
            else: calc_status = "In Process"
            
            # Use chronological data boundary, fallback to minimum system boundary if unassigned
            sort_date = sho_in_raw or tb_out_raw or ch_in_raw or datetime.min.date()

            rows.append({
                "_sort_date": sort_date, 
                "channel_ref": ch, "mo_ref": mo_ref,
                "product_variant": fam, "ring_type": r_type,
                "sho_qty": safe_ceil(sho_qty), "sho_in": format_dt(sho_in_raw),
                "tb_qty": safe_ceil(tb_qty), "tb_out": format_dt(tb_out_raw),
                "ch_qty": safe_ceil(ch_qty), "ch_in": format_dt(ch_in_raw), "ch_out": format_dt(ch_out_raw),
                "status": calc_status
            })

    for (fam, r_type), s_data in sho_grouped.items():
        if (fam, r_type) not in processed_sho_keys:
            sho_in_raw = min(s_data["dates"]) if s_data["dates"] else None
            sort_date = sho_in_raw or datetime.min.date()
            rows.append({
                "_sort_date": sort_date,
                "channel_ref": "-", "mo_ref": "-",
                "product_variant": fam, "ring_type": r_type,
                "sho_qty": safe_ceil(s_data["qty"]), "sho_in": format_dt(sho_in_raw),
                "tb_qty": 0, "tb_out": "-", "ch_qty": 0, "ch_in": "-", "ch_out": "-", "status": "SHO Logged"
            })

    # --- CHRONOLOGICAL SORTING: NEWEST DATES FIRST ---
    rows.sort(key=lambda x: x["_sort_date"], reverse=True)
    
    for r in rows:
        del r["_sort_date"]
    return rows

def background_refresh_loop():
    while True:
        try: process_tbe_data()
        except Exception as e: print(f"Background Error: {e}")
        time.sleep(CACHE_DURATION_MINUTES * 60)

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/tbe_all_mos")
def get_tbe_dashboard(start_date: str = Query(None), end_date: str = Query(None)):
    if not INITIALIZED: return {"status": "initializing", "data": []}
    if start_date or end_date:
        return {"status": "success", "data": compile_summary_data(start_date, end_date)}
    return {"status": "success", "data": MASTER_CACHE}

@router.get("/tbe_variant_details")
def get_tbe_variant_details(ch: str = Query(...), fam: str = Query(...), start_date: str = Query(None), end_date: str = Query(None)):
    s_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date and start_date.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date and end_date.strip() not in ["", "null", "None"] else None

    def local_filter(records, offset_days=0):
        if not s_dt and not e_dt: return records
        filtered = []
        start_target = s_dt - timedelta(days=offset_days) if s_dt else None
        for r in records:
            d = r.get("date")
            if not d: continue
            if start_target and e_dt:
                if start_target <= d <= e_dt: filtered.append(r)
            elif start_target:
                if d >= start_target: filtered.append(r)
            elif e_dt:
                if d <= e_dt: filtered.append(r)
        return filtered

    ch_f = local_filter([r for r in GLOBAL_CH_ROWS if r["ch"] == ch and r["fam"] == fam], 0)
    tb_f = local_filter([r for r in GLOBAL_TB_ROWS if r["ch"] == ch and r["fam"] == fam], 0)
    sho_f = local_filter([r for r in GLOBAL_SHO_ROWS if r["fam"] == fam], 2)

    sho_map, tb_map, ch_map = {}, {}, {}

    for r in sho_f:
        norm_key = str(r["label"]).upper().replace("-", "").replace(" ", "")
        if not norm_key: continue
        if norm_key not in sho_map: sho_map[norm_key] = {"label": r["label"], "qty": 0.0, "dates": []}
        sho_map[norm_key]["qty"] += r["qty"]
        if r["date"]: sho_map[norm_key]["dates"].append(r["date"])

    for r in tb_f:
        norm_key = str(r["variant"]).upper().replace("-", "").replace(" ", "")
        if not norm_key: continue
        if norm_key not in tb_map: tb_map[norm_key] = {"label": r["variant"], "qty": 0.0, "dates": []}
        tb_map[norm_key]["qty"] += r["qty"]
        if r["date"]: tb_map[norm_key]["dates"].append(r["date"])

    for r in ch_f:
        raw_mo = str(r.get("mo", "")).strip()
        norm_v = str(r["variant"]).upper().replace("-", "").replace(" ", "")
        if not norm_v: continue
        
        norm_key = (norm_v, raw_mo)
        if norm_key not in ch_map: ch_map[norm_key] = {"label": r["variant"], "exact_mo": raw_mo, "qty": 0.0, "dates": []}
        ch_map[norm_key]["qty"] += r["qty"]
        if r["date"]: ch_map[norm_key]["dates"].append(r["date"])
            
    sequential_rows = []
    
    for k, data in sho_map.items():
        min_date_raw = min(data["dates"]) if data["dates"] else None
        sequential_rows.append({
            "_sort_date": min_date_raw or datetime.min.date(),
            "mo_ref": f"Ch: {ch}", "department": "SHO Department", "variant": data["label"],
            "in_date": format_dt(min_date_raw), "out_date": "-",  
            "qty": safe_ceil(data["qty"]), "status": "Allocated"
        })

    for k, data in tb_map.items():
        max_date_raw = max(data["dates"]) if data["dates"] else None
        sequential_rows.append({
            "_sort_date": max_date_raw or datetime.min.date(),
            "mo_ref": f"Ch: {ch}", "department": "Transit Buffer", "variant": data["label"],
            "in_date": "-", "out_date": format_dt(max_date_raw),
            "qty": safe_ceil(data["qty"]), "status": "In Transit"
        })

    for k, data in ch_map.items():
        exact_mo = data["exact_mo"]
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo else f"Ch: {ch}"
        min_date_raw = min(data["dates"]) if data["dates"] else None
        max_date_raw = max(data["dates"]) if data["dates"] else None
        sequential_rows.append({
            "_sort_date": min_date_raw or datetime.min.date(),
            "mo_ref": ch_mo_display, "department": "Channel Section", "variant": data["label"],
            "in_date": format_dt(min_date_raw),
            "out_date": format_dt(max_date_raw),
            "qty": safe_ceil(data["qty"]), "status": "Completed"
        })

    # Sort deep-dive chronological windows newest first
    sequential_rows.sort(key=lambda x: x["_sort_date"], reverse=True)
    for r in sequential_rows:
        del r["_sort_date"]

    return {"status": "success", "data": sequential_rows}
