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

# --- BULLETPROOF DD-MM-YYYY PARSER ---
# This explicitly forces the first number to be the Day. It cannot flip to MM-DD.
def strict_dd_mm_yyyy(value):
    if pd.isna(value) or value is None: return None
    if isinstance(value, (datetime, pd.Timestamp)): return value.date()
    
    val_str = str(value).strip().lower().split()[0] # Remove timestamps
    if val_str in ["nan", "nat", "", "-", "none"]: return None
    
    # Replace slashes and dots with dashes
    val_str = val_str.replace("/", "-").replace(".", "-")
    
    try:
        parts = val_str.split("-")
        if len(parts) >= 2:
            # If year is first (YYYY-MM-DD), handle it safely
            if len(parts[0]) == 4:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
            
            # FORCE DD-MM-YYYY
            d = int(parts[0])
            m = int(parts[1])
            y = int(parts[2]) if len(parts) >= 3 else datetime.now().year
            
            if y < 100: y += 2000
            return datetime(y, m, d).date()
    except:
        pass
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

def find_column(df, patterns):
    cols = {re.sub(r'[^a-z0-9]', '', str(c).lower()): c for c in df.columns}
    for p in patterns:
        p_clean = re.sub(r'[^a-z0-9]', '', p.lower())
        if p_clean in cols: return cols[p_clean]
    for p in patterns:
        p_clean = re.sub(r'[^a-z0-9]', '', p.lower())
        for clean_col, orig_col in cols.items():
            if p_clean in clean_col: return orig_col
    return None

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        try: xls = pd.ExcelFile(content, engine='calamine')
        except: xls = pd.ExcelFile(content, engine='openpyxl')
        sheets = {}
        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name)
            # Find the true header row
            if not df.empty:
                for i in range(min(15, len(df))):
                    row_vals = [str(x).lower().replace(" ", "") for x in df.iloc[i].values]
                    if any(key in row_vals for key in ["date", "qty", "product", "channel", "ch", "jwchallandate", "qtysent"]):
                        df.columns = [str(c).strip() if pd.notna(c) else f"U_{j}" for j, c in enumerate(df.iloc[i].tolist())]
                        df = df.iloc[i+1:].reset_index(drop=True)
                        break
            sheets[sheet_name] = df
        return sheets
    except Exception as e:
        print(f"Excel load error for {url}: {e}")
        return {}

def process_master_sheets(sheets_dict, is_trb):
    ch_list = []
    for sheet_name, df in sheets_dict.items():
        if df.empty: continue
        clean_name = str(sheet_name).strip().upper()
        if not re.match(r'^(T|CH)[-\s]*\d+', clean_name): continue
            
        ch_col = find_column(df, ["channelno", "channel", "machineno", "line", "ch"])
        mo_col = find_column(df, ["mo", "mono", "order", "orderno"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        d_col = find_column(df, ["date", "day", "txndate"])
        prod_col = find_column(df, ["production", "prodqty", "shiftproduction", "qty", "quantity"])

        if not type_col: continue 

        for _, row in df.iterrows():
            c_val = row.get(ch_col) if ch_col else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.get(mo_col, "")).strip()
            if mo_val.upper() in ["NAN", "NONE", "TOTAL"]: mo_val = ""
            
            prod_str = str(row.get(type_col)).strip()
            if prod_str.upper() in ["", "NAN", "TOTAL", "GRAND TOTAL"]: continue
            
            base_family, _ = parse_family_and_type(prod_str)
            qty = clean_nan(row.get(prod_col))
            dt = strict_dd_mm_yyyy(row.get(d_col))  # Using strict parser for consistency
            
            if qty > 0:
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

        # 1. CHANNEL EXTRACTION
        ch_list = process_master_sheets(trb_sheets, is_trb=True) + process_master_sheets(dgbb_sheets, is_trb=False)

        # 2. EXACT TRANSIT BUFFER EXTRACTION
        tb_list = []
        for sheet_name, df in tb_sheets.items():
            if df.empty: continue
            
            cols = {str(c).lower().replace(" ", "").replace("#", ""): c for c in df.columns}
            
            ch_col = cols.get("ch") or cols.get("chno") or cols.get("channel")
            fam_col = cols.get("type") or cols.get("variant") or cols.get("product")
            qty_col = cols.get("noofrings") or cols.get("qty")
            date_col = cols.get("date") or cols.get("indate")
            
            if not fam_col: continue

            for _, row in df.iterrows():
                ch_val = str(row.get(ch_col, sheet_name)).strip().upper().replace("CHANNEL", "").replace("CH", "").replace("-", "").strip()
                if ch_val.startswith("T"): ch_val = ch_val[1:]
                
                prod_text = str(row.get(fam_col)).strip()
                if prod_text.upper() in ["", "NAN", "NONE"]: continue
                
                base_fam, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(qty_col))
                dt = strict_dd_mm_yyyy(row.get(date_col))
                
                if qty > 0:
                    tb_list.append({"ch": ch_val, "fam": base_fam, "variant": prod_text, "type": r_type, "qty": qty, "date": dt})

        # 3. FROM-SCRATCH SHO (JOBWORK) EXTRACTION - 3 COLUMNS ONLY
        sho_list = []
        for sheet_name, df in jw_sheets.items():
            if df.empty: continue
            clean_sheet = str(sheet_name).strip().lower()
            if "master" in clean_sheet or "summary" in clean_sheet: continue
            
            # Pure targeted column match
            cols = {str(c).lower().replace(" ", ""): c for c in df.columns}
            
            date_col = cols.get("jwchallandate")
            prod_col = cols.get("product") or cols.get("item")
            qty_col = cols.get("qtysent") or cols.get("sentqty")
            
            if not date_col or not prod_col or not qty_col: 
                continue 
                
            for _, row in df.iterrows():
                raw_prod = str(row.get(prod_col, "")).strip()
                if raw_prod.upper() in ["NAN", "NONE", "", "TOTAL"]: continue
                
                base_fam, comp_type = parse_family_and_type(raw_prod)
                qty = clean_nan(row.get(qty_col))
                dt = strict_dd_mm_yyyy(row.get(date_col))
                
                if qty > 0:
                    sho_list.append({"fam": base_fam, "type": comp_type, "qty": qty, "date": dt, "label": raw_prod})

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

def compile_summary_data(start_date_str, end_date_str):
    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str and start_date_str.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str and end_date_str.strip() not in ["", "null", "None"] else None

    # Forward-Looking Filter Logic
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
    f_sho = filter_records(GLOBAL_SHO_ROWS, 2) # SHO looks 2 days earlier

    # Aggregations
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

    # Build Outer Join (CH + TB)
    merged_keys = set()
    for (ch, fam) in ch_grouped.keys():
        merged_keys.add((ch, fam))
    for (ch, fam, r_type) in tb_grouped.keys():
        merged_keys.add((ch, fam))

    rows = []
    processed_sho_keys = set()

    for ch, fam in merged_keys:
        ch_data = ch_grouped.get((ch, fam), {"qty": 0, "dates": [], "mos": set()})
        ch_qty = ch_data["qty"]
        ch_in = format_dt(min(ch_data["dates"])) if ch_data["dates"] else "-"
        ch_out = format_dt(max(ch_data["dates"])) if ch_data["dates"] else "-"
        mo_ref = ", ".join(sorted(ch_data["mos"])) if ch_data["mos"] else "-"
        
        # Check TB for this CH + FAM (could have IM and OM)
        types_found = [t for (c, f, t) in tb_grouped.keys() if c == ch and f == fam]
        if not types_found: types_found = ["ASSEMBLY"]

        for r_type in types_found:
            tb_data = tb_grouped.get((ch, fam, r_type), {"qty": 0, "dates": []})
            tb_qty = tb_data["qty"]
            tb_out = format_dt(max(tb_data["dates"])) if tb_data["dates"] else "-"

            sho_key = (fam, r_type)
            sho_qty = 0
            sho_in = "-"
            
            # Match purely by family type
            if sho_key in sho_grouped:
                sho_qty = sho_grouped[sho_key]["qty"]
                sho_in = format_dt(min(sho_grouped[sho_key]["dates"])) if sho_grouped[sho_key]["dates"] else "-"
                processed_sho_keys.add(sho_key)

            if tb_qty == 0 and ch_qty > 0: calc_status = "Channel Only"
            elif tb_qty > 0 and ch_qty == 0: calc_status = "Missing Channel Data"
            elif ch_qty >= tb_qty and tb_qty > 0: calc_status = "Completed"
            else: calc_status = "In Process"

            rows.append({
                "channel_ref": ch, "mo_ref": mo_ref,
                "product_variant": fam, "ring_type": r_type,
                "sho_qty": safe_ceil(sho_qty), "sho_in": sho_in,
                "tb_qty": safe_ceil(tb_qty), "tb_out": tb_out,
                "ch_qty": safe_ceil(ch_qty), "ch_in": ch_in, "ch_out": ch_out,
                "status": calc_status
            })

    # Add remaining SHO data that didn't map to any CH or TB
    for (fam, r_type), s_data in sho_grouped.items():
        if (fam, r_type) not in processed_sho_keys:
            rows.append({
                "channel_ref": "-", "mo_ref": "-",
                "product_variant": fam, "ring_type": r_type,
                "sho_qty": safe_ceil(s_data["qty"]), "sho_in": format_dt(min(s_data["dates"])) if s_data["dates"] else "-",
                "tb_qty": 0, "tb_out": "-", "ch_qty": 0, "ch_in": "-", "ch_out": "-", "status": "SHO Logged"
            })

    rows.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
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
        sequential_rows.append({
            "mo_ref": f"Ch: {ch}", "department": "SHO Department", "variant": data["label"],
            "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": "-",  
            "qty": safe_ceil(data["qty"]), "status": "Allocated"
        })

    for k, data in tb_map.items():
        sequential_rows.append({
            "mo_ref": f"Ch: {ch}", "department": "Transit Buffer", "variant": data["label"],
            "in_date": "-", "out_date": format_dt(max(data["dates"])) if data["dates"] else "-",
            "qty": safe_ceil(data["qty"]), "status": "In Transit"
        })

    for k, data in ch_map.items():
        exact_mo = data["exact_mo"]
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo else f"Ch: {ch}"
        sequential_rows.append({
            "mo_ref": ch_mo_display, "department": "Channel Section", "variant": data["label"],
            "in_date": format_dt(min(data["dates"])) if data["dates"] else "-",
            "out_date": format_dt(max(data["dates"])) if data["dates"] else "-",
            "qty": safe_ceil(data["qty"]), "status": "Completed"
        })

    return {"status": "success", "data": sequential_rows}
