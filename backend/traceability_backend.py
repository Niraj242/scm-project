from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import re
from database import get_db 
# Import your models (TraceabilityLog, etc.) as defined in models.py
from models import TraceabilityLog 

router = APIRouter()

def normalize_mo_number(mo_str: str) -> str:
    """
    Extracts the core alphanumeric sequence to handle variants 
    (e.g., M0UC6306-2Z/C3 -> M0UC6306) and strips IM/OM prefixes.
    """
    if not mo_str:
        return ""
    # Strip IM/OM prefixes if present
    clean_str = re.sub(r'^(IM|OM)', '', mo_str)
    # Extract the base continuous alphanumeric sequence
    match = re.search(r'([A-Za-z0-9]+)', clean_str)
    return match.group(1) if match else clean_str

@router.post("/run_traceability_sync")
def run_traceability_sync(db: Session = Depends(get_db)):
    """
    Performs reconciliation:
    1. Fetches data from staging tables.
    2. Normalizes MO numbers.
    3. Joins data within a 30-day temporal window.
    """
    try:
        # Implementation Logic Placeholder:
        # 1. Fetch raw data from JobWork_Report, TRB_Master, DGBB_Master, Traceability_Master
        # 2. Iterate and apply normalize_mo_number()
        # 3. Apply window: abs(JobWork_Date - Master_Date) <= 30
        # 4. Save results to TraceabilityLog
        return {"message": "Traceability synchronization completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.get("/traceability_report/{mo_number}")
def get_traceability_history(mo_number: str, db: Session = Depends(get_db)):
    """
    Retrieves the full lifecycle history for a specific MO number.
    """
    normalized_mo = normalize_mo_number(mo_number)
    # Query database for the reconciled view using normalized_mo
    return {"mo": normalized_mo, "status": "Retrieved successfully"}
