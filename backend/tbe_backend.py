import os
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# ---------------------------------------------------------
# CORS MIDDLEWARE (Fixes the "Failed to fetch" React error)
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Fetch the Excel URL from .env
RINGWT_TRANSITBUFFER_URL = os.getenv("RINGWT_TRANSITBUFFERE_URL")

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def clean_channel(ch_string):
    """Extracts only the number from 'CH-03', 'CH-5', 'T-3' for exact matching."""
    if pd.isna(ch_string):
        return None
    match = pd.Series(str(ch_string).upper()).str.extract(r'(\d+)')[0].values
    if len(match) > 0 and pd.notna(match[0]):
        return str(match[0])
    return str(ch_string)

def extract_family(type_string):
    """Extracts the base numerical family (e.g., OM62132rs -> 62132)."""
    if pd.isna(type_string):
        return ""
    match = pd.Series(str(type_string)).str.extract(r'(\d{3,})')[0].values
    if len(match) > 0 and pd.notna(match[0]):
        return str(match[0])
    return str(type_string)

def get_processed_tbe_data():
    """Fetches Excel, cleans data, and groups by Date Proximity."""
    if not RINGWT_TRANSITBUFFER_URL:
        raise ValueError("RINGWT_TRANSITBUFFERE_URL is missing in environment variables.")

    try:
        # 1. Load Data
        df = pd.read_excel(RINGWT_TRANSITBUFFER_URL)
        df.columns = df.columns.str.strip() 
        
        # 2. Standardize Columns
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']) 
        
        df['Clean_Channel'] = df['Ch#'].apply(clean_channel)
        df['Base_Family'] = df['TYPE'].apply(extract_family)
        
        # 3. DATE PROXIMITY LOGIC (Group closer dates together)
        # Sort sequentially by Channel -> Family -> Date
        df = df.sort_values(by=['Clean_Channel', 'Base_Family', 'Date'])
        
        # Calculate days between the current row and the previous row for the same Channel+Family
        df['Date_Diff'] = df.groupby(['Clean_Channel', 'Base_Family'])['Date'].diff().dt.days
        
        # If the gap is greater than 10 days, consider it a NEW Production Run
        df['New_Run_Flag'] = (df['Date_Diff'].fillna(0) > 10).astype(int)
        
        # Cumulative sum creates a unique Run ID (0, 1, 2...) for isolated date clusters
        df['Run_ID'] = df.groupby(['Clean_Channel', 'Base_Family'])['New_Run_Flag'].cumsum()
        
        # 4. GENERATE THE MO NUMBER
        # Format: MO-CH[Channel]-[Family]-R[Run_ID] (e.g., MO-CH3-6306-R1)
        df['Generated_MO'] = "MO-CH" + df['Clean_Channel'].astype(str) + "-" + df['Base_Family'].astype(str) + "-R" + (df['Run_ID'] + 1).astype(str)
        
        # Clean up NaNs for JSON serialization
        df = df.fillna(0)
        
        return df
    except Exception as e:
        print(f"Error processing TBE data: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------
# ENDPOINT 1: SUMMARY DASHBOARD (ALL MOs)
# ---------------------------------------------------------
@app.get("/tbe_all_mos")
def get_tbe_summary():
    df = get_processed_tbe_data()
    
    if df.empty:
        return {"status": "error", "message": "Failed to fetch or parse TBE pipeline."}

    # Group by the dynamically generated MO and sum the metrics
    agg_funcs = {
        'Clean_Channel': 'first',
        'Base_Family': 'first',
        'TYPE': 'first',
        'No Of Rings': 'sum',
        'Net Wt': 'sum',
        'Date': ['min', 'max']
    }
    
    grouped = df.groupby('Generated_MO').agg(agg_funcs).reset_index()
    grouped.columns = ['mo', 'channel', 'family', 'component', 'total_rings', 'total_net_wt', 'first_scan', 'last_scan']
    
    payload = []
    for _, row in grouped.iterrows():
        if row['total_rings'] <= 0:
            continue
            
        payload.append({
            "mo": row['mo'],
            "channel": row['channel'],
            "base_product": row['family'],
            "component_type": row['component'],
            "total_rings": int(row['total_rings']),
            "total_net_weight": round(float(row['total_net_wt']), 2),
            "in_date": row['first_scan'].strftime('%Y-%m-%d') if pd.notna(row['first_scan']) and row['first_scan'] != 0 else '-',
            "out_date": row['last_scan'].strftime('%Y-%m-%d') if pd.notna(row['last_scan']) and row['last_scan'] != 0 else '-',
            "status": "completed"
        })
        
    # Sort payload so channels display sequentially
    payload = sorted(payload, key=lambda x: (x['channel'], x['base_product']))
        
    return {"status": "success", "data": payload}


# ---------------------------------------------------------
# ENDPOINT 2: DETAILED MO DRILLDOWN
# ---------------------------------------------------------
@app.get("/tbe_report/{mo_id}")
def get_tbe_detail(mo_id: str):
    df = get_processed_tbe_data()
    
    if df.empty:
        return {"status": "error", "message": "Pipeline unavailable."}
        
    # Filter the dataframe to only show rows for the clicked MO
    filtered_df = df[df['Generated_MO'] == mo_id.strip()]

    rows = []
    for _, row in filtered_df.iterrows():
        rows.append({
            "department": f"Channel {row['Clean_Channel']}",
            "product": row['TYPE'] if row['TYPE'] != 0 else '-',
            "date": row['Date'].strftime('%Y-%m-%d') if row['Date'] != 0 else '-',
            "shift": row['Shift'] if row['Shift'] != 0 else '-',
            "gross_weight": float(row['Gr Wt']) if row['Gr Wt'] != 0 else 0,
            "net_weight": float(row['Net Wt']) if row['Net Wt'] != 0 else 0,
            "ring_weight": float(row['Ring Wt']) if row['Ring Wt'] != 0 else 0,
            "rings": int(row['No Of Rings']) if row['No Of Rings'] != 0 else 0,
            "status": "completed" if row['No Of Rings'] != 0 else "pending"
        })

    return {
        "status": "success",
        "data": {
            "mo": mo_id,
            "rows": rows
        }
    }
