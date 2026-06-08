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

if not DATABASE_URL:
    raise ValueError("CRITICAL ERROR: DATABASE_URL environment variable is not set.")

class ScrapEntry(BaseModel):
    department: str
    date: date
    shift: str
    category: str
    data: List[Dict[str, Any]]

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

# Hardcoded absolute paths so it works instantly regardless of main.py setup
@router.post("/api/scrap/submit")
async def submit_scrap(entry: ScrapEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        insert_query = """
            INSERT INTO scrap_history (department, date, shift, category, payload) 
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            entry.department, 
            entry.date, 
            entry.shift, 
            entry.category,
            json.dumps(entry.data)
        ))
        conn.commit()
        return {"status": "success", "message": "Scrap data saved successfully!"}
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
