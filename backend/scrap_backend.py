# scrap_backend.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import psycopg2
import os
import json
from datetime import date

router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")

class ScrapEntry(BaseModel):
    department: str
    date: date
    shift: str
    category: str
    data: List[Dict[str, Any]]

class ScrapUpdate(BaseModel):
    id: int
    payload: List[Dict[str, Any]]

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

@router.post("/api/scrap/submit")
async def submit_scrap(entry: ScrapEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # CRITICAL PROTECTION: Prevent double entries for same department, date, and shift
        cursor.execute(
            """
            SELECT id FROM scrap_history 
            WHERE department = %s AND date = %s AND shift = %s
            """,
            (entry.department, entry.date, entry.shift)
        )
        existing_record = cursor.fetchone()
        
        if existing_record:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate Alert: An entry already exists for {entry.department} on {entry.date} during {entry.shift}. Please use the 'View & Edit Saved Sheets' tab to adjust these figures."
            )

        # Proceed to insert if clear
        cursor.execute(
            "INSERT INTO scrap_history (department, date, shift, category, payload) VALUES (%s, %s, %s, %s, %s)",
            (entry.department, entry.date, entry.shift, entry.category, json.dumps(entry.data))
        )
        conn.commit()
        return {"status": "success", "message": "Scrap data saved successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to insert data: {e}")
    finally:
        cursor.close()
        conn.close()

@router.get("/api/scrap/history")
def get_scrap_history(department: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT id, department, date, shift, category, payload FROM scrap_history"
        params = []
        if department:
            query += " WHERE department = %s"
            params.append(department)
        query += " ORDER BY date DESC, shift ASC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        history_list = []
        for row in rows:
            history_list.append({
                "id": row[0],
                "department": row[1],
                "date": str(row[2]),
                "shift": row[3],
                "category": row[4],
                "payload": row[5] if isinstance(row[5], (list, dict)) else json.loads(row[5])
            })
        return {"status": "success", "data": history_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {e}")
    finally:
        cursor.close()
        conn.close()

@router.put("/api/scrap/update")
async def update_scrap(update_data: ScrapUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE scrap_history SET payload = %s WHERE id = %s",
            (json.dumps(update_data.payload), update_data.id)
        )
        conn.commit()
        return {"status": "success", "message": "Historical records updated successfully!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to modify archive records: {e}")
    finally:
        cursor.close()
        conn.close()
