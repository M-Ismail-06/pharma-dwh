import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DROPZONE = ROOT / "data" / "dropzone"
PROCESSED = ROOT / "data" / "processed"
FAILED = ROOT / "data" / "failed"
DUCKDB_PATH = ROOT / "data" / "warehouse" / "pharma_dwh.duckdb"
SQL_DIR = ROOT / "sql"

# Environment variables let Airflow (inside Docker) override these later.
DB = dict(
    host=os.getenv("STAGING_HOST", "localhost"),
    port=int(os.getenv("STAGING_PORT", "5433")),
    dbname="staging",
    user="de",
    password="de",
)

API_URL = os.getenv("INGEST_API_URL", "http://localhost:8000/ingest")


# file-name prefix -> staging table
FILE_MAP = {
    "01_master_data": "stg_master_data",
    "05_pharmacy_sales_data": "stg_pharmacy_sales",
    "06_hospital_demand_data": "stg_hospital_demand",
}

# The hospital CSV has a mislabelled header (found during profiling)
COLUMN_RENAMES = {"MED003": "MedicineID"}

CHUNK_ROWS = 100_000