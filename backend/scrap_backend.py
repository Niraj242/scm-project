# scrap_backend.py
# Requirements: pip install fastapi uvicorn psycopg2-binary pydantic python-dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import psycopg2
import os
import uvicorn
from datetime import date
from dotenv import load_dotenv

# Load environment variables from a .env file if running locally
load_dotenv()

app = FastAPI()

# --- CORS CONFIGURATION ---
# This allows your Vercel frontend to successfully fetch data from your Render backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # NOTE: For better security later, replace "*" with ["https://your-vercel-domain.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Securely fetch the database URL from the environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Fail fast if the environment variable is missing
if not DATABASE_URL:
    raise ValueError("CRITICAL ERROR: DATABASE_URL environment variable is not set. Please configure it in Render/Vercel or your local .env file.")

class ScrapEntry(BaseModel):
    department: str
    date: date
    shift: str
    category: str # Industrial or Automotive
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

# --- RENDER PORT BINDING FIX ---
if __name__ == "__main__":
    # Render assigns a port dynamically via the PORT environment variable
    # If it's not found (like when running locally), it defaults to 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("scrap_backend:app", host="0.0.0.0", port=port)
