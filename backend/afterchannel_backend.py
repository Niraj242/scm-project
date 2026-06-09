# afterchannel_backend.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")

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

# --- Helper Function for DB Connections ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- API Endpoints ---
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
