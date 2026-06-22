from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
import os
import pandas as pd
import requests
import io
import threading
import time
import re
from datetime import datetime

router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# --- Global Caches & State ---
MASTER_DATA_CACHE = {}
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 10

def ensure_schema():
    """Auto-injects missing scrap and component dispatch columns."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            ALTER TABLE vibration_dismantling_ledger
            ADD COLUMN IF NOT EXISTS ir_scrap INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS or_scrap INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS cage_scrap INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS ball_scrap INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS roller_scrap INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS bearing_family VARCHAR(50),
            ADD COLUMN IF NOT EXISTS remark TEXT,
            ADD COLUMN IF NOT EXISTS ir_sent INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS ir_station VARCHAR(100),
            ADD COLUMN IF NOT EXISTS or_sent INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS or_station VARCHAR(100),
            ADD COLUMN IF NOT EXISTS cage_sent INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS cage_station VARCHAR(100),
            ADD COLUMN IF NOT EXISTS roller_sent INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS roller_station VARCHAR(100);
        """)
        cursor.execute("""
            ALTER TABLE rework_ledger
            ADD COLUMN IF NOT EXISTS bearing_family VARCHAR(50);
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("Afterchannel Schema Verified: Multi-component dispatch columns synced.")
    except Exception as e:
        print(f"Schema sync notice: {e}")

@router.on_event("startup")
def startup_event():
    ensure_schema()

def parse_date(date_str):
    if not date_str or str(date_str).strip() == "":
        return None
    return date_str

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
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

class VibrationEntry(BaseModel):
    id: Optional[int] = None
    mo: str
    type: str
    bearingFamily: Optional[str] = None
    inDate: Optional[str] = None
    shiftIn: Optional[str] = None
    materialInFrom: Optional[str] = None
    qtyIn: Optional[int] = None
    ballScrap: Optional[int] = None
    rollerScrap: Optional[int] = None
    cageScrap: Optional[int] = None
    irScrap: Optional[int] = None
    orScrap: Optional[int] = None
    irSent: Optional[int] = None
    irStation: Optional[str] = None
    orSent: Optional[int] = None
    orStation: Optional[str] = None
    cageSent: Optional[int] = None
    cageStation: Optional[str] = None
    rollerSent: Optional[int] = None
    rollerStation: Optional[str] = None
    remark: Optional[str] = None
    nextStation: Optional[str] = None
    qtySent: Optional[int] = None
    outDate: Optional[str] = None
    shiftOut: Optional[str] = None

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

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def handle_auto_forward(cursor, source_dept, mo, b_type, out_date, shift_out, next_station, qty_sent):
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
        try:
            cursor.execute(f"""
                INSERT INTO {table} (mo, bearing_type, in_date, shift_in, material_in_from, qty_in)
                VALUES (%s, %s, %s::date, %s, %s, %s)
            """, (mo, b_type, out_date, shift_out, source_dept, qty_sent))
        except psycopg2.Error:
            pass 

# --- Endpoints ---
@router.get("/api/afterchannel/summary_ledgers")
def get_summary_ledgers():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT * FROM accurate_ledger")
        accurate = cursor.fetchall()
        cursor.execute("SELECT * FROM cps_ledger")
        cps = cursor.fetchall()
        cursor.execute("SELECT * FROM rework_ledger")
        rework = cursor.fetchall()
        cursor.execute("SELECT * FROM vibration_dismantling_ledger")
        dismantling = cursor.fetchall()
        cursor.execute("SELECT * FROM autopackaging_ledger")
        autopackaging = cursor.fetchall()
        cursor.execute("SELECT * FROM fps_ledger")
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
        if entry.id:
            cursor.execute("""
                UPDATE accurate_ledger SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, pc_no=%s, material_in_from=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.id))
        else:
            cursor.execute("""
                INSERT INTO accurate_ledger (mo, bearing_type, in_date, shift_in, pc_no, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.pc, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut))
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
        if entry.id:
            cursor.execute("""
                UPDATE rework_ledger SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, material_in_from=%s, qty_in=%s, next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, bearing_family=%s WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.bearingFamily, entry.id))
        else:
            cursor.execute("""
                INSERT INTO rework_ledger (mo, bearing_type, in_date, shift_in, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out, bearing_family)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::date, %s, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.bearingFamily))
            handle_auto_forward(cursor, "Rework", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
        conn.commit()
        return {"status": "success"}
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
        
        if entry.id:
            cursor.execute("""
                UPDATE vibration_dismantling_ledger 
                SET mo=%s, bearing_type=%s, in_date=%s::date, shift_in=%s, material_in_from=%s, qty_in=%s, 
                    next_station=%s, qty_sent=%s, out_date=%s::date, shift_out=%s, 
                    ir_scrap=%s, or_scrap=%s, cage_scrap=%s, ball_scrap=%s, roller_scrap=%s, bearing_family=%s, remark=%s,
                    ir_sent=%s, ir_station=%s, or_sent=%s, or_station=%s, cage_sent=%s, cage_station=%s, roller_sent=%s, roller_station=%s
                WHERE id=%s
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.irScrap, entry.orScrap, entry.cageScrap, entry.ballScrap, entry.rollerScrap, entry.bearingFamily, entry.remark, entry.irSent, entry.irStation, entry.orSent, entry.orStation, entry.cageSent, entry.cageStation, entry.rollerSent, entry.rollerStation, entry.id))
        else:
            cursor.execute("""
                INSERT INTO vibration_dismantling_ledger 
                (mo, bearing_type, in_date, shift_in, material_in_from, qty_in, next_station, qty_sent, out_date, shift_out, ir_scrap, or_scrap, cage_scrap, ball_scrap, roller_scrap, bearing_family, remark, ir_sent, ir_station, or_sent, or_station, cage_sent, cage_station, roller_sent, roller_station)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (entry.mo, entry.type, in_d, entry.shiftIn, entry.materialInFrom, entry.qtyIn, entry.nextStation, entry.qtySent, out_d, entry.shiftOut, entry.irScrap, entry.orScrap, entry.cageScrap, entry.ballScrap, entry.rollerScrap, entry.bearingFamily, entry.remark, entry.irSent, entry.irStation, entry.orSent, entry.orStation, entry.cageSent, entry.cageStation, entry.rollerSent, entry.rollerStation))
            
            # Forward Generic Main Dispatches
            handle_auto_forward(cursor, "Dismantling", entry.mo, entry.type, out_d, entry.shiftOut, entry.nextStation, entry.qtySent)
            # Forward Specific Components dynamically to target tables
            if entry.irSent and entry.irStation:
                handle_auto_forward(cursor, "Dismantling (IR Component)", entry.mo, f"{entry.type} (IR)", out_d, entry.shiftOut, entry.irStation, entry.irSent)
            if entry.orSent and entry.orStation:
                handle_auto_forward(cursor, "Dismantling (OR Component)", entry.mo, f"{entry.type} (OR)", out_d, entry.shiftOut, entry.orStation, entry.orSent)
            if entry.cageSent and entry.cageStation:
                handle_auto_forward(cursor, "Dismantling (Cage)", entry.mo, f"{entry.type} (Cage)", out_d, entry.shiftOut, entry.cageStation, entry.cageSent)
            if entry.rollerSent and entry.rollerStation:
                handle_auto_forward(cursor, "Dismantling (Roll/Ball)", entry.mo, f"{entry.type} (Roller/Ball)", out_d, entry.shiftOut, entry.rollerStation, entry.rollerSent)
        
        conn.commit()
        return {"status": "success"}
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
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
        return {"status": "success"}
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
        in_d, out_d = parse_date(entry.inDate), parse_date(entry.outDate)
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
        return {"status": "success"}
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
        table_map = {"accurate": "accurate_ledger", "cps": "cps_ledger", "rework": "rework_ledger", "vibration": "vibration_dismantling_ledger", "dismantling": "vibration_dismantling_ledger", "autopackaging": "autopackaging_ledger", "fps": "fps_ledger"}
        cursor.execute(f"DELETE FROM {table_map[dept]} WHERE id = %s", (record_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
