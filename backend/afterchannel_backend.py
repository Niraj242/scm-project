import os
import io
import re
import time
import logging
import threading
from typing import Optional, List, Dict, Any
import pandas as pd
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel, Field, validator

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# --- Global Caches & State (Thread Safe) ---
MASTER_DATA_CACHE = {
    "dgbb": pd.DataFrame(),
    "trb": pd.DataFrame(),
    "last_updated": 0.0
}
CACHE_LOCK = threading.Lock()
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 10
CACHE_TTL = CACHE_DURATION_MINUTES * 60

# Database initialization with strict handling
def init_db():
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is missing.")
        return
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        departments = ["accurate", "cps", "rework", "vibration"]
        for dept in departments:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {dept}_entries (
                    id SERIAL PRIMARY KEY,
                    mo_number VARCHAR(100) NOT NULL,
                    bearing_variant VARCHAR(255),
                    quantity NUMERIC DEFAULT 0,
                    next_channel VARCHAR(100),
                    remarks TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Create indexes for high production search performance
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{dept}_mo ON {dept}_entries (mo_number);")
        conn.commit()
        cursor.close()
        logger.info("Database tables and indexes verified successfully.")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Critical error during database initialization: {e}")
    finally:
        if conn:
            conn.close()

init_db()

# Worker function to fetch remote Excel/CSV master sheets
def fetch_remote_sheets_worker():
    global IS_UPDATING, INITIALIZED
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    dgbb_df = pd.DataFrame()
    trb_df = pd.DataFrame()

    logger.info("Starting background fetch for master Excel/CSV sheets...")
    
    if DGBB_MASTER_URL:
        try:
            r = requests.get(DGBB_MASTER_URL, headers=headers, timeout=20)
            if r.status_code == 200:
                if DGBB_MASTER_URL.endswith('.csv'):
                    dgbb_df = pd.read_csv(io.BytesIO(r.content))
                else:
                    dgbb_df = pd.read_excel(io.BytesIO(r.content))
                logger.info(f"DGBB Master sheet loaded. Rows: {len(dgbb_df)}")
            else:
                logger.error(f"DGBB Master HTTP error status code: {r.status_code}")
        except Exception as e:
            logger.error(f"Failed to fetch or parse DGBB Master URL: {e}")

    if TRB_MASTER_URL:
        try:
            r = requests.get(TRB_MASTER_URL, headers=headers, timeout=20)
            if r.status_code == 200:
                if TRB_MASTER_URL.endswith('.csv'):
                    trb_df = pd.read_csv(io.BytesIO(r.content))
                else:
                    trb_df = pd.read_excel(io.BytesIO(r.content))
                logger.info(f"TRB Master sheet loaded. Rows: {len(trb_df)}")
            else:
                logger.error(f"TRB Master HTTP error status code: {r.status_code}")
        except Exception as e:
            logger.error(f"Failed to fetch or parse TRB Master URL: {e}")

    with CACHE_LOCK:
        MASTER_DATA_CACHE["dgbb"] = dgbb_df
        MASTER_DATA_CACHE["trb"] = trb_df
        MASTER_DATA_CACHE["last_updated"] = time.time()
        INITIALIZED = True
        IS_UPDATING = False
    logger.info("Background update worker loop finished successfully.")

def trigger_cache_refresh(force: bool = False):
    global IS_UPDATING
    now = time.time()
    should_update = False
    
    with CACHE_LOCK:
        if force or (now - MASTER_DATA_CACHE["last_updated"] > CACHE_TTL):
            if not IS_UPDATING:
                IS_UPDATING = True
                should_update = True

    if should_update:
        t = threading.Thread(target=fetch_remote_sheets_worker, daemon=True)
        t.start()

# Sync execution to guarantee data availability on initial start
trigger_cache_refresh(force=True)

def find_mo_metadata(mo_number: str) -> Dict[str, Any]:
    trigger_cache_refresh(force=False)
    
    with CACHE_LOCK:
        dgbb_df = MASTER_DATA_CACHE["dgbb"].copy() if MASTER_DATA_CACHE["dgbb"] is not None else pd.DataFrame()
        trb_df = MASTER_DATA_CACHE["trb"].copy() if MASTER_DATA_CACHE["trb"] is not None else pd.DataFrame()

    target_mo = str(mo_number).strip().lower()
    if not target_mo:
        return {"found": False, "qty": 0, "bearing_variant": "Not Found"}

    mo_aliases = ['mo number', 'mo_number', 'mo no', 'mo_no', 'mo', 'manufacturing order', 'mono']
    qty_aliases = ['qty', 'quantity', 'mo qty', 'mo_qty', 'order qty', 'production qty', 'volume', 'total qty', 'prod qty']
    variant_aliases = ['bearing', 'variant', 'bearing_variant', 'bearing variant', 'part number', 'part_number', 'model', 'product']

    for df_name, df in [("DGBB", dgbb_df), ("TRB", trb_df)]:
        if df.empty:
            continue
        
        normalized_cols = {str(col).strip().lower(): col for col in df.columns}
        
        mo_col = None
        for alias in mo_aliases:
            if alias in normalized_cols:
                mo_col = normalized_cols[alias]
                break
                
        if not mo_col:
            continue

        try:
            df_str_mo = df[mo_col].astype(str).str.strip().str.lower()
            matched_rows = df[df_str_mo == target_mo]
            
            if matched_rows.empty:
                # Fallback check for safe flexible matching
                matched_rows = df[df_str_mo.apply(lambda x: bool(re.search(rf'\b{re.escape(target_mo)}\b', str(x)) if x else False))]

            if not matched_rows.empty:
                row = matched_rows.iloc[0]
                
                qty_col = None
                for alias in qty_aliases:
                    if alias in normalized_cols:
                        qty_col = normalized_cols[alias]
                        break
                        
                variant_col = None
                for alias in variant_aliases:
                    if alias in normalized_cols:
                        variant_col = normalized_cols[alias]
                        break

                parsed_qty = 0
                if qty_col:
                    val = row[qty_col]
                    parsed_qty = float(pd.to_numeric(val, errors='coerce'))
                    if pd.isna(parsed_qty):
                        parsed_qty = 0
                
                parsed_variant = "Unknown"
                if variant_col:
                    parsed_variant = str(row[variant_col]).strip()

                return {"found": True, "qty": parsed_qty, "bearing_variant": parsed_variant}
        except Exception as ex:
            logger.error(f"Error filtering target rows in sheet structure {df_name}: {ex}")

    return {"found": False, "qty": 0, "bearing_variant": "Not Found"}

# --- Pydantic Data Contracts ---
class EntryPayload(BaseModel):
    mo_number: str = Field(..., min_length=1, description="Manufacturing Order reference ID")
    bearing_variant: Optional[str] = Field(None, description="Bearing specification variant catalog marker")
    quantity: float = Field(..., ge=0, description="Process production load unit metrics")
    next_channel: Optional[str] = Field("Next Process", description="Routing destination state machine channel flags")
    remarks: Optional[str] = Field("", description="Supplemental documentation logs details annotations")

    @validator('mo_number')
    def validate_mo_clean(cls, v):
        if not v or not v.strip():
            raise ValueError("MO Number cannot be blank spaces or empty value parameters.")
        return v.strip()

@router.get("/lookup-mo")
def lookup_mo(mo_number: str = Query(..., min_length=1)):
    return find_mo_metadata(mo_number)

@router.get("/entries/{dept}")
def get_channel_entries(dept: str = Path(...)):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid manufacturing verification channel context route.")
    
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, mo_number, bearing_variant, quantity, next_channel, remarks, created_at FROM {dept}_entries ORDER BY id DESC;")
        records = cursor.fetchall()
        cursor.close()
        return records
    except Exception as e:
        logger.error(f"Database extraction failed for target tab {dept}: {e}")
        raise HTTPException(status_code=500, detail=f"Database record extraction failure: {str(e)}")
    finally:
        if conn:
            conn.close()

@router.post("/entries/{dept}")
def create_channel_entry(dept: str, payload: EntryPayload):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Target tracking table context category route lookup invalid.")
    
    meta = find_mo_metadata(payload.mo_number)
    variant = payload.bearing_variant or (meta["bearing_variant"] if meta["found"] else "Unknown")
    if variant in ["Unknown", "Not Found", "", None]:
        variant = "Unknown"

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {dept}_entries (mo_number, bearing_variant, quantity, next_channel, remarks)
            VALUES (%s, %s, %s, %s, %s) RETURNING *;
        """, (payload.mo_number, variant, payload.quantity, payload.next_channel, payload.remarks))
        row = cursor.fetchone()
        conn.commit()
        cursor.close()
        return row
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Failed to append row item record to table matrix {dept}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to append row context node: {str(e)}")
    finally:
        if conn:
            conn.close()

@router.put("/entries/{dept}/{entry_id}")
def update_channel_entry(dept: str, entry_id: int, payload: EntryPayload):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid target channel table category context configuration.")
    
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE {dept}_entries 
            SET mo_number = %s, bearing_variant = %s, quantity = %s, next_channel = %s, remarks = %s
            WHERE id = %s RETURNING *;
        """, (payload.mo_number, payload.bearing_variant, payload.quantity, payload.next_channel, payload.remarks, entry_id))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            raise HTTPException(status_code=404, detail=f"Log structural entity record with identifier reference ID {entry_id} not located.")
        conn.commit()
        cursor.close()
        return row
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Failed to execute modifications step workflow for ID {entry_id} inside {dept}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.delete("/entries/{dept}/{entry_id}")
def delete_channel_entry(dept: str, entry_id: int):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid departmental storage route parameter selection pointer.")
    
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {dept}_entries WHERE id = %s RETURNING id;", (entry_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            raise HTTPException(status_code=404, detail="Selected unique index identity reference pointer tracking point absent.")
        conn.commit()
        cursor.close()
        return {"success": True, "deleted_id": entry_id, "scope": dept}
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Row deletion exception encountered inside workflow scope mapping for row {entry_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.get("/summary")
def get_channels_summary_matrix():
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        departments = ["accurate", "cps", "rework", "vibration"]
        store = {}
        distinct_mos = set()
        
        for dept in departments:
            cursor.execute(f"SELECT mo_number, bearing_variant, quantity, next_channel FROM {dept}_entries;")
            rows = cursor.fetchall()
            store[dept] = rows
            for r in rows:
                if r.get("mo_number"):
                    distinct_mos.add(str(r["mo_number"]).strip())
                    
        cursor.close()
        compiled_output = []
        
        for mo in sorted(distinct_mos):
            meta = find_mo_metadata(mo)
            sheet_qty = meta["qty"] if meta["found"] else 0
            variant_name = meta["bearing_variant"] if meta["found"] else "Unknown"
            
            acc_total = sum(float(x["quantity"] or 0) for x in store["accurate"] if str(x["mo_number"]).strip() == mo)
            cps_total = sum(float(x["quantity"] or 0) for x in store["cps"] if str(x["mo_number"]).strip() == mo)
            rew_total = sum(float(x["quantity"] or 0) for x in store["rework"] if str(x["mo_number"]).strip() == mo)
            vib_total = sum(float(x["quantity"] or 0) for x in store["vibration"] if str(x["mo_number"]).strip() == mo)
            
            # Explicit, precise scrap aggregation counter logic block
            total_scrap_sum = 0
            for dept in departments:
                for record in store[dept]:
                    if str(record["mo_number"]).strip() == mo:
                        nxt = str(record.get("next_channel") or "").strip().lower()
                        if nxt == "scrap":
                            total_scrap_sum += float(record["quantity"] or 0)
            
            if variant_name in ["Unknown", "Not Found", ""]:
                for dept in departments:
                    for x in store[dept]:
                        if str(x["mo_number"]).strip() == mo and x.get("bearing_variant") and x["bearing_variant"] not in ["Unknown", "Not Found", ""]:
                            variant_name = x["bearing_variant"]
                            break
                    if variant_name not in ["Unknown", "Not Found", ""]:
                        break

            compiled_output.append({
                "mo_number": mo,
                "bearing_variant": variant_name if variant_name else "Unknown",
                "original_qty": sheet_qty,
                "accurate_qty": acc_total,
                "cps_qty": cps_total,
                "rework_qty": rew_total,
                "vibration_qty": vib_total,
                "scrap_sum": total_scrap_sum
            })
            
        return compiled_output
    except Exception as e:
        logger.error(f"Critical metrics compilation failure triggered inside summary aggregation layer: {e}")
        raise HTTPException(status_code=500, detail=f"Matrix metrics summary compiling loop internal error: {str(e)}")
    finally:
        if conn:
            conn.close()

@router.post("/force-refresh")
def force_refresh_cache(background_tasks: BackgroundTasks):
    trigger_cache_refresh(force=True)
    return {"message": "Background spreadsheet cache update iteration has been forcefully queued."}
