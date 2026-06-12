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

NUM_REGEX = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
PREFIX_REGEX = re.compile(r'^(CH-|CH\.|CH|CHANNEL-|CHANNEL|SHEET-|SHEET)')
FAM_REGEX = re.compile(r'(\d{3,5})')

def format_dt(dt):
    if dt and pd.notna(dt): return dt.strftime("%d-%m-%Y")
    return "-"

def safe_ceil(value):
    if pd.isna(value) or value is None: return 0
    try: return math.ceil(float(value))
    except: return 0

# --- ABSOLUTE STRICT DATE PARSERS ---
def parse_dd_mm_yyyy(value):
    """Forces Day-Month-Year format (JobWork & Transit Buffer)"""
    if pd.isna(value) or value is None: return None
    if isinstance(value, (datetime, pd.Timestamp)): return value.date()
    val_str = str(value).strip().lower()
    if val_str in ["nan", "nat", "", "-", "none"]: return None
    try:
        # dayfirst=True absolutely prevents 11 March becoming 3 Nov
        res = pd.to_datetime(val_str, dayfirst=True, errors='coerce')
        if pd.isna(res): return None 
        return res.date()
    except: return None

def parse_mm_dd_yyyy(value):
    """Forces Month-Day-Year format (Channel Master)"""
    if pd.isna(value) or value is None: return None
    if isinstance(value, (datetime, pd.Timestamp)): return value.date()
    val_str = str(value).strip().lower()
    if val_str in ["nan", "nat", "", "-", "none"]: return None
    try:
        res = pd.to_datetime(val_str, dayfirst=False, errors='coerce')
        if pd.isna(res): return None 
        return res.date()
    except: return None

def repair_sheet_headers(df):
    if df.empty: return df
    targets = {"ch", "chno", "type", "noofrings", "date", "netwt", "ringwt", "qty", "quantity"}
    best_row_idx = -1
    max_score = 0
    for idx in range(min(20, len(df))):
        row_vals = [str(val).strip().lower().replace(" ", "").replace("#", "") for val in df.iloc[idx].values]
        score = sum(1 for t in targets if any(t in v for v in row_vals))
        if score > max_score:
            max_score = score
            best_row_idx = idx
    if max_score >= 2 and best_row_idx >= 0:
        new_cols = df.iloc[best_row_idx].tolist()
        new_cols = [str(c).strip() if pd.notna(c) else f"Unnamed_{i}" for i, c in enumerate(new_cols)]
        df.columns = new_cols
        return df.iloc[best_row_idx+1:].reset_index(drop=True)
    return df

def find_exact_column(df, exact_names):
    """Strictly matches columns, ignoring spaces and dots to prevent grabbing wrong headers"""
    cols = {str(c).strip().lower().replace(" ", "").replace(".", "").replace("_", ""): c for c in df.columns}
    for name in exact_names:
        clean_name = name.lower().replace(" ", "").replace(".", "").replace("_", "")
        if clean_name in cols:
            return cols[clean_name]
    return None

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

def parse_family_and_type(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", ""]: return "UNKNOWN", "ASSEMBLY"
    r_type = "ASSEMBLY"
    t_norm = text.replace("-", " ").replace("_", " ").replace("/", " ")
    words = t_norm.split()
    if any(w in ["IM", "IR", "INNER"] for w in words) or "INNER" in text or "IM" in text or "IR" in text:
        r_type = "IM"
    elif any(w in ["OM", "OR", "OUTER"] for w in words) or "OUTER" in text or "OM" in text or "OR" in text:
        r_type = "OM"
    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    if "BT" in words or text.startswith("BT") or "-BT" in text or " BT" in text: base = f"BT-{base}"
    elif "BB" in words or text.startswith("BB") or "-BB" in text or " BB" in text: base = f"BB-{base}"
    return base, r_type

def clean_nan(value):
    if pd.isna(value): return 0.0
    val_str = str(value)
    match = NUM_REGEX.search(val_str.replace(',', ''))
    if match: return float(match.group())
    return 0.0

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        try: xls = pd.ExcelFile(content, engine='calamine')
        except: xls = pd.ExcelFile(content)
        time.sleep(0.05) 
        return {sheet: repair_sheet_headers(xls.parse(sheet)) for sheet in xls.sheet_names}
    except Exception as e: return {}

def process_master_sheets(sheets_dict, is_trb):
    ch_list = []
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01) 
        if df.empty: continue
        clean_name = str(sheet_name).strip().upper()
        if not re.match(r'^(T|CH)[-\s]*\d+', clean_name): continue
            
        ch_col = find_exact_column(df, ["channelno", "channel", "machineno", "line", "ch"])
        mo_col = find_exact_column(df, ["mo", "mono", "order", "orderno"])
        type_col = find_exact_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        d_col = find_exact_column(df, ["date", "day", "txndate"])
        prod_col = find_exact_column(df, ["production", "prodqty", "shiftproduction", "qty", "quantity"])

        if not type_col: continue 

        target_cols = [c for c in [ch_col, mo_col, type_col, d_col, prod_col] if c]
        for row in df[target_cols].to_dict('records'):
            c_val = row.get(ch_col) if ch_col else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.get(mo_col)).strip() if mo_col else ""
            if mo_val.upper() in ["NAN", "NONE", "TOTAL"]: mo_val = ""
            
            prod_str = str(row.get(type_col)).strip()
            if prod_str.upper() in ["", "NAN", "TOTAL", "GRAND TOTAL"]: continue
            
            base_family, _ = parse_family_and_type(prod_str)
            qty = clean_nan(row.get(prod_col)) if prod_col else 0.0
            
            # CHANNEL explicitly uses MM-DD-YYYY
            dt = parse_mm_dd_yyyy(row.get(d_col)) 

            ch_list.append({"ch": ch, "fam": base_family, "variant": prod_str, "mo": mo_val, "qty": qty, "date": dt})
    return ch_list

def compile_summary_data(start_date_str=None, end_date_str=None):
    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str and start_date_str.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str and end_date_str.strip() not in ["", "null", "None"] else None

    # Filter Channel
    filtered_ch = []
    for r in GLOBAL_CH_ROWS:
        if s_dt or e_dt:
            d = r.get("date")
            if pd.isna(d) or d is None: continue
            if s_dt and e_dt and not (s_dt <= d <= e_dt): continue
            if s_dt and not e_dt and d < s_dt: continue 
            if e_dt and not s_dt and d > e_dt: continue
        filtered_ch.append(r)

    # Filter Transit Buffer
    filtered_tb = []
    for r in GLOBAL_TB_ROWS:
        if s_dt or e_dt:
            d = r.get("date")
            if pd.isna(d) or d is None: continue
            if s_dt and e_dt and not (s_dt <= d <= e_dt): continue
            if s_dt and not e_dt and d < s_dt: continue 
            if e_dt and not s_dt and d > e_dt: continue
        filtered_tb.append(r)

    # Filter JobWork (with -2 Days applied to start_date)
    sho_s_dt = s_dt - timedelta(days=2) if s_dt else None
    filtered_sho = []
    for r in GLOBAL_SHO_ROWS:
        if sho_s_dt or e_dt:
            d = r.get("date")
            if pd.isna(d) or d is None: continue
            if sho_s_dt and e_dt and not (sho_s_dt <= d <= e_dt): continue
            if sho_s_dt and not e_dt and d < sho_s_dt: continue 
            if e_dt and not sho_s_dt and d > e_dt: continue
        filtered_sho.append(r)

    # --- PURE FAMILY AGGREGATION FOR JOBWORK ---
    sho_grouped = {}
    for r in filtered_sho:
        k = (r["fam"], r["type"])
        if k not in sho_grouped:
            sho_grouped[k] = {"qty": 0.0, "dates": []}
        sho_grouped[k]["qty"] += r["qty"]
        if r["date"]: sho_grouped[k]["dates"].append(r["date"])

    if filtered_ch:
        df_ch_grouped = pd.DataFrame(filtered_ch).groupby(["ch", "fam"]).agg(
            ch_qty=('qty', 'sum'),
            ch_min_date=('date', lambda x: min([d for d in x if pd.notna(d) and d is not None], default=None)),
            ch_max_date=('date', lambda x: max([d for d in x if pd.notna(d) and d is not None], default=None)),
            mo_list=('mo', lambda x: ", ".join(sorted(set([str(i) for i in x if pd.notna(i) and str(i).strip()]))))
        ).reset_index()
    else:
        df_ch_grouped = pd.DataFrame(columns=["ch", "fam", "ch_qty", "ch_min_date", "ch_max_date", "mo_list"])

    tb_list_parsed = []
    for r in filtered_tb:
        tb_list_parsed.append({
            "ch": r["ch"], "fam": r["fam"], "type": r.get("type", parse_family_and_type(r["variant"])[1]),
            "qty": r["qty"], "date": r["date"]
        })

    if tb_list_parsed:
        df_tb_grouped = pd.DataFrame(tb_list_parsed).groupby(["ch", "fam", "type"]).agg(
            tb_qty=('qty', 'sum'),
            tb_min_date=('date', lambda x: min([d for d in x if pd.notna(d) and d is not None], default=None)),
            tb_max_date=('date', lambda x: max([d for d in x if pd.notna(d) and d is not None], default=None))
        ).reset_index()
    else:
        df_tb_grouped = pd.DataFrame(columns=["ch", "fam", "type", "tb_qty", "tb_min_date", "tb_max_date"])

    merged = pd.merge(df_tb_grouped, df_ch_grouped, on=["ch", "fam"], how="outer")

    base_rows = []
    matched_sho_keys = set()

    for _, row in merged.iterrows():
        ch, fam = row["ch"], row["fam"]
        r_type = row.get("type") if pd.notna(row.get("type")) else "ASSEMBLY"
        mo_list = row.get("mo_list", "")
        
        # Pull matching SHO data perfectly by Family & Type
        sho_key = (fam, r_type)
        if sho_key in sho_grouped:
            sho_qty = sho_grouped[sho_key]["qty"]
            sho_in_date = format_dt(min(sho_grouped[sho_key]["dates"])) if sho_grouped[sho_key]["dates"] else "-"
            matched_sho_keys.add(sho_key)
        else:
            sho_qty = 0.0
            sho_in_date = "-"

        tb_q = safe_ceil(row.get("tb_qty"))
        ch_q = safe_ceil(row.get("ch_qty"))

        if tb_q == 0 and ch_q > 0: calc_status = "Channel Only"
        elif tb_q > 0 and ch_q == 0: calc_status = "Missing Channel Data"
        elif ch_q >= tb_q and tb_q > 0: calc_status = "Completed"
        else: calc_status = "In Process"

        base_rows.append({
            "channel_ref": ch, 
            "mo_ref": mo_list if pd.notna(mo_list) else "",
            "product_variant": fam, 
            "ring_type": r_type,
            "sho_qty": safe_ceil(sho_qty), 
            "sho_in": sho_in_date,
            "tb_qty": tb_q, 
            "tb_out": format_dt(row.get("tb_max_date")),
            "ch_qty": ch_q,
            "ch_in": format_dt(row.get("ch_min_date")),
            "ch_out": format_dt(row.get("ch_max_date")),
            "status": calc_status
        })

    # Ensure un-matched JobWork entries are still visible!
    for k, data in sho_grouped.items():
        if k not in matched_sho_keys:
            fam, r_type = k
            base_rows.append({
                "channel_ref": "-", "mo_ref": "-",
                "product_variant": fam, "ring_type": r_type,
                "sho_qty": safe_ceil(data["qty"]), "tb_qty": 0,
                "sho_in": format_dt(min(data["dates"])) if data["dates"] else "-",
                "tb_out": "-", "ch_qty": 0, "ch_in": "-", "ch_out": "-",
                "status": "SHO Logged"
            })

    base_rows.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
    return base_rows

def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_CH_ROWS, GLOBAL_TB_ROWS, GLOBAL_SHO_ROWS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        from settings import settings
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_ring = executor.submit(load_excel_sheets, settings.RINGWT_TRANSITBUFFER_URL)
            future_trb = executor.submit(load_excel_sheets, settings.TRB_MASTER_URL)
            future_dgbb = executor.submit(load_excel_sheets, settings.DGBB_MASTER_URL)
            future_jw = executor.submit(load_excel_sheets, settings.JOBWORK_REPORT_URL)
            
            ring_wt_sheets = future_ring.result()
            trb_sheets = future_trb.result()
            dgbb_sheets = future_dgbb.result()
            jw_sheets = future_jw.result()

        ch_list = process_master_sheets(trb_sheets, is_trb=True) + process_master_sheets(dgbb_sheets, is_trb=False)

        tb_list = []
        for sheet_name, df in ring_wt_sheets.items():
            time.sleep(0.01) 
            if df.empty: continue
            
            c_col = find_exact_column(df, ["ch#no", "channelref", "channel", "machineno"])
            f_col = find_exact_column(df, ["type", "ringfamily", "family", "variant", "product"])
            d_col = find_exact_column(df, ["date", "indate", "outdate", "day"])
            q_col = find_exact_column(df, ["noofrings", "qty", "quantity", "total"])
            
            if not f_col: continue 

            target_cols = [c for c in [c_col, f_col, d_col, q_col] if c]
            for row in df[target_cols].to_dict('records'):
                c_val = row.get(c_col) if c_col else sheet_name
                ch = normalize_channel(c_val, force_t_prefix=False) 
                if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=False)
                
                prod_text = str(row.get(f_col)).strip()
                if prod_text.upper() in ["", "NAN"]: continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col)) if q_col else 0.0
                
                # STRICT: RingWT explicitly uses DD-MM-YYYY
                dt = parse_dd_mm_yyyy(row.get(d_col))

                tb_list.append({"ch": ch, "fam": base_family, "variant": prod_text, "type": r_type, "qty": qty, "date": dt})

        sho_list = []
        for sheet_name, df in jw_sheets.items():
            time.sleep(0.01)
            clean_sheet = str(sheet_name).strip().lower()
            if any(k in clean_sheet for k in ["summary", "pivot", "total", "history", "dash", "master"]): continue
            
            # ABSOLUTE TARGETING: EXACT COLUMNS ONLY
            prod_col = find_exact_column(df, ["product", "item", "itemdescription"])
            qty_col = find_exact_column(df, ["qtysent", "sentqty"])
            date_col = find_exact_column(df, ["jwchallandate"])
            
            if not prod_col or not qty_col or not date_col: continue
            
            target_cols = [c for c in [prod_col, qty_col, date_col] if c]
            for row in df[target_cols].to_dict('records'):
                raw_product = str(row.get(prod_col, ""))
                if raw_product.upper() in ["NAN", "NONE", "NA", "", "TOTAL", "GRAND TOTAL"]: continue
                
                base_fam, comp_type = parse_family_and_type(raw_product)
                sho_qty = clean_nan(row.get(qty_col))
                
                # STRICT: JobWork Report explicitly uses DD-MM-YYYY
                sho_date = parse_dd_mm_yyyy(row.get(date_col))
                
                if sho_qty > 0:
                    sho_list.append({"fam": base_fam, "type": comp_type, "qty": sho_qty, "date": sho_date, "label": raw_product})

        GLOBAL_CH_ROWS = ch_list
        GLOBAL_TB_ROWS = tb_list
        GLOBAL_SHO_ROWS = sho_list

        MASTER_CACHE = compile_summary_data(None, None)
        LAST_REFRESH = datetime.now()

    except Exception as e:
        print(f"❌ COMPILATION FAULT: {str(e)}")
    finally:
        INITIALIZED = True 
        IS_UPDATING = False

def background_refresh_loop():
    while True:
        try: process_tbe_data()
        except Exception as e: print(f"Background thread error: {e}")
        time.sleep(CACHE_DURATION_MINUTES * 60)

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/tbe_all_mos")
def get_tbe_dashboard(start_date: str = Query(None), end_date: str = Query(None)):
    if not INITIALIZED: return {"status": "initializing", "message": "Compiling data matrices...", "data": []}
    if start_date or end_date:
        return {"status": "success", "last_updated": str(LAST_REFRESH), "data": compile_summary_data(start_date, end_date)}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/tbe_variant_details")
def get_tbe_variant_details(ch: str = Query(...), fam: str = Query(...), start_date: str = Query(None), end_date: str = Query(None)):
    s_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date and start_date.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date and end_date.strip() not in ["", "null", "None"] else None

    ch_f = []
    for r in GLOBAL_CH_ROWS:
        if r["ch"] == ch and r["fam"] == fam:
            d = r.get("date")
            if s_dt or e_dt:
                if pd.isna(d) or d is None: continue
                if s_dt and e_dt and not (s_dt <= d <= e_dt): continue
                if s_dt and not e_dt and d < s_dt: continue
                if e_dt and not s_dt and d > e_dt: continue
            ch_f.append(r)
            
    tb_f = []
    for r in GLOBAL_TB_ROWS:
        if r["ch"] == ch and r["fam"] == fam:
            d = r.get("date")
            if s_dt or e_dt:
                if pd.isna(d) or d is None: continue
                if s_dt and e_dt and not (s_dt <= d <= e_dt): continue
                if s_dt and not e_dt and d < s_dt: continue
                if e_dt and not s_dt and d > e_dt: continue
            tb_f.append(r)

    sho_f = []
    sho_s_dt = s_dt - timedelta(days=2) if s_dt else None
    for r in GLOBAL_SHO_ROWS:
        if r["fam"] == fam:
            d = r.get("date")
            if sho_s_dt or e_dt:
                if pd.isna(d) or d is None: continue
                if sho_s_dt and e_dt and not (sho_s_dt <= d <= e_dt): continue
                if sho_s_dt and not e_dt and d < sho_s_dt: continue
                if e_dt and not sho_s_dt and d > e_dt: continue
            sho_f.append(r)

    found_mos = sorted(list(set([str(r["mo"]).strip() for r in ch_f if r.get("mo")])))
    mo_reference = ", ".join(found_mos) if found_mos else "-"
    mo_group_display = f"{mo_reference} (Ch: {ch})" if (mo_reference != "-" and ch) else (f"Ch: {ch}" if ch else mo_reference)

    sho_map, tb_map, ch_map, mo_summary_map = {}, {}, {}, {}

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
            
        if raw_mo not in mo_summary_map: mo_summary_map[raw_mo] = {"qty": 0.0, "dates": []}
        mo_summary_map[raw_mo]["qty"] += r["qty"]
        if r["date"]: mo_summary_map[raw_mo]["dates"].append(r["date"])

    sequential_rows = []
    for k, data in sho_map.items():
        sequential_rows.append({
            "mo_ref": mo_group_display, "department": "SHO Department", "variant": data["label"],
            "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": "-",  
            "qty": safe_ceil(data["qty"]), "status": "Allocated"
        })

    for k, data in tb_map.items():
        sequential_rows.append({
            "mo_ref": mo_group_display, "department": "Transit Buffer", "variant": data["label"],
            "in_date": "-", "out_date": format_dt(max(data["dates"])) if data["dates"] else "-",
            "qty": safe_ceil(data["qty"]), "status": "In Transit"
        })
        
    for exact_mo, data in mo_summary_map.items():
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo and ch else (exact_mo if exact_mo else (f"Ch: {ch}" if ch else "-"))
        sequential_rows.append({
            "mo_ref": ch_mo_display, "department": "Channel (MO Summary)", "variant": "ALL VARIANTS",
            "in_date": format_dt(min(data["dates"])) if data["dates"] else "-",
            "out_date": format_dt(max(data["dates"])) if data["dates"] else "-",
            "qty": safe_ceil(data["qty"]), "status": "MO Total"
        })

    for k, data in ch_map.items():
        exact_mo = data["exact_mo"]
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo and ch else (exact_mo if exact_mo else (f"Ch: {ch}" if ch else "-"))
        sequential_rows.append({
            "mo_ref": ch_mo_display, "department": "Channel Section", "variant": data["label"],
            "in_date": format_dt(min(data["dates"])) if data["dates"] else "-",
            "out_date": format_dt(max(data["dates"])) if data["dates"] else "-",
            "qty": safe_ceil(data["qty"]), "status": "Completed"
        })

    return {"status": "success", "data": sequential_rows}
