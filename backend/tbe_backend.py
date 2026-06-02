from fastapi import APIRouter
import pandas as pd
import requests
import io
import threading
import time
import re
import math
import concurrent.futures
from collections import defaultdict
from datetime import datetime

router = APIRouter()

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False  
CACHE_DURATION_MINUTES = 5

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

# MODIFIED: Extract exact float to prevent premature rounding discrepancies
def clean_float(value):
    if pd.isna(value): return 0.0
    val_str = str(value)
    match = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', val_str.replace(',', ''))
    if match: return float(match.group())
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
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        return {sheet: repair_sheet_headers(xls.parse(sheet)) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Error reading workbook stream: {e}")
        return {}

def process_master_sheets(sheets_dict, is_trb, ch_details_map):
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

        # MODIFIED: to_dict('records') is exponentially faster than iterrows()
        records = df.to_dict('records')
        for row in records:
            c_val = row.get(ch_col) if ch_col else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.get(mo_col)).strip() if mo_col else ""
            if mo_val.upper() in ["NAN", "NONE"]: mo_val = ""
            
            prod_str = str(row.get(type_col)).strip().upper()
            if prod_str in ["", "NAN"]: continue
            
            base_family, _ = parse_family_and_type(prod_str)
            qty = clean_float(row.get(prod_col)) if prod_col else 0.0
            dt = parse_date_safe(row.get(d_col))

            ch_list.append({"ch": ch, "fam": base_family, "mo": mo_val, "qty": qty, "date": dt})
            
            # Map raw details for frontend modal
            if qty > 0:
                ch_details_map[(ch, base_family)].append({
                    "source": "Channel Build", "variant": prod_str, "date": str(dt) if dt else "-", "qty": qty
                })
    return ch_list

def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        from settings import settings
        
        # MODIFIED: ThreadPoolExecutor runs downloads concurrently (Huge loading speed boost)
        urls = {
            'ring_wt': settings.RINGWT_TRANSITBUFFER_URL,
            'trb': settings.TRB_MASTER_URL,
            'dgbb': settings.DGBB_MASTER_URL
        }
        loaded_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_key = {executor.submit(load_excel_sheets, url): key for key, url in urls.items()}
            for future in concurrent.futures.as_completed(future_to_key):
                loaded_data[future_to_key[future]] = future.result()

        ring_wt_sheets = loaded_data.get('ring_wt', {})
        trb_sheets = loaded_data.get('trb', {})
        dgbb_sheets = loaded_data.get('dgbb', {})

        tb_details_map = defaultdict(list)
        ch_details_map = defaultdict(list)

        # --- STEP 1: PARSE SOURCE CHANNELS ---
        ch_list = process_master_sheets(trb_sheets, True, ch_details_map) + process_master_sheets(dgbb_sheets, False, ch_details_map)

        df_ch_grouped = pd.DataFrame(ch_list).groupby(["ch", "fam"]).agg(
            ch_qty=('qty', 'sum'), # Adding EXACT float values
            ch_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            ch_max_date=('date', lambda x: max([d for d in x if d is not None], default=None)),
            mo_list=('mo', lambda x: ", ".join(sorted(set([i for i in x if i]))))
        ).reset_index() if ch_list else pd.DataFrame(columns=["ch", "fam", "ch_qty", "ch_min_date", "ch_max_date", "mo_list"])

        # --- STEP 2: PARSE TRANSIT BUFFER DEPENDENCIES ---
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

            records = df.to_dict('records')
            for row in records:
                c_val = row.get(c_col) if c_col else sheet_name
                ch = normalize_channel(c_val, force_t_prefix=False) 
                if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=False)
                
                prod_text = str(row.get(f_col)).strip().upper()
                if prod_text in ["", "NAN"]: continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_float(row.get(q_col)) if q_col else 0.0
                dt = parse_date_safe(row.get(d_col))

                tb_list.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})
                
                if qty > 0:
                    tb_details_map[(ch, base_family, r_type)].append({
                        "source": "Transit Buffer (SHO)", "variant": prod_text, "date": str(dt) if dt else "-", "qty": qty
                    })

        df_tb_grouped = pd.DataFrame(tb_list).groupby(["ch", "fam", "type"]).agg(
            tb_qty=('qty', 'sum'),
            tb_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            tb_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
        ).reset_index() if tb_list else pd.DataFrame(columns=["ch", "fam", "type", "tb_qty", "tb_min_date", "tb_max_date"])

        # --- STEP 3: MATRIX RELATIONSHIP MERGE ---
        if df_tb_grouped.empty and df_ch_grouped.empty:
            MASTER_CACHE = []
            LAST_REFRESH = datetime.now()
            return

        merged = pd.merge(df_tb_grouped, df_ch_grouped, on=["ch", "fam"], how="outer")
        merged['tb_qty'] = merged['tb_qty'].fillna(0.0)
        merged['ch_qty'] = merged['ch_qty'].fillna(0.0)
        
        compiled_summary = []
        for row in merged.to_dict('records'):
            ch, fam = row["ch"], row["fam"]
            r_type = row.get("type") if pd.notna(row.get("type")) else "ASSEMBLY"
            
            # MODIFIED: Apply round up ONLY after grouping math is totally finished
            tb_qty = math.ceil(row["tb_qty"])
            ch_qty = math.ceil(row["ch_qty"])

            tb_min, tb_max = row.get("tb_min_date"), row.get("tb_max_date")
            ch_min, ch_max = row.get("ch_min_date"), row.get("ch_max_date")
            mo_list = row.get("mo_list", "")

            if tb_qty == 0 and ch_qty > 0: calc_status = "Channel Only"
            elif tb_qty > 0 and ch_qty == 0: calc_status = "Missing Channel Data"
            elif ch_qty >= tb_qty and tb_qty > 0: calc_status = "Completed"
            else: calc_status = "In Process"

            # Compile Raw Detail rows mapped to this specific combination
            combined_details = []
            if (ch, fam, r_type) in tb_details_map:
                combined_details.extend(tb_details_map[(ch, fam, r_type)])
            if (ch, fam) in ch_details_map:
                combined_details.extend(ch_details_map[(ch, fam)])

            compiled_summary.append({
                "channel_ref": ch,
                "mo_ref": mo_list if pd.notna(mo_list) else "",
                "product_variant": fam,
                "ring_type": r_type,
                "sho_qty": tb_qty, 
                "sho_in": str(tb_min) if pd.notna(tb_min) and tb_min else "-",
                "tb_qty": tb_qty,
                "tb_out": str(tb_max) if pd.notna(tb_max) and tb_max else "-",
                "ch_qty": ch_qty,
                "ch_in": str(ch_min) if pd.notna(ch_min) and ch_min else "-",
                "ch_out": str(ch_max) if pd.notna(ch_max) and ch_max else "-",
                "status": calc_status,
                "details": sorted(combined_details, key=lambda x: (x["date"] == "-", x["date"]))
            })

        compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
        MASTER_CACHE = compiled_summary
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
def get_tbe_dashboard():
    if not INITIALIZED:
        return {"status": "initializing", "message": "Compiling data matrices...", "data": []}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}
