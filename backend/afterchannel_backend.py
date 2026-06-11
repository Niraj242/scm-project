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
from datetime import datetime, timedelta

router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# --- Global Caches & State ---
MASTER_DATA_CACHE = {}
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 10

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
    bearingFamily: Optional[str] = None
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    channel: Optional[str] = None
    lineType: Optional[str] = None
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
    bearingFamily: Optional[str] = None
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    channel: Optional[str] = None
    lineType: Optional[str] = None
    reason: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    activity: Optional[str] = None
    ballScrap: Optional[int] = None
    rollerScrap: Optional[int] = None
    cageScrap: Optional[int] = None
    sealScrap: Optional[int] = None
    shieldScrap: Optional[int] = None
    irScrap: Optional[int] = None
    orScrap: Optional[int] = None
    ringType: Optional[str] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None

class AutopackagingEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

class FpsEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    customerOrder: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

# --- Database Helper ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def handle_auto_forward(cursor, source_dept, mo, b_type, out_date, shift_out, next_station, qty_sent):
    """Automatically logs an 'IN' entry to the next station when a department logs an 'OUT'."""
    if not next_station or qty_sent is None or qty_sent <= 0: return
    ns_lower = next_station.lower()
    table = None
    if "rework" in ns_lower: table = "rework_ledger"
    elif "dismantling" in ns_lower or "vibration" in ns_lower: table = "vibration_dismantling_ledger"
    elif "cps" in ns_lower: table = "cps_ledger"
    elif "accurate" in ns_lower: table = "accurate_ledger"
    elif "autopackaging" in ns_lower: table = "autopackaging_ledger"
    elif "fps" in ns_lower: table = "fps_ledger"

    if table:
        cursor.execute(f"""
            INSERT INTO {table} (mo, bearing_type, in_date, shift_in, material_in_from, qty_in)
            VALUES (%s, %s, %s::date, %s, %s, %s)
        """, (mo, b_type, out_date, shift_out, source_dept, qty_sent))

# --- Excel Loading Helpers ---
def find_column(df, patterns):
    for p in patterns:
        norm_p = re.sub(r'[^a-z0-9]', '', str(p).lower())
        for orig_c in df.columns:
            norm_c = re.sub(r'[^a-z0-9]', '', str(orig_c).lower())
            if norm_c == norm_p: 
                return orig_c
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
        print(f"Error reading workbook stream for Afterchannel: {e}")
        return {}

def process_mo_sheets(sheets_dict, temp_cache):
    for sheet_name, df in sheets_dict.items():
        time.sleep(0.01) 
        if df.empty: continue
        
        mo_col = find_column(df, ["mo", "mono", "order", "orderno", "masterorder"])
        type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "desc", "family", "part", "material"])
        qty_col = find_column(df, ["production", "productionqty", "qty", "quantity", "targetqty", "target", "orderqty", "planqty", "plannedqty", "total", "reqqty", "required"])
        date_col = find_column(df, ["date"]) 
        
        if not mo_col or not type_col: continue

        target_cols = [c for c in [mo_col, type_col, qty_col, date_col] if c is not None and c in df.columns]
        df_records = df[target_cols].to_dict('records')

        for row in df_records:
            mo_val = str(row.get(mo_col, "")).strip().upper()
            if not mo_val or mo_val in ["NAN", "NONE", ""]: continue
            
            type_val = str(row.get(type_col, "")).strip().upper()
            if not type_val or type_val in ["NAN", "NONE", ""]: continue

            raw_qty = row.get(qty_col, 0) if qty_col else 0
            if pd.isna(raw_qty) or str(raw_qty).strip() in ['-', 'NAN', 'NONE', '']:
                raw_qty = 0
            try:
                qty_val = int(float(str(raw_qty).replace(',', '')))
            except (ValueError, TypeError):
                qty_val = 0

            date_str = ""
            if date_col:
                raw_date = row.get(date_col)
                if pd.notna(raw_date):
                    try:
                        if isinstance(raw_date, datetime):
                            date_str = raw_date.strftime("%Y-%m-%d")
                        else:
                            date_str = str(pd.to_datetime(raw_date).date())
                    except:
                        date_str = str(raw_date)[:10]

            if mo_val not in temp_cache:
                temp_cache[mo_val] = []
            
            variant_exists = False
            for item in temp_cache[mo_val]:
                if item['type'] == type_val:
                    item['qty'] += qty_val
                    if date_str and (not item.get('date') or date_str < item['date']):
                        item['date'] = date_str
                    variant_exists = True
                    break
            
            if not variant_exists:
                temp_cache[mo_val].append({"type": type_val, "qty": qty_val, "date": date_str})

def process_master_data():
    global MASTER_DATA_CACHE, IS_UPDATING, INITIALIZED
    if IS_UPDATING: return
    IS_UPDATING = True
    try:
        temp_cache = {}
        dgbb_sheets = load_excel_sheets(DGBB_MASTER_URL)
        trb_sheets = load_excel_sheets(TRB_MASTER_URL)
        process_mo_sheets(dgbb_sheets, temp_cache)
        process_mo_sheets(trb_sheets, temp_cache)
        MASTER_DATA_CACHE = temp_cache
    except Exception as e:
        print(f"Afterchannel Cache Compilation Fault: {str(e)}")
    finally:
        INITIALIZED = True
        IS_UPDATING = False

def background_refresh_loop():
    while True:
        try:
            process_master_data()
        except Exception as e:
            pass
        time.sleep(CACHE_DURATION_MINUTES * 60)

threading.Thread(target=background_refresh_loop, daemon=True).start()

# --- API Endpoints ---
@router.get("/api/mo-lookup")
def mo_lookup(refresh: Optional[str] = Query(None)):
    if refresh == "true": process_master_data()
    if not INITIALIZED: return {"status": "initializing", "message": "Compiling data...", "data": {}}
    return {"status": "success", "data": MASTER_DATA_CACHE}

@router.get("/api/afterchannel/summary_ledgers")
def get_summary_ledgers():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # FULLY RESTORED: Exact SQL Aliases so React tables map columns correctly
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out FROM accurate_ledger")
        accurate = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, item_type, in_date, shift_in, rc_no, material_in_from, channel, qty_in, next_station, qty_sent, out_date, shift_out FROM cps_ledger")
        cps = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, bearing_family, in_date, shift_in, channel, line_type as line_segment, material_in_from, qty_in, rework_activity, next_station, qty_sent, out_date, shift_out, operator, remark FROM rework_ledger")
        rework = cursor.fetchall()
        
        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, bearing_family, in_date, shift_in, channel, line_type as line_segment, reason, material_in_from, qty_in, activity, ball_scrap, cage_seal_scrap, roller_scrap, cage_scrap, seal_scrap, shield_scrap, ir_scrap, or_scrap, ring_type, next_station, qty_sent, out_date, shift_out, operator, remark FROM vibration_dismantling_ledger")
        dismantling = cursor.fetchall()

        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out FROM autopackaging_ledger")
        autopackaging = cursor.fetchall()

        cursor.execute("SELECT id, upper(mo) as mo, upper(bearing_type) as type, in_date, shift_in, material_in_from, qty_in, customer_order, qty_sent, out_date, shift_out FROM fps_ledger")
        fps = cursor.fetchall()

        return {
            "status": "success",
            "data": {
                "accurate": accurate, "cps": cps, "rework": rework, 
                "dismantling": dismantling, "autopackaging": autopackaging, "fps": fps
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
        if entry.id:
            cursor.execute("""
                UPDATE accurate_ledger SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, pc_no=%s, material_in_from=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO accurate_ledger (mo, bearing_type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
            
            # Auto-forward
            handle_auto_forward(cursor, "Accurate", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
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
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None
        if entry.id:
            cursor.execute("""
                UPDATE cps_ledger SET mo=%s, bearing_type=%s, item_type=%s, in_date=%s::date, shift_in=%s, rc_no=%s, material_in_from=%s, channel=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s WHERE id=%s
            """, (entry.mo, entry.type, entry.item, in_d, entry.shiftIn, entry.rcNo, entry.materialInFrom, entry.channel, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO cps_ledger (mo, bearing_type, item_type, in_date, shift_in, rc_no, material_in_from, channel, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, entry.item, in_d, entry.shiftIn, entry.rcNo, entry.materialInFrom, entry.channel, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
            
            handle_auto_forward(cursor, "CPS", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
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
                UPDATE rework_ledger SET mo=%s, in_date=%s::date, shift_in=%s, channel=%s, bearing_type=%s, bearing_family=%s, line_type=%s, material_in_from=%s, qty_in=%s, rework_activity=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, operator=%s, remark=%s WHERE id=%s
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.bearingFamily, entry.lineType, entry.materialInFrom, entry.qtyIn, entry.reworkActivity, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark, entry.id))
        else:
            cursor.execute("""
                INSERT INTO rework_ledger (mo, in_date, shift_in, channel, bearing_type, bearing_family, line_type, material_in_from, qty_in, rework_activity, next_station, qty_sent, out_date, shift_out, operator, remark)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s)
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.bearingFamily, entry.lineType, entry.materialInFrom, entry.qtyIn, entry.reworkActivity, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark))
            
            handle_auto_forward(cursor, "Rework", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
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
                UPDATE vibration_dismantling_ledger SET mo=%s, in_date=%s::date, shift_in=%s, channel=%s, bearing_type=%s, bearing_family=%s, line_type=%s, reason=%s, material_in_from=%s, qty_in=%s, activity=%s, ball_scrap=%s, roller_scrap=%s, cage_scrap=%s, seal_scrap=%s, shield_scrap=%s, ir_scrap=%s, or_scrap=%s, ring_type=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, operator=%s, remark=%s WHERE id=%s
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.bearingFamily, entry.lineType, entry.reason, entry.materialInFrom, entry.qtyIn, entry.activity, entry.ballScrap, entry.rollerScrap, entry.cageScrap, entry.sealScrap, entry.shieldScrap, entry.irScrap, entry.orScrap, entry.ringType, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark, entry.id))
        else:
            cursor.execute("""
                INSERT INTO vibration_dismantling_ledger (mo, in_date, shift_in, channel, bearing_type, bearing_family, line_type, reason, material_in_from, qty_in, activity, ball_scrap, roller_scrap, cage_scrap, seal_scrap, shield_scrap, ir_scrap, or_scrap, ring_type, next_station, qty_sent, out_date, shift_out, operator, remark)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s)
            """, (entry.mo, in_d, entry.shiftIn, entry.channel, entry.type, entry.bearingFamily, entry.lineType, entry.reason, entry.materialInFrom, entry.qtyIn, entry.activity, entry.ballScrap, entry.rollerScrap, entry.cageScrap, entry.sealScrap, entry.shieldScrap, entry.irScrap, entry.orScrap, entry.ringType, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.operator, entry.remark))
            
            handle_auto_forward(cursor, "Dismantling", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
        conn.commit()
        return {"status": "success", "message": "Dismantling entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/autopackaging")
def submit_autopackaging(entry: AutopackagingEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None
        if entry.id:
            cursor.execute("""
                UPDATE autopackaging_ledger SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, material_in_from=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO autopackaging_ledger (mo, bearing_type, in_date, shift_in, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
            handle_auto_forward(cursor, "Autopackaging", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
        conn.commit()
        return {"status": "success", "message": "Autopackaging entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/api/afterchannel/fps")
def submit_fps(entry: FpsEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        in_d = entry.inDate if entry.inDate else None
        out_d = entry.outDate if entry.outDate else None
        if entry.id:
            cursor.execute("""
                UPDATE fps_ledger SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, material_in_from=%s, qty_in=%s, customer_order=%s, qty_sent=%s, out_date=%s::date, shift_out=%s WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.customerOrder, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO fps_ledger (mo, bearing_type, in_date, shift_in, material_in_from, qty_in, customer_order, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.customerOrder, entry.qtySent, out_d, entry.shiftOut))
        conn.commit()
        return {"status": "success", "message": "FPS entry logged"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.delete("/api/afterchannel/{dept}/{record_id}")
def delete_ledger_entry(dept: str, record_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        table_map = {
            "accurate": "accurate_ledger", 
            "cps": "cps_ledger", 
            "rework": "rework_ledger", 
            "vibration": "vibration_dismantling_ledger",
            "dismantling": "vibration_dismantling_ledger",
            "autopackaging": "autopackaging_ledger",
            "fps": "fps_ledger"
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
