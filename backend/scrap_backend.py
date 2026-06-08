# scrap_backend.py
# Requirements: pip install fastapi uvicorn psycopg2-binary pydantic python-dotenv

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import psycopg2
import os
from datetime import date

app = FastAPI()

# Make sure to set your Neon DB connection string in Render environment variables as DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@ep-cool-snowflake-123456.us-east-2.aws.neon.tech/neondb")

class ScrapEntry(BaseModel):
    department: str
    date: date
    shift: str
    category: str # Industrial or Automobile
    data: List[Dict[str, Any]] # The row data from the tables

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

@app.post("/api/scrap/submit")
async def submit_scrap(entry: ScrapEntry):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Example query - you will adjust this later when we design the specific database tables
        # For now, it confirms the backend successfully receives the complex JSON from React
        insert_query = """
            INSERT INTO scrap_history (department, date, shift, category, payload) 
            VALUES (%s, %s, %s, %s, %s)
        """
        import json
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

# Run locally using: uvicorn scrap_backend:app --reload
