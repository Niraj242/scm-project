from fastapi import APIRouter, Query
import pandas as pd
import requests
import io
import threading
import time
import re
import math
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False  
CACHE_DURATION_MINUTES = 5

GLOBAL_CH_ROWS = []
GLOBAL_TB_ROWS = []

HTTP_SESSION = requests.Session()

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

def find_column(df, patterns):
    cols = [str(c).strip() for c in df.columns]
    for p in patterns:
        norm_p = p.lower().replace(" ", "").replace("_", "").replace("#", "")
        for c in cols:
            norm_c = c.lower().replace(" ", "").replace("_", "").replace("#", "")
            if norm_c == norm_p: return c
    return None

def normalize_channel(value, force_t_prefix=False):
    if pd.isna(value): return ""
    val_str = str(value).strip().upper()
    
    is_explicit_t = val_str.startswith("T")
    val_str = re.sub(r'^(CH-|CH\.|CH|CHANNEL-|CHANNEL|SHEET-|SHEET)', '', val_str).strip()
    
    if val_str.startswith("T"):
        is_explicit_t = True
        val_str = val_str[1:]
        
    val_str = val_str.replace("-", "").replace(" ", "")
    if val_str.endswith(".0"): val_str = val_str[:-2]
    
    cleaned = val_str.lstrip("0")
    if not cleaned: cleaned = "0"
    
    if force_t_prefix or is_explicit_t:
        return f"T{cleaned}"
    return cleaned

def parse_family_and_type(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", ""]: return "UNKNOWN", "ASSEMBLY"
    
    r_type = "ASSEMBLY"
    if any(x in text for x in ["IM", "IR", "INNER"]): r_type = "IM"
    elif any(x in text for x in ["OM", "OR", "OUTER"]): r_type = "OM"
    
    match = re.search(r'(\d{3,5})', text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    
    if "BT" in text.split() or text.startswith("BT") or "-BT" in text or " BT" in text:
        base = f"BT-{base}"
    elif "BB" in text.split() or text.startswith("BB") or "-BB" in text or " BB" in text:
        base = f"BB-{base}"
        
    return base, r_type

def clean_nan(value):
    if pd.isna(value): return 0.0
    val_str = str(value)
    match = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', val_str.replace(',', ''))
    if match: 
        return float(match.group())
    return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-", "none"]: return None
        ts = pd.to_datetime(value, dayfirst=True, errors='coerce')
        if ts is pd.NaT or pd.isna(ts): return None
        return ts.date()
    except:
        return None

def load_excel_sheets(url):
    try:
        resp = HTTP_SESSION.get(url, timeout=30)
        if resp.status_code != 200: return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        return {sheet: repair_sheet_headers(xls.parse(sheet)) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Error reading workbook stream: {e}")
        return {}

def process_master_sheets(sheets_dict, is_trb):
    ch_list = []
    for sheet_name, df in sheets_dict.items():
        if df.empty: continue
        
        clean_name = str(sheet_name).strip().upper()
        if not re.match(r'^(T|CH)[-\s]*\d+', clean_name):
            continue
            
        ch_col = find_column(df, ["channelno", "channel", "machineno", "line", "ch"])
        mo_col = find_column(df, ["mo", "mono", "order", "orderno"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        d_col = find_column(df, ["date", "day", "txndate"])
        prod_col = find_column(df, ["production", "prodqty", "shiftproduction", "qty", "quantity"])

        if not type_col: continue 

        target_cols = [c for c in [ch_col, mo_col, type_col, d_col, prod_col] if c]
        df_records = df[target_cols].to_dict('records')
        
        for row in df_records:
            c_val = row.get(ch_col) if ch_col else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.get(mo_col)).strip() if mo_col else ""
            if mo_val.upper() in ["NAN", "NONE"]: mo_val = ""
            
            prod_str = str(row.get(type_col)).strip()
            if prod_str.upper() in ["", "NAN"]: continue
            
            base_family, _ = parse_family_and_type(prod_str)
            qty = clean_nan(row.get(prod_col)) if prod_col else 0.0
            dt = parse_date_safe(row.get(d_col))

            ch_list.append({
                "ch": ch, 
                "fam": base_family, 
                "variant": prod_str, 
                "mo": mo_val, 
                "qty": qty, 
                "date": dt
            })
    return ch_list

def compile_summary_data(start_date_str=None, end_date_str=None):
    """Dynamically slices matrices. Applies dates strictly to Channel throughput, protecting Buffer inventory."""
    
    # 1. Global MO Mappings: Ensures rows don't lose their MO if Channel Qty hits 0
    if GLOBAL_CH_ROWS:
        df_mo = pd.DataFrame(GLOBAL_CH_ROWS).groupby(["ch", "fam"]).agg(
            mo_list=('mo', lambda x: ", ".join(sorted(set([str(i) for i in x if pd.notna(i) and str(i).strip()]))))
        ).reset_index()
    else:
        df_mo = pd.DataFrame(columns=["ch", "fam", "mo_list"])

    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None

    # 2. Date Filter Applies ONLY to Channel 
    filtered_ch = GLOBAL_CH_ROWS
    filtered_tb = GLOBAL_TB_ROWS # Buffer is intentionally kept unfiltered so inventory does not disappear

    if s_dt or e_dt:
        if s_dt and e_dt:
            filtered_ch = [r for r in GLOBAL_CH_ROWS if r["date"] and s_dt <= r["date"] <= e_dt]
        elif s_dt:
            filtered_ch = [r for r in GLOBAL_CH_ROWS if r["date"] and r["date"] >= s_dt]
        elif e_dt:
            filtered_ch = [r for r in GLOBAL_CH_ROWS if r["date"] and r["date"] <= e_dt]

    # 3. Group Channel Data
    if filtered_ch:
        df_ch_grouped = pd.DataFrame(filtered_ch).groupby(["ch", "fam"]).agg(
            ch_qty=('qty', 'sum'),
            ch_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            ch_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
        ).reset_index()
    else:
        df_ch_grouped = pd.DataFrame(columns=["ch", "fam", "ch_qty", "ch_min_date", "ch_max_date"])

    # 4. Group TB / SHO Data
    tb_list_parsed = []
    if filtered_tb:
        for r in filtered_tb:
            tb_list_parsed.append({
                "ch": r["ch"], "fam": r["fam"], "type": r.get("type", parse_family_and_type(r["variant"])[1]),
                "qty": r["qty"], "date": r["date"]
            })

    if tb_list_parsed:
        df_tb_grouped = pd.DataFrame(tb_list_parsed).groupby(["ch", "fam", "type"]).agg(
            tb_qty=('qty', 'sum'),
            tb_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            tb_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
        ).reset_index()
    else:
        df_tb_grouped = pd.DataFrame(columns=["ch", "fam", "type", "tb_qty", "tb_min_date", "tb_max_date"])

    if df_tb_grouped.empty and df_ch_grouped.empty:
        return []

    # 5. Strategic Merging 
    merged = pd.merge(df_tb_grouped, df_ch_grouped, on=["ch", "fam"], how="outer")
    merged = pd.merge(merged, df_mo, on=["ch", "fam"], how="left")

    compiled_summary = []
    for _, row in merged.iterrows():
        ch, fam = row["ch"], row["fam"]
        r_type = row.get("type") if pd.notna(row.get("type")) else "ASSEMBLY"
        
        tb_qty = row.get("tb_qty", 0.0)
        ch_qty = row.get("ch_qty", 0.0)
        if pd.isna(tb_qty): tb_qty = 0.0
        if pd.isna(ch_qty): ch_qty = 0.0

        tb_min, tb_max = row.get("tb_min_date"), row.get("tb_max_date")
        ch_min, ch_max = row.get("ch_min_date"), row.get("ch_max_date")
        
        # Grab locked MO reference
        mo_list = row.get("mo_list", "")
        if pd.isna(mo_list): mo_list = ""

        final_tb_qty = math.ceil(tb_qty)
        final_ch_qty = math.ceil(ch_qty)

        if final_tb_qty == 0 and final_ch_qty > 0: calc_status = "Channel Only"
        elif final_tb_qty > 0 and final_ch_qty == 0: calc_status = "Missing Channel Data"
        elif final_ch_qty >= final_tb_qty and final_tb_qty > 0: calc_status = "Completed"
        else: calc_status = "In Process"

        compiled_summary.append({
            "channel_ref": ch,
            "mo_ref": mo_list,
            "product_variant": fam,
            "ring_type": r_type,
            "sho_qty": final_tb_qty, 
            "tb_qty": final_tb_qty, 
            "sho_in": str(tb_min) if pd.notna(tb_min) and tb_min else "-",
            "tb_out": str(tb_max) if pd.notna(tb_max) and tb_max else "-",
            "ch_qty": final_ch_qty,
            "ch_in": str(ch_min) if pd.notna(ch_min) and ch_min else "-",
            "ch_out": str(ch_max) if pd.notna(ch_max) and ch_max else "-",
            "status": calc_status
        })

    compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
    return compiled_summary

def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_CH_ROWS, GLOBAL_TB_ROWS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        from settings import settings
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_ring = executor.submit(load_excel_sheets, settings.RINGWT_TRANSITBUFFER_URL)
            future_trb = executor.submit(load_excel_sheets, settings.TRB_MASTER_URL)
            future_dgbb = executor.submit(load_excel_sheets, settings.DGBB_MASTER_URL)
            
            ring_wt_sheets = future_ring.result()
            trb_sheets = future_trb.result()
            dgbb_sheets = future_dgbb.result()

        ch_list = process_master_sheets(trb_sheets, is_trb=True) + process_master_sheets(dgbb_sheets, is_trb=False)

        tb_list = []
        for sheet_name, df in ring_wt_sheets.items():
            if df.empty: continue
            
            c_col = find_column(df, ["ch#no", "ch# no", "channelref", "channel", "machineno"])
            f_col = find_column(df, ["type", "ringfamily", "family", "variant", "product"])
            d_col = find_column(df, ["date", "indate", "outdate", "day"])
            
            q_col = None
            for c in df.columns:
                if str(c).lower().replace(" ", "").replace("#", "") == "noofrings":
                    q_col = c
                    break
            if not q_col: q_col = find_column(df, ["qty", "quantity", "total"])
            
            if not f_col: continue 

            target_cols = [c for c in [c_col, f_col, d_col, q_col] if c]
            df_records = df[target_cols].to_dict('records')

            for row in df_records:
                c_val = row.get(c_col) if c_col else sheet_name
                ch = normalize_channel(c_val, force_t_prefix=False) 
                if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=False)
                
                prod_text = str(row.get(f_col)).strip()
                if prod_text.upper() in ["", "NAN"]: continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col)) if q_col else 0.0
                dt = parse_date_safe(row.get(d_col))

                tb_list.append({
                    "ch": ch, 
                    "fam": base_family, 
                    "variant": prod_text, 
                    "type": r_type, 
                    "qty": qty, 
                    "date": dt
                })

        GLOBAL_CH_ROWS = ch_list
        GLOBAL_TB_ROWS = tb_list

        MASTER_CACHE = compile_summary_data(None, None)
        LAST_REFRESH = datetime.now()

    except Exception as e:
        print(f"❌ COMPILATION FAULT: {str(e)}")
    finally:
        INITIALIZED = True 
        IS_UPDATING = False

def background_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/tbe_all_mos")
def get_tbe_dashboard(start_date: str = Query(None), end_date: str = Query(None)):
    if not INITIALIZED:
        return {"status": "initializing", "message": "Compiling data matrices...", "data": []}
    
    if start_date or end_date:
        data_slice = compile_summary_data(start_date, end_date)
    else:
        data_slice = MASTER_CACHE
        
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": data_slice}

@router.get("/tbe_variant_details")
def get_tbe_variant_details(ch: str = Query(...), fam: str = Query(...), start_date: str = Query(None), end_date: str = Query(None)):
    s_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    e_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    ch_filtered = [r for r in GLOBAL_CH_ROWS if r["ch"] == ch and r["fam"] == fam]
    tb_filtered = [r for r in GLOBAL_TB_ROWS if r["ch"] == ch and r["fam"] == fam]
    
    # Isolate date filter to target Channel only, protecting Buffer logs from hiding
    if s_dt or e_dt:
        if s_dt and e_dt:
            ch_filtered = [r for r in ch_filtered if r["date"] and s_dt <= r["date"] <= e_dt]
        elif s_dt:
            ch_filtered = [r for r in ch_filtered if r["date"] and r["date"] >= s_dt]
        elif e_dt:
            ch_filtered = [r for r in ch_filtered if r["date"] and r["date"] <= e_dt]

    found_mos = sorted(list(set([str(r["mo"]).strip() for r in ch_filtered if r.get("mo")])))
    mo_reference = ", ".join(found_mos) if found_mos else "-"
    if mo_reference != "-" and ch:
        mo_group_display = f"{mo_reference} (Ch: {ch})"
    else:
        mo_group_display = f"Ch: {ch}" if ch else mo_reference

    sho_map = {}
    tb_map = {}
    ch_map = {}

    for r in tb_filtered:
        raw_v = r["variant"]
        norm_key = str(raw_v).upper().replace("-", "").replace(" ", "")
        if not norm_key: continue
        
        if norm_key not in sho_map:
            sho_map[norm_key] = {"label": raw_v, "qty": 0.0, "dates": []}
        sho_map[norm_key]["qty"] += r["qty"]
        if r["date"]: sho_map[norm_key]["dates"].append(r["date"])

        if norm_key not in tb_map:
            tb_map[norm_key] = {"label": raw_v, "qty": 0.0, "dates": []}
        tb_map[norm_key]["qty"] += r["qty"]
        if r["date"]: tb_map[norm_key]["dates"].append(r["date"])

    for r in ch_filtered:
        raw_v = r["variant"]
        raw_mo = str(r.get("mo", "")).strip()
        norm_v = str(raw_v).upper().replace("-", "").replace(" ", "")
        if not norm_v: continue
        
        norm_key = (norm_v, raw_mo)
        
        if norm_key not in ch_map:
            ch_map[norm_key] = {"label": raw_v, "exact_mo": raw_mo, "qty": 0.0, "dates": []}
        ch_map[norm_key]["qty"] += r["qty"]
        if r["date"]: ch_map[norm_key]["dates"].append(r["date"])

    sequential_rows = []

    for k, data in sho_map.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        sequential_rows.append({
            "mo_ref": mo_group_display,
            "department": "SHO Department",
            "variant": data["label"],
            "in_date": in_d,
            "out_date": "-",  
            "qty": math.ceil(data["qty"]),
            "status": "Allocated"
        })

    for k, data in tb_map.items():
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        sequential_rows.append({
            "mo_ref": mo_group_display,
            "department": "Transit Buffer",
            "variant": data["label"],
            "in_date": "-",
            "out_date": out_d,
            "qty": math.ceil(data["qty"]),
            "status": "In Transit"
        })

    for k, data in ch_map.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        
        exact_mo = data["exact_mo"]
        if exact_mo and ch:
            ch_mo_display = f"{exact_mo} (Ch: {ch})"
        elif exact_mo:
            ch_mo_display = exact_mo
        elif ch:
            ch_mo_display = f"Ch: {ch}"
        else:
            ch_mo_display = "-"

        sequential_rows.append({
            "mo_ref": ch_mo_display,
            "department": "Channel Section",
            "variant": data["label"],
            "in_date": in_d,
            "out_date": out_d,
            "qty": math.ceil(data["qty"]),
            "status": "Completed"
        })

    return {"status": "success", "data": sequential_rows}
