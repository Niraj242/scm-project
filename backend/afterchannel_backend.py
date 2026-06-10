from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
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

# --- Pydantic Models (ALL OPTIONAL FIELDS TO ALLOW SPLIT IN/OUT LOGS) ---
# PATCH: Added optional 'id' field to all models to allow editing existing rows
class AccurateEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    pc: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

class CpsEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    item: Optional[str] = None
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    rcNo: Optional[str] = None
    materialInFrom: Optional[str] = None
    channel: Optional[str] = None
    qtyIn: Optional[int] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

class ReworkEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    channel: Optional[str] = None
    lineSegment: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    reworkActivity: Optional[str] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None

class VibrationEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    channel: Optional[str] = None
    lineSegment: Optional[str] = None
    reason: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    activity: Optional[str] = None
    ballScrap: Optional[int] = None
    cageSealScrap: Optional[int] = None
    ringType: Optional[str] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None

# --- Database Helper ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- Excel Loading Helpers ---
def find_column(df, patterns):
    cols = [str(c).strip() for c in df.columns]
    for p in patterns:
        norm_p = re.sub(r'[^a-z0-9]', '', p.lower())
        for c in cols:
            norm_c = re.sub(r'[^a-z0-9]', '', c.lower())
            if norm_c == norm_p: 
                return c
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
        return {sheet: xls.parse(sheet) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Error reading workbook stream for Afterchannel: {e}")
        return {}

def process_mo_sheets(sheets_dict, temp_cache):
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01) 
        if df.empty: continue
        
        mo_col = find_column(df, ["mo", "mono", "order", "orderno", "masterorder"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part", "material"])
        qty_col = find_column(df, ["qty", "quantity", "targetqty", "target", "orderqty", "planqty", "plannedqty", "production", "total", "reqqty", "required"])
        
        if not mo_col or not type_col: continue

        target_cols = [c for c in [mo_col, type_col, qty_col] if c]
        df_records = df[target_cols].to_dict('records')

        for row in df_records:
            mo_val = str(row.get(mo_col, "")).strip().upper()
            if not mo_val or mo_val in ["NAN", "NONE", ""]: continue
            
            type_val = str(row.get(type_col, "")).strip().upper()
            if not type_val or type_val in ["NAN", "NONE", ""]: continue

            # PATCH: Safely strip out '-' dashes and explicit NaNs to stop zeroing out Qty
            raw_qty = row.get(qty_col, 0) if qty_col else 0
            if pd.isna(raw_qty) or str(raw_qty).strip() in ['-', 'NAN', 'NONE', '']:
                raw_qty = 0
            try:
                qty_val = int(float(str(raw_qty).replace(',', '')))
            except (ValueError, TypeError):
                qty_val = 0

            if mo_val not in temp_cache:
                temp_cache[mo_val] = []
            
            variant_exists = False
            for item in temp_cache[mo_val]:
                if item['type'] == type_val:
                    item['qty'] += qty_val
                    variant_exists = True
                    break
            
            if not variant_exists:
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

threading.Thread(target=background_refresh_loop, daemon=True).start()

# --- API Endpoints ---

@router.get("/api/mo-lookup")
def mo_lookup(refresh: Optional[str] = Query(None)):
    if refresh == "true":
        process_master_data()
    if not INITIALIZED:
        return {"status": "initializing", "message": "Compiling data matrices...", "data": {}}
    return {"status": "success", "data": MASTER_DATA_CACHE}

@router.get("/api/afterchannel/summary_ledgers")
def get_summary_ledgers():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # PATCH: Selecting ALL columns so the frontend table shows data and the Scrap sum triggers correctly
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out FROM accurate_ledger")
        accurate = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, item_type, in_date, shift_in, rc_no, material_in_from, channel, qty_in, next_station, qty_sent, out_date, shift_out FROM cps_ledger")
        cps = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, channel, line_type as line_segment, material_in_from, qty_in, rework_activity, next_station, qty_sent, out_date, shift_out, operator, remark FROM rework_ledger")
        rework = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, channel, line_type as line_segment, reason, material_in_from, qty_in, activity, ball_scrap, cage_seal_scrap, ring_type, next_station, qty_sent, out_date, shift_out, operator, remark FROM vibration_dismantling_ledger")
        dismantling = cursor.fetchall()

        return {
            "status": "success",
            "data": {
                "accurate": accurate,
                "cps": cps,
                "rework": rework,
                "dismantling": dismantling
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.post("/api/afterchannel/accurate")
def submit_accurate(entry: AccurateEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None

        # PATCH: If 'id' is sent, do an UPDATE for editing. Otherwise INSERT.
        if entry.id:
            cursor.execute("""
                UPDATE accurate_ledger SET 
                mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, pc_no=%s, material_in_from=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s 
                WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO accurate_ledger (mo, bearing_type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
        conn.commit()
        return {"status": "success", "message": "Accurate entry logged"}
    except Exception as e:
        conn.rollback()
        print("DB Error:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/cps")
def submit_cps(entry: CpsEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None

        if entry.id:
            cursor.execute("""
                UPDATE cps_ledger SET 
                mo=%s, bearing_type=%s, item_type=%s, in_date=%s::date, shift_in=%s, rc_no=%s, material_in_from=%s, channel=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s 
                WHERE id=%s
            """, (entry.mo, entry.type, entry.item, in_d, entry.shiftIn, entry.rcNo, entry.materialInFrom, entry.channel, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO cps_ledger (mo, bearing_type, item_type, in_date, shift_in, rc_no, material_in_from, channel, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, entry.item, in_d, entry.shiftIn, entry.rcNo, entry.materialInFrom, entry.channel, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
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
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None

        if entry.id:
            cursor.execute("""
                UPDATE rework_ledger SET 
                mo=%s, in_date=%s::date, shift_in=%s, channel=%s, bearing_type=%s, line_type=%s, material_in_from=%s, qty_in=%s, rework_activity=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, operator=%s, remark=%s 
                WHERE id=%s
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.materialInFrom, entry.qtyIn, entry.reworkActivity, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark, entry.id))
        else:
            cursor.execute("""
                INSERT INTO rework_ledger (mo, in_date, shift_in, channel, bearing_type, line_type, material_in_from, qty_in, rework_activity, next_station, qty_sent, out_date, shift_out, operator, remark)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s)
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.materialInFrom, entry.qtyIn, entry.reworkActivity, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark))
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
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None

        if entry.id:
            cursor.execute("""
                UPDATE vibration_dismantling_ledger SET 
                mo=%s, in_date=%s::date, shift_in=%s, channel=%s, bearing_type=%s, line_type=%s, reason=%s, material_in_from=%s, qty_in=%s, activity=%s, ball_scrap=%s, cage_seal_scrap=%s, ring_type=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, operator=%s, remark=%s 
                WHERE id=%s
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.reason, entry.materialInFrom, entry.qtyIn, entry.activity, entry.ballScrap, entry.cageSealScrap, entry.ringType, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark, entry.id))
        else:
            cursor.execute("""
                INSERT INTO vibration_dismantling_ledger (mo, in_date, shift_in, channel, bearing_type, line_type, reason, material_in_from, qty_in, activity, ball_scrap, cage_seal_scrap, ring_type, next_station, qty_sent, out_date, shift_out, operator, remark)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s)
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.lineSegment, entry.reason, entry.materialInFrom, entry.qtyIn, entry.activity, entry.ballScrap, entry.cageSealScrap, entry.ringType, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark))
        conn.commit()
        return {"status": "success", "message": "Vibration entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# PATCH: Added Delete Endpoints for all 4 modules
@router.delete("/api/afterchannel/{dept}/{record_id}")
def delete_ledger_entry(dept: str, record_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        table_map = {
            "accurate": "accurate_ledger", 
            "cps": "cps_ledger", 
            "rework": "rework_ledger", 
            "vibration": "vibration_dismantling_ledger"
        }
        if dept not in table_map: raise HTTPException(status_code=400, detail="Invalid dept")
        table = table_map[dept]
        
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", (record_id,))
        conn.commit()
        return {"status": "success", "message": "Record deleted"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
