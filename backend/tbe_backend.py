from fastapi import APIRouter, Query
import pandas as pd
import requests
import io
import threading
import time
import re
import math
import os
from datetime import datetime, timedelta, date
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
GLOBAL_SCRAP_ROWS = []

NUM_REGEX = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
PREFIX_REGEX = re.compile(r'^(CH-|CH\.|CH|CHANNEL-|CHANNEL|SHEET-|SHEET)')
FAM_REGEX = re.compile(r'(\d{3,5})')

def format_dt(dt):
    if dt and not pd.isna(dt):
        return dt.strftime("%d-%m-%Y")
    return "-"

def safe_ceil(value):
    if pd.isna(value) or value is None: return 0
    try: return math.ceil(float(value))
    except: return 0

def clean_nan(value):
    """Force any input to a clean float number, handling commas, whitespace, and basic inline formulas (+)"""
    if pd.isna(value) or value is None: return 0.0
    val_str = str(value).replace(',', '').strip()
    if not val_str or val_str.lower() in ["nan", "none", "na"]: return 0.0
    
    # Handle cell formulas like "9+1" found in scrap logs
    if '+' in val_str:
        try:
            return sum(float(NUM_REGEX.search(p).group()) for p in val_str.split('+') if NUM_REGEX.search(p))
        except: pass

    match = NUM_REGEX.search(val_str)
    if match: return float(match.group())
    return 0.0

def repair_sheet_headers(df):
    if df.empty: return df
    targets = {"ch", "chno", "type", "noofrings", "date", "netwt", "ringwt", "qty", "quantity", "automotive", "defect", "scrap"}
    best_row_idx = -1
    max_score = 0
    
    for idx in range(min(20, len(df))):
        row_vals = [str(val).strip().lower().replace(" ", "").replace("#", "") for val in df.iloc[idx].values]
        score = sum(1 for t in targets if any(t in v for v in row_vals))
        if score > max_score:
            max_score = score
            best_row_idx = idx
            
    if max_score >= 2 and best_row_idx >= 0:
        raw_cols = df.iloc[best_row_idx].tolist()
        new_cols = []
        for i, c in enumerate(raw_cols):
            c_str = str(c).strip()
            if pd.isna(c) or c_str.lower() in ["nan", "none", ""]:
                new_cols.append(f"Unnamed_{i}")
            else:
                new_cols.append(c_str)
        
        seen = {}
        final_cols = []
        for col in new_cols:
            if col in seen:
                seen[col] += 1
                final_cols.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                final_cols.append(col)
                
        df.columns = final_cols
        return df.iloc[best_row_idx+1:].reset_index(drop=True)
        
    seen = {}
    final_cols = []
    for col in df.columns:
        col_str = str(col)
        if col_str in seen:
            seen[col_str] += 1
            final_cols.append(f"{col_str}_{seen[col_str]}")
        else:
            seen[col_str] = 0
            final_cols.append(col_str)
    df.columns = final_cols
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
    
    # 1. FIX TYPOS
    if "INDUSTRILA" in text:
        text = text.replace("INDUSTRILA", "INDUSTRIAL")
        
    # 2. STRICT AUTOMOTIVE EXCLUSION
    if "AUTOMOTIVE" in text:
        return None, None
    
    if not text or text in ["NAN", "NONE", ""]: return "UNKNOWN", "ASSEMBLY"
    
    r_type = "ASSEMBLY"
    t_norm = text.replace("-", " ").replace("_", " ").replace("/", " ")
    words = t_norm.split()
    
    # 3. IDENTIFY IM vs OM (Securely catches IR and OR suffixes)
    if any(w in ["IM", "IR", "INNER"] for w in words) or "INNER" in text or "IM" in text or "IR" in text:
        r_type = "IM"
    elif any(w in ["OM", "OR", "OUTER"] for w in words) or "OUTER" in text or "OM" in text or "OR" in text:
        r_type = "OM"
        
    # 4. EXTRACT BASE FAMILY
    match = FAM_REGEX.search(text)
    base = match.group(1) if match else text.split()[0].split('-')[0]
    
    if "BT" in words or text.startswith("BT") or "-BT" in text or " BT" in text:
        base = f"BT-{base}"
    elif "BB" in words or text.startswith("BB") or "-BB" in text or " BB" in text:
        base = f"BB-{base}"
        
    return base, r_type

def parse_date_safe(value, date_format="dd-mm-yyyy", source=None):
    try:
        if pd.isna(value) or value is None: 
            return None
            
        val_str = str(value).strip().split(' ')[0].split('T')[0]
        if val_str.lower() in ["nan", "nat", "", "-", "none", "null"]: return None

        if val_str.replace('.', '', 1).isdigit():
            val_float = float(val_str)
            if 30000 < val_float < 60000:
                return (datetime(1899, 12, 30) + timedelta(days=val_float)).date()

        val_clean = val_str.replace('/', '-').replace('.', '-')

        if source in ["tb", "ch", "scrap"]:
            if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', val_clean):
                try: return datetime.strptime(val_clean, "%Y-%m-%d").date()
                except ValueError: pass

        if date_format == "dd-mm-yyyy":
            try: return datetime.strptime(val_clean, "%d-%m-%Y").date()
            except ValueError: pass
            try: return datetime.strptime(val_clean, "%d-%m-%y").date()
            except ValueError: pass
            
            if source == "sho":
                try: return datetime.strptime(val_clean, "%Y-%d-%m").date()
                except ValueError: pass
            
            try: return datetime.strptime(val_clean, "%Y-%m-%d").date()
            except ValueError: pass

        else: 
            try: return datetime.strptime(val_clean, "%m-%d-%Y").date()
            except ValueError: pass
            try: return datetime.strptime(val_clean, "%m-%d-%y").date()
            except ValueError: pass
            try: return datetime.strptime(val_clean, "%Y-%m-%d").date()
            except ValueError: pass

        parsed = pd.to_datetime(val_str, dayfirst=(date_format == "dd-mm-yyyy"), errors='coerce')
        if pd.notna(parsed): return parsed.date()

    except Exception:
        pass
    return None

def load_excel_sheets(url):
    if not url: return {}
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        try: xls = pd.ExcelFile(content, engine='calamine')
        except: xls = pd.ExcelFile(content)
        time.sleep(0.05) 
        return {sheet: repair_sheet_headers(xls.parse(sheet, dtype=str)) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Error reading workbook stream: {e}")
        return {}

def process_master_sheets(sheets_dict, is_trb):
    ch_list = []
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01) 
        if df.empty: continue
        
        clean_name = str(sheet_name).strip().upper()
        if not re.match(r'^(T|CH)[-\s]*\d+', clean_name): continue
            
        ch_col = find_column(df, ["channelno", "channel", "machineno", "line", "ch"])
        mo_col = find_column(df, ["mo", "mono", "order", "orderno"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        d_col = find_column(df, ["date", "day", "txndate"])
        prod_col = find_column(df, ["production", "prodqty", "shiftproduction", "qty", "quantity"])

        if not type_col: continue 

        target_cols = [c for c in [ch_col, mo_col, type_col, d_col, prod_col] if c]
        for row in df[target_cols].to_dict('records'):
            prod_str = str(row.get(type_col)).strip()
            base_family, r_type = parse_family_and_type(prod_str)
            if base_family is None: continue # Excluded via Automotive check
            
            c_val = row.get(ch_col) if ch_col else sheet_name
            ch = normalize_channel(c_val, force_t_prefix=is_trb)
            if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=is_trb)
            
            mo_val = str(row.get(mo_col)).strip() if mo_col else ""
            if mo_val.upper() in ["NAN", "NONE"]: mo_val = ""
            
            qty = clean_nan(row.get(prod_col))
            dt = parse_date_safe(row.get(d_col), date_format="mm-dd-yyyy", source="ch") 
            ch_list.append({"ch": ch, "fam": base_family, "variant": prod_str, "type": r_type, "mo": mo_val, "qty": qty, "date": dt})
    return ch_list

def process_scrap_sheets(sheets_dict):
    scrap_list = []
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01)
        if df.empty: continue
        
        date_col = find_column(df, ["date", "datetime"])
        type_col = find_column(df, ["type", "variant", "part"])
        qty_col = find_column(df, ["defectqty.", "defectqty", "defectquantity", "scrapqty", "qty", "totaldefect"])
        
        if not type_col or not qty_col or not date_col: continue
        
        # 1. FORWARD-FILL DATES (Fixes the merged cell issue natively)
        df[date_col] = df[date_col].replace(['nan', 'None', '', 'NaN', 'NaT'], pd.NA).ffill()
        
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            row_str = " ".join([str(v).upper() for v in row_dict.values()])
            
            # Identify and exclude Automotive, but protect Industrial records
            if "INDUSTRILA" in row_str:
                row_str = row_str.replace("INDUSTRILA", "INDUSTRIAL")
            if "AUTO" in row_str and "INDUSTRIAL" not in row_str:
                continue

            prod_str = str(row_dict.get(type_col)).strip()
            base_family, r_type = parse_family_and_type(prod_str)
            if base_family is None: continue 
            
            qty = clean_nan(row_dict.get(qty_col))
            if qty <= 0: continue
            
            dt = parse_date_safe(row_dict.get(date_col), date_format="dd-mm-yyyy", source="scrap")
            scrap_list.append({"fam": base_family, "type": r_type, "qty": qty, "date": dt, "label": prod_str})
            
    return scrap_list

def compile_summary_data(start_date_str=None, end_date_str=None):
    s_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str and start_date_str.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str and end_date_str.strip() not in ["", "null", "None"] else None

    def apply_filter(rows):
        filtered = []
        for r in rows:
            if s_dt or e_dt:
                if not r.get("date"): continue
                if s_dt and e_dt and not (s_dt <= r["date"] <= e_dt): continue
                if s_dt and not e_dt and r["date"] < s_dt: continue
                if e_dt and not s_dt and r["date"] > e_dt: continue
            filtered.append(r)
        return filtered

    filtered_ch = apply_filter(GLOBAL_CH_ROWS)
    filtered_tb = apply_filter(GLOBAL_TB_ROWS)
    filtered_sho = apply_filter(GLOBAL_SHO_ROWS)
    filtered_scrap = apply_filter(GLOBAL_SCRAP_ROWS)

    if filtered_ch:
        df_ch_grouped = pd.DataFrame(filtered_ch).groupby(["ch", "fam"]).agg(
            ch_qty=('qty', 'sum'),
            ch_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            ch_max_date=('date', lambda x: max([d for d in x if d is not None], default=None)),
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
            tb_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
            tb_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
        ).reset_index()
    else:
        df_tb_grouped = pd.DataFrame(columns=["ch", "fam", "type", "tb_qty", "tb_min_date", "tb_max_date"])

    merged = pd.merge(df_tb_grouped, df_ch_grouped, on=["ch", "fam"], how="outer")

    base_rows = []
    for _, row in merged.iterrows():
        ch, fam = row["ch"], row["fam"]
        r_type = row.get("type") if pd.notna(row.get("type")) else "ASSEMBLY"
        mo_list = row.get("mo_list", "")
        
        base_rows.append({
            "channel_ref": ch, "mo_ref": mo_list if not pd.isna(mo_list) else "",
            "product_variant": fam, "ring_type": r_type,
            "sho_qty": 0.0, "sho_dates": [],
            "scrap_qty": 0.0,
            "tb_qty": safe_ceil(row.get("tb_qty")), 
            "tb_out": format_dt(row.get("tb_max_date")),
            "ch_qty": safe_ceil(row.get("ch_qty")),
            "ch_in": format_dt(row.get("ch_min_date")),
            "ch_out": format_dt(row.get("ch_max_date"))
        })

    orphan_records = {}
    
    for sho in filtered_sho:
        sho_fam, sho_type, sho_mo, sho_qty, sho_date = sho["fam"], sho["type"], sho["mo"], sho["qty"], sho["date"]
        candidates = [r for r in base_rows if r["product_variant"] == sho_fam and r["ring_type"] == sho_type]
        
        assigned = False
        if candidates:
            mo_candidates = [c for c in candidates if sho_mo and sho_mo in c["mo_ref"]]
            target = mo_candidates[0] if mo_candidates else candidates[0]
            target["sho_qty"] += sho_qty
            if sho_date: target["sho_dates"].append(sho_date)
            assigned = True
            
        if not assigned:
            k = (sho_fam, sho_type)
            if k not in orphan_records: orphan_records[k] = {"sho_qty": 0.0, "sho_dates": [], "scrap_qty": 0.0}
            orphan_records[k]["sho_qty"] += sho_qty
            if sho_date: orphan_records[k]["sho_dates"].append(sho_date)

    scrap_grouped = {}
    for r in filtered_scrap:
        k = (r["fam"], r["type"])
        scrap_grouped[k] = scrap_grouped.get(k, 0) + r["qty"]

    for k, sqty in scrap_grouped.items():
        fam, r_type = k
        candidates = [r for r in base_rows if r["product_variant"] == fam and r["ring_type"] == r_type]
        if candidates:
            candidates[0]["scrap_qty"] += sqty
        else:
            if k not in orphan_records: orphan_records[k] = {"sho_qty": 0.0, "sho_dates": [], "scrap_qty": 0.0}
            orphan_records[k]["scrap_qty"] += sqty

    compiled_summary = []
    for r in base_rows:
        tb_q, ch_q = r["tb_qty"], r["ch_qty"]
        if tb_q == 0 and ch_q > 0: calc_status = "Channel Only"
        elif tb_q > 0 and ch_q == 0: calc_status = "Missing Channel Data"
        elif ch_q >= tb_q and tb_q > 0: calc_status = "Completed"
        else: calc_status = "In Process"
        
        r["status"] = calc_status
        r["sho_qty"] = safe_ceil(r["sho_qty"])
        r["scrap_qty"] = safe_ceil(r["scrap_qty"])
        r["sho_in"] = format_dt(min(r["sho_dates"])) if r["sho_dates"] else "-"
        del r["sho_dates"] 
        compiled_summary.append(r)

    for k, data in orphan_records.items():
        fam, r_type = k
        compiled_summary.append({
            "channel_ref": "-", "mo_ref": "-",
            "product_variant": fam, "ring_type": r_type,
            "sho_qty": safe_ceil(data["sho_qty"]),
            "scrap_qty": safe_ceil(data.get("scrap_qty", 0.0)),
            "tb_qty": 0,
            "sho_in": format_dt(min(data["sho_dates"])) if data["sho_dates"] else "-",
            "tb_out": "-", "ch_qty": 0, "ch_in": "-", "ch_out": "-",
            "status": "SHO/Scrap Logged"
        })

    compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
    return compiled_summary

def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_CH_ROWS, GLOBAL_TB_ROWS, GLOBAL_SHO_ROWS, GLOBAL_SCRAP_ROWS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        from settings import settings
        
        od_url = getattr(settings, 'SHO_ODSCRAP_URL', os.getenv('SHO_ODSCRAP_URL', ''))
        face_url = getattr(settings, 'SHO_FACESCRAP_URL', os.getenv('SHO_FACESCRAP_URL', ''))

        with ThreadPoolExecutor(max_workers=6) as executor:
            future_ring = executor.submit(load_excel_sheets, getattr(settings, 'RINGWT_TRANSITBUFFER_URL', ''))
            future_trb = executor.submit(load_excel_sheets, getattr(settings, 'TRB_MASTER_URL', ''))
            future_dgbb = executor.submit(load_excel_sheets, getattr(settings, 'DGBB_MASTER_URL', ''))
            future_jw = executor.submit(load_excel_sheets, getattr(settings, 'JOBWORK_REPORT_URL', ''))
            future_od = executor.submit(load_excel_sheets, od_url)
            future_face = executor.submit(load_excel_sheets, face_url)
            
            ring_wt_sheets = future_ring.result()
            trb_sheets = future_trb.result()
            dgbb_sheets = future_dgbb.result()
            jw_sheets = future_jw.result()
            od_sheets = future_od.result()
            face_sheets = future_face.result()

        ch_list = process_master_sheets(trb_sheets, is_trb=True) + process_master_sheets(dgbb_sheets, is_trb=False)

        tb_list = []
        for sheet_name, df in ring_wt_sheets.items():
            time.sleep(0.01) 
            if df.empty: continue
            
            c_col = find_column(df, ["ch#no", "ch# no", "channelref", "channel", "machineno"])
            f_col = find_column(df, ["type", "ringfamily", "family", "variant", "product"])
            d_col = find_column(df, ["date", "indate", "outdate", "day"])
            q_col = next((c for c in df.columns if str(c).lower().replace(" ", "").replace("#", "") == "noofrings"), find_column(df, ["qty", "quantity", "total"]))
            
            if not f_col: continue 

            target_cols = [c for c in [c_col, f_col, d_col, q_col] if c]
            for row in df[target_cols].to_dict('records'):
                prod_str = str(row.get(f_col)).strip()
                base_family, r_type = parse_family_and_type(prod_str)
                if base_family is None: continue 
                
                c_val = row.get(c_col) if c_col else sheet_name
                ch = normalize_channel(c_val, force_t_prefix=False) 
                if not ch or ch == "0": ch = normalize_channel(sheet_name, force_t_prefix=False)
                
                qty = clean_nan(row.get(q_col))
                dt = parse_date_safe(row.get(d_col), date_format="dd-mm-yyyy", source="tb")

                tb_list.append({"ch": ch, "fam": base_family, "variant": prod_str, "type": r_type, "qty": qty, "date": dt})

        sho_list = []
        for sheet_name, df in jw_sheets.items():
            time.sleep(0.01)
            clean_sheet = str(sheet_name).strip().lower()
            if any(k in clean_sheet for k in ["summary", "pivot", "total", "history", "dash", "master"]): continue
            
            mo_col = find_column(df, ["po/prno.", "poprno", "mono", "mo", "po/prno"])
            prod_col = find_column(df, ["product", "item", "description"])
            qty_col = find_column(df, ["qtysent", "sentqty", "qty sent", "sent", "qtyapproved", "approvedqty", "shoqty", "qty"])
            date_col = find_column(df, ["jwchallandate", "challandate", "date", "jwdate"])
            
            if not mo_col: continue
            
            target_cols = [c for c in [mo_col, prod_col, qty_col, date_col] if c]
            for row in df[target_cols].to_dict('records'):
                prod_str = str(row.get(prod_col, ""))
                base_fam, comp_type = parse_family_and_type(prod_str)
                if base_fam is None: continue 
                
                raw_mo = str(row.get(mo_col, "")).strip().upper().replace(" ", "")
                if raw_mo.endswith(".0"): raw_mo = raw_mo[:-2]
                if not raw_mo or raw_mo in ["NAN", "NONE", "NA"]: continue
                
                sho_qty = clean_nan(row.get(qty_col))
                sho_date = parse_date_safe(row.get(date_col), date_format="dd-mm-yyyy", source="sho")
                
                if sho_qty > 0:
                    sho_list.append({"mo": raw_mo, "fam": base_fam, "type": comp_type, "qty": sho_qty, "date": sho_date, "label": prod_str})

        GLOBAL_CH_ROWS = ch_list
        GLOBAL_TB_ROWS = tb_list
        GLOBAL_SHO_ROWS = sho_list
        
        # Build Scrap Data using our isolated processor
        GLOBAL_SCRAP_ROWS = process_scrap_sheets(od_sheets) + process_scrap_sheets(face_sheets)

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
    if not INITIALIZED:
        return {"status": "initializing", "message": "Compiling data matrices...", "data": []}
    
    if start_date or end_date:
        return {"status": "success", "last_updated": str(LAST_REFRESH), "data": compile_summary_data(start_date, end_date)}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/tbe_variant_details")
def get_tbe_variant_details(ch: str = Query(...), fam: str = Query(...), start_date: str = Query(None), end_date: str = Query(None)):
    s_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date and start_date.strip() not in ["", "null", "None"] else None
    e_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date and end_date.strip() not in ["", "null", "None"] else None

    def apply_filter(rows):
        filtered = []
        for r in rows:
            if r.get("fam") != fam: continue
            if "ch" in r and r["ch"] != ch: continue 
            if s_dt or e_dt:
                if not r["date"]: continue
                if s_dt and e_dt and not (s_dt <= r["date"] <= e_dt): continue
                if s_dt and not e_dt and r["date"] < s_dt: continue
                if e_dt and not s_dt and r["date"] > e_dt: continue
            filtered.append(r)
        return filtered

    ch_f = apply_filter(GLOBAL_CH_ROWS)
    tb_f = apply_filter(GLOBAL_TB_ROWS)
    sho_f = apply_filter(GLOBAL_SHO_ROWS)
    scrap_f = apply_filter(GLOBAL_SCRAP_ROWS)

    found_mos = sorted(list(set([str(r["mo"]).strip() for r in ch_f if r.get("mo")])))
    mo_reference = ", ".join(found_mos) if found_mos else "-"
    mo_group_display = f"{mo_reference} (Ch: {ch})" if (mo_reference != "-" and ch) else (f"Ch: {ch}" if ch else mo_reference)

    sho_map, tb_map, ch_map, mo_summary_map, scrap_map = {}, {}, {}, {}, {}

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

    for r in scrap_f:
        norm_key = str(r["label"]).upper().replace("-", "").replace(" ", "")
        if not norm_key: continue
        if norm_key not in scrap_map: scrap_map[norm_key] = {"label": r["label"], "qty": 0.0, "dates": []}
        scrap_map[norm_key]["qty"] += r["qty"]
        if r["date"]: scrap_map[norm_key]["dates"].append(r["date"])

    sequential_rows = []
    for k, data in sho_map.items():
        sequential_rows.append({"mo_ref": mo_group_display, "department": "SHO Department", "variant": data["label"], "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": "-", "qty": safe_ceil(data["qty"]), "status": "Allocated"})

    for k, data in scrap_map.items():
        sequential_rows.append({"mo_ref": mo_group_display, "department": "Scrap (OD/Face)", "variant": data["label"], "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": "-", "qty": safe_ceil(data["qty"]), "status": "Scrapped"})

    for k, data in tb_map.items():
        sequential_rows.append({"mo_ref": mo_group_display, "department": "Transit Buffer", "variant": data["label"], "in_date": "-", "out_date": format_dt(max(data["dates"])) if data["dates"] else "-", "qty": safe_ceil(data["qty"]), "status": "In Transit"})
        
    for exact_mo, data in mo_summary_map.items():
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo and ch else (exact_mo if exact_mo else (f"Ch: {ch}" if ch else "-"))
        sequential_rows.append({"mo_ref": ch_mo_display, "department": "Channel (MO Summary)", "variant": "ALL VARIANTS", "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": format_dt(max(data["dates"])) if data["dates"] else "-", "qty": safe_ceil(data["qty"]), "status": "MO Total"})

    for k, data in ch_map.items():
        exact_mo = data["exact_mo"]
        ch_mo_display = f"{exact_mo} (Ch: {ch})" if exact_mo and ch else (exact_mo if exact_mo else (f"Ch: {ch}" if ch else "-"))
        sequential_rows.append({"mo_ref": ch_mo_display, "department": "Channel Section", "variant": data["label"], "in_date": format_dt(min(data["dates"])) if data["dates"] else "-", "out_date": format_dt(max(data["dates"])) if data["dates"] else "-", "qty": safe_ceil(data["qty"]), "status": "Completed"})

    return {"status": "success", "data": sequential_rows}
