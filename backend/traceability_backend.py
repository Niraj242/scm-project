from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import re
from database import get_db 
from models import TraceabilityLog 
from settings import settings  # Ensure this matches your filename

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
    Performs reconciliation using the validated settings object.
    """
    try:
        # Pydantic validates these at startup; if they are missing from 
        # your Render environment, the app will throw an error immediately 
        # instead of failing silently during the request.
        
        # Accessing validated URLs from settings:
        # settings.JOBWORK_REPORT_URL
        # settings.TRB_MASTER_URL
        # settings.DGBB_MASTER_URL
        # settings.TRACEABILITY_MASTER_URL
        
        # ... your ingestion and matching logic here ...
        
        return {"message": "Traceability synchronization completed successfully"}
    except Exception as e:
        # Returning the specific error helps you identify issues in logs
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.get("/traceability_report/{mo_number}")
def get_traceability_history(mo_number: str, db: Session = Depends(get_db)):
    """
    Retrieves the full lifecycle history for a specific MO number.
    """
    normalized_mo = normalize_mo_number(mo_number)
    # Query database for the reconciled view using normalized_mo
    return {"mo": normalized_mo, "status": "Retrieved successfully"}
