# afterchannel_backend.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import psycopg2
import os
import pandas as pd
import requests
import io
import threading
import time
import re

router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# --- Global Caches & State ---
MASTER_DATA_CACHE = {}
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 10

# --- Pydantic Models ---
class AccurateEntry(BaseModel):
    mo: str
    type: str
    inDate: str
    shiftIn: str
    pc: str
    materialInFrom: str
    qtyIn: int
    nextStation: str
    qtySent: int
    outDate: Optional[str] = None
    shiftOut: str

class CpsEntry(BaseModel):
    mo: str
    type: str
    item: str
    inDate: str
    shiftIn: str
    rcNo: str
    materialInFrom: str
    channel: str
    qtyIn: int
    nextStation: str
    qtySent: int
    outDate: Optional[str] = None
    shiftOut: str

class ReworkEntry(BaseModel):
    mo: str
    inDate: str
    shiftIn: str
    channel: str
    type: str
    materialInFrom: str
    qtyIn: int
    reworkActivity: str
    nextStation: str
    qtySent: int
    outDate: Optional[str] = None
    shiftOut: str
    operator: Optional[str] = None
    remark: Optional[str] = None
    lineSegment: str

class VibrationEntry(BaseModel):
    mo: str
    inDate: str
    shiftIn: str
    channel: str
    type: str
    reason: str
    materialInFrom: str
    qtyIn: int
    activity: str
    ballScrap: Optional[int] = 0
    cageSealScrap: Optional[int] = 0
    ringType: str
    nextStation: str
    qtySent: int
    outDate: Optional[str] = None
    shiftOut: str
    operator: Optional[str] = None
    remark: Optional[str] = None
    lineSegment: str

# --- Database Helper ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- Excel Loading Helpers (Adapted from TBE) ---
def find_column(df, patterns):
    cols = [str(c).strip() for c in df.columns]
    for p in patterns:
        norm_p = p.lower().replace(" ", "").replace("_", "").replace("#", "")
        for c in cols:
            norm_c = c.lower().replace(" ", "").replace("_", "").replace("#", "")
            if norm_c == norm_p: return c
    return None

def load_excel_sheets(url):
    if not url: return {}
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200: return {}
        content = io.BytesIO(resp.content)
        try:
            xls = pd.ExcelFile(content, engine='calamine')
        except ImportError:
            xls = pd.ExcelFile(content)
        time.sleep(0.05)
        # Parse all sheets
        return {sheet: xls.parse(sheet) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Error reading workbook stream for Afterchannel: {e}")
        return {}

def process_mo_sheets(sheets_dict, temp_cache):
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01) # Yield CPU
        if df.empty: continue
        
        # Find necessary columns regardless of exact naming
        mo_col = find_column(df, ["mo", "mono", "order", "orderno"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part"])
        qty_col = find_column(df, ["qty", "quantity", "prodqty", "production", "total"])

        if not mo_col or not type_col: continue

        target_cols = [c for c in [mo_col, type_col, qty_col] if c]
        df_records = df[target_cols].to_dict('records')

        for row in df_records:
            mo_val = str(row.get(mo_col, "")).strip().upper()
            if not mo_val or mo_val in ["NAN", "NONE", ""]: continue
            
            type_val = str(row.get(type_col, "")).strip()
            if not type_val or type_val.upper() in ["NAN", "NONE", ""]: continue

            raw_qty = row.get(qty_col, 0) if qty_col else 0
            try:
                qty_val = int(float(str(raw_qty).replace(',', '')))
            except (ValueError, TypeError):
                qty_val = 0

            if mo_val not in temp_cache:
                temp_cache[mo_val] = []
            
            # Avoid duplicate variants for the same MO
            if not any(item['type'] == type_val for item in temp_cache[mo_val]):
                temp_cache[mo_val].append({"type": type_val, "qty": qty_val})

# --- Background Task ---
def process_master_data():
    global MASTER_DATA_CACHE, IS_UPDATING, INITIALIZED
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        temp_cache = {}
        print("🔄 Afterchannel: Fetching Excel streams...")
        
        dgbb_sheets = load_excel_sheets(DGBB_MASTER_URL)
        trb_sheets = load_excel_sheets(TRB_MASTER_URL)

        process_mo_sheets(dgbb_sheets, temp_cache)
        process_mo_sheets(trb_sheets, temp_cache)

        MASTER_DATA_CACHE = temp_cache
        print(f"✅ Afterchannel: Successfully mapped {len(MASTER_DATA_CACHE)} unique MOs.")
    except Exception as e:
        print(f"❌ Afterchannel Cache Compilation Fault: {str(e)}")
    finally:
        INITIALIZED = True
        IS_UPDATING = False

def background_refresh_loop():
    while True:
        try:
            process_master_data()
        except Exception as e:
            print(f"Afterchannel Background thread error: {e}")
        time.sleep(CACHE_DURATION_MINUTES * 60)

# Start the background thread immediately
threading.Thread(target=background_refresh_loop, daemon=True).start()

# --- API Endpoints ---

@router.get("/api/mo-lookup")
def mo_lookup(refresh: Optional[str] = Query(None)):
    if refresh == "true":
        # Run synchronous update if forced
        process_master_data()
    
    if not INITIALIZED:
        return {"status": "initializing", "message": "Compiling data matrices...", "data": {}}

    return {
        "status": "success",
        "data": MASTER_DATA_CACHE
    }

@router.post("/api/afterchannel/accurate")
def submit_accurate(entry: AccurateEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO accurate_ledger (mo, bearing_type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out)
            VALUES (%s, %s, NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date, %s)
        """, (entry.mo, entry.type, entry.inDate, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, entry.outDate, entry.shiftOut))
        conn.commit()
        return {"status": "success", "message": "Accurate entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/cps")
def submit_cps(entry: CpsEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO cps_ledger (mo, bearing_type, item_type, in_date, shift_in, rc_no, material_in_from, channel, qty_in, next_station, qty_sent, out_date, shift_out)
            VALUES (%s, %s, %s, NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date, %s)
        """, (entry.mo, entry.type, entry.item, entry.inDate, entry.shiftIn, entry.rcNo, entry.materialInFrom, entry.channel, entry.qtyIn, entry.nextStation, entry.qtySent, entry.outDate, entry.shiftOut))
        conn.commit()
        return {"status": "success", "message": "CPS entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/rework")
def submit_rework(entry: ReworkEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO rework_ledger (mo, in_date, shift_in, channel, bearing_type, line_type, material_in_from, qty_in, rework_activity, next_station, qty_sent, out_date, shift_out, operator, remark)
            VALUES (%s, NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date, %s, %s, %s)
        """, (entry.mo, entry.inDate, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.materialInFrom, entry.qtyIn, entry.reworkActivity, entry.nextStation, entry.qtySent, entry.outDate, entry.shiftOut, entry.operator, entry.remark))
        conn.commit()
        return {"status": "success", "message": "Rework entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/vibration")
def submit_vibration(entry: VibrationEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO vibration_dismantling_ledger (mo, in_date, shift_in, channel, bearing_type, line_type, reason, material_in_from, qty_in, activity, ball_scrap, cage_seal_scrap, ring_type, next_station, qty_sent, out_date, shift_out, operator, remark)
            VALUES (%s, NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date, %s, %s, %s)
        """, (entry.mo, entry.inDate, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.reason, entry.materialInFrom, entry.qtyIn, entry.activity, entry.ballScrap, entry.cageSealScrap, entry.ringType, entry.nextStation, entry.qtySent, entry.outDate, entry.shiftOut, entry.operator, entry.remark))
        conn.commit()
        return {"status": "success", "message": "Vibration entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
