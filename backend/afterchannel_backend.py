# afterchannel_backend.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import pandas as pd

router = APIRouter()

# --- Configuration & Environment Variables ---
DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# Global Cache Registry for Dynamic Dropdown Profiles
master_data_cache = {}

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

# --- Automated Master Sheet Cache Sync ---
def load_master_data():
    global master_data_cache
    if not DGBB_MASTER_URL or not TRB_MASTER_URL:
        print("⚠️ Environment Variables DGBB_MASTER_URL or TRB_MASTER_URL are missing!")
        return

    try:
        print("🔄 Pulling live data directly from configured Google Sheet Environment URLs...")
        df_dgbb = pd.read_csv(DGBB_MASTER_URL)
        df_trb = pd.read_csv(TRB_MASTER_URL)
        
        # Merge both TRB and DGBB master entries
        df_combined = pd.concat([df_dgbb, df_trb], ignore_index=True)
        
        # Clean and standardize column names to find match profiles
        df_combined.columns = [str(col).strip().upper() for col in df_combined.columns]
        
        temp_cache = {}
        for _, row in df_combined.iterrows():
            mo = str(row.get('MO', '')).strip().upper()
            if not mo or mo == 'NAN' or mo == '': 
                continue
            
            v_type = str(row.get('TYPE', '')).strip()
            v_qty = row.get('QTY', row.get('QUANTITY', 0))
            
            try:
                v_qty = int(float(v_qty))
            except (ValueError, TypeError):
                v_qty = 0
                
            if mo not in temp_cache:
                temp_cache[mo] = []
                
            # Prevent duplicate rows from inflating recommendation options
            if not any(item['type'] == v_type for item in temp_cache[mo]):
                temp_cache[mo].append({"type": v_type, "qty": v_qty})
                
        master_data_cache = temp_cache
        print(f"✅ Successfully loaded {len(master_data_cache)} unique MO variant profiles.")
    except Exception as e:
        print(f"❌ Failed to parse Master Sheets: {str(e)}")

# Initialize data cache immediately upon server module initialization
load_master_data()

# --- API Endpoints ---

@router.get("/api/mo-lookup")
def mo_lookup(refresh: Optional[str] = None):
    """
    Exposes parsed variant datasets to the frontend.
    Pass query parameter ?refresh=true to force re-fetch the live Google Sheets.
    """
    if refresh == "true":
        load_master_data()
    return {
        "status": "success",
        "data": master_data_cache
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
