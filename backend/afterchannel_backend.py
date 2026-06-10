import os
import io
import time
from typing import Optional, List
import pandas as pd
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel

router = APIRouter()

# Environment Configurations
DATABASE_URL = os.getenv("DATABASE_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")

# Isolated Local Caches to prevent memory collision
MASTER_DATA_CACHE = {"dgbb": None, "trb": None, "last_updated": 0}
CACHE_DURATION_SECONDS = 300  # 5 Minutes cache TTL

def init_db():
    """Initializes dedicated isolated persistent storage for each department."""
    if not DATABASE_URL:
        print("Warning: DATABASE_URL environment variable is not defined.")
        return
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
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")

# Run database setup automatically on initialization
init_db()

def fetch_master_sheets():
    """Fetches and caches master production tracking spreadsheets."""
    now = time.time()
    if MASTER_DATA_CACHE["last_updated"] + CACHE_DURATION_SECONDS > now and MASTER_DATA_CACHE["dgbb"] is not None:
        return MASTER_DATA_CACHE["dgbb"], MASTER_DATA_CACHE["trb"]

    dgbb_df = pd.DataFrame()
    trb_df = pd.DataFrame()

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    if DGBB_MASTER_URL:
        try:
            r = requests.get(DGBB_MASTER_URL, headers=headers, timeout=15)
            if r.status_code == 200:
                if DGBB_MASTER_URL.endswith('.csv'):
                    dgbb_df = pd.read_csv(io.BytesIO(r.content))
                else:
                    dgbb_df = pd.read_excel(io.BytesIO(r.content))
        except Exception as e:
            print(f"Error reading DGBB Master: {e}")

    if TRB_MASTER_URL:
        try:
            r = requests.get(TRB_MASTER_URL, headers=headers, timeout=15)
            if r.status_code == 200:
                if TRB_MASTER_URL.endswith('.csv'):
                    trb_df = pd.read_csv(io.BytesIO(r.content))
                else:
                    trb_df = pd.read_excel(io.BytesIO(r.content))
        except Exception as e:
            print(f"Error reading TRB Master: {e}")

    MASTER_DATA_CACHE["dgbb"] = dgbb_df
    MASTER_DATA_CACHE["trb"] = trb_df
    MASTER_DATA_CACHE["last_updated"] = now
    return dgbb_df, trb_df

def find_mo_metadata(mo_number: str):
    """
    Scans data sheets to parse total original quantities and bearing variants.
    Standardizes casing and handles potential text format padding.
    """
    dgbb_df, trb_df = fetch_master_sheets()
    target_mo = str(mo_number).strip().lower()

    if not target_mo:
        return {"found": False, "qty": 0, "bearing_variant": "Not Found"}

    for df in [dgbb_df, trb_df]:
        if df is None or df.empty:
            continue
        
        # Normalize column maps to handle variations like 'MO No' or 'Qty'
        normalized_cols = {str(col).strip().lower(): col for col in df.columns}
        
        # Locate MO identification column
        mo_col_key = None
        for cand in ['mo number', 'mo_number', 'mo no', 'mo_no', 'mo', 'manufacturing order', 'mono']:
            if cand in normalized_cols:
                mo_col_key = normalized_cols[cand]
                break
        
        if not mo_col_key:
            continue

        # Look for matching row entries
        matched_rows = df[df[mo_col_key].astype(str).str.strip().str.lower() == target_mo]
        if not matched_rows.empty:
            target_row = matched_rows.iloc[0]
            
            # Locate quantity data target
            qty_col_key = None
            for cand in ['qty', 'quantity', 'mo qty', 'mo_qty', 'order qty', 'production qty', 'volume']:
                if cand in normalized_cols:
                    qty_col_key = normalized_cols[cand]
                    break
            
            # Locate bearing model target
            variant_col_key = None
            for cand in ['bearing', 'variant', 'bearing_variant', 'bearing variant', 'part number', 'part_number', 'model']:
                if cand in normalized_cols:
                    variant_col_key = normalized_cols[cand]
                    break

            # Parse structural metrics safely
            parsed_qty = 0
            if qty_col_key:
                try:
                    val = target_row[qty_col_key]
                    parsed_qty = float(pd.to_numeric(val, errors='coerce'))
                    if pd.isna(parsed_qty):
                        parsed_qty = 0
                except:
                    parsed_qty = 0

            parsed_variant = "Unknown"
            if variant_col_key:
                parsed_variant = str(target_row[variant_col_key]).strip()

            return {"found": True, "qty": parsed_qty, "bearing_variant": parsed_variant}
            
    return {"found": False, "qty": 0, "bearing_variant": "Not Found"}

# Data Schemas
class DepartmentEntryPayload(BaseModel):
    mo_number: str
    bearing_variant: Optional[str] = None
    quantity: float
    next_channel: Optional[str] = None
    remarks: Optional[str] = None

@router.get("/lookup-mo")
def lookup_mo(mo_number: str = Query(..., description="The MO reference string")):
    """Exposes real-time verification to prevent manual data tracking mistakes."""
    return find_mo_metadata(mo_number)

@router.get("/entries/{dept}")
def get_department_entries(dept: str = Path(..., description="Target department standard name")):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid department tracking target context.")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {dept}_entries ORDER BY id DESC;")
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/entries/{dept}")
def create_department_entry(dept: str, payload: DepartmentEntryPayload):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid department selection context.")
    
    # Fallback to master file if frontend does not send variant explicitly
    meta = find_mo_metadata(payload.mo_number)
    variant = payload.bearing_variant or (meta["bearing_variant"] if meta["found"] else "Unknown")

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {dept}_entries (mo_number, bearing_variant, quantity, next_channel, remarks)
            VALUES (%s, %s, %s, %s, %s) RETURNING *;
        """, (payload.mo_number, variant, payload.quantity, payload.next_channel, payload.remarks))
        inserted_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return inserted_row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/entries/{dept}/{entry_id}")
def update_department_entry(dept: str, entry_id: int, payload: DepartmentEntryPayload):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid department context.")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE {dept}_entries 
            SET mo_number = %s, bearing_variant = %s, quantity = %s, next_channel = %s, remarks = %s
            WHERE id = %s RETURNING *;
        """, (payload.mo_number, payload.bearing_variant, payload.quantity, payload.next_channel, payload.remarks, entry_id))
        updated_row = cursor.fetchone()
        if not updated_row:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Requested record was not found.")
        conn.commit()
        cursor.close()
        conn.close()
        return updated_row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/entries/{dept}/{entry_id}")
def delete_department_entry(dept: str, entry_id: int):
    if dept not in ["accurate", "cps", "rework", "vibration"]:
        raise HTTPException(status_code=400, detail="Invalid operational department context.")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {dept}_entries WHERE id = %s RETURNING id;", (entry_id,))
        deleted_record = cursor.fetchone()
        if not deleted_record:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Target record not located.")
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "deleted_id": entry_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
def get_master_summary_ledger():
    """
    Compiles distinct active orders and aggregates department quantities.
    Calculates total scrap summation across all four operations.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        departments = ["accurate", "cps", "rework", "vibration"]
        store = {}
        distinct_mos = set()
        
        for dept in departments:
            cursor.execute(f"SELECT * FROM {dept}_entries;")
            rows = cursor.fetchall()
            store[dept] = rows
            for r in rows:
                if r.get("mo_number"):
                    distinct_mos.add(str(r["mo_number"]).strip())
                    
        cursor.close()
        conn.close()
        
        compiled_output = []
        
        for mo in sorted(distinct_mos):
            meta = find_mo_metadata(mo)
            sheet_qty = meta["qty"] if meta["found"] else 0
            variant_name = meta["bearing_variant"] if meta["found"] else "Unknown"
            
            # Sum regular quantities per station context
            acc_total = sum(float(x["quantity"] or 0) for x in store["accurate"] if str(x["mo_number"]).strip() == mo)
            cps_total = sum(float(x["quantity"] or 0) for x in store["cps"] if str(x["mo_number"]).strip() == mo)
            rew_total = sum(float(x["quantity"] or 0) for x in store["rework"] if str(x["mo_number"]).strip() == mo)
            vib_total = sum(float(x["quantity"] or 0) for x in store["vibration"] if str(x["mo_number"]).strip() == mo)
            
            # Calculate aggregate scrap values across all 4 departments for this MO
            total_scrap_sum = 0
            for dept in departments:
                for record in store[dept]:
                    if str(record["mo_number"]).strip() == mo:
                        channel_value = str(record.get("next_channel") or "").strip().lower()
                        if channel_value == "scrap":
                            total_scrap_sum += float(record["quantity"] or 0)
            
            # Fallback for variant resolution
            if variant_name == "Unknown" or variant_name == "Not Found":
                for dept in departments:
                    for x in store[dept]:
                        if str(x["mo_number"]).strip() == mo and x.get("bearing_variant"):
                            variant_name = x["bearing_variant"]
                            break
                    if variant_name != "Unknown" and variant_name != "Not Found":
                        break

            compiled_output.append({
                "mo_number": mo,
                "bearing_variant": variant_name,
                "original_qty": sheet_qty,
                "accurate_qty": acc_total,
                "cps_qty": cps_total,
                "rework_qty": rew_total,
                "vibration_qty": vib_total,
                "scrap_sum": total_scrap_sum
            })
            
        return compiled_output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
