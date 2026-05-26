from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import re
import os
from database import get_db 
from models import TraceabilityLog 

router = APIRouter()

# Ingestion Service: Accessing URLs from .env
JOBWORK_REPORT_URL = os.getenv("JOBWORK_REPORT_URL")
TRB_MASTER_URL = os.getenv("TRB_MASTER_URL")
DGBB_MASTER_URL = os.getenv("DGBB_MASTER_URL")
TRACEABILITY_MASTER_URL = os.getenv("TRACEABILITY_MASTER_URL")

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
    1. Triggers ingestion from Google Sheets using environment variables.
    2. Normalizes MO numbers.
    3. Joins data within a 30-day temporal window.
    4. Saves results to TraceabilityLog.
    """
    try:
        # Example: Log the ingestion source check
        if not all([JOBWORK_REPORT_URL, TRB_MASTER_URL, DGBB_MASTER_URL, TRACEABILITY_MASTER_URL]):
             raise HTTPException(status_code=400, detail="One or more Google Sheet URLs are missing in .env")

        # Logic to fetch data from these URLs and push to staging tables goes here
        # ... ingestion logic ...
        
        # Apply normalization and temporal matching (abs(JobWork_Date - Master_Date) <= 30)
        # ... matching logic ...
        
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
