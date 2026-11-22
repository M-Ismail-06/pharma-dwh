import psycopg2

from config import DB, DROPZONE, PROCESSED, FAILED, DUCKDB_PATH, ROOT

if input("This deletes ALL loaded data (staging, warehouse, logs). Type YES to continue: ") != "YES":
    raise SystemExit("Cancelled.")

conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute("""TRUNCATE stg_master_data, stg_pharmacy_sales, stg_hospital_demand, ingestion_log,
               rejected_records, query_log, storage_metrics RESTART IDENTITY""")
conn.commit()
conn.close()

for p in (DUCKDB_PATH, DUCKDB_PATH.with_name(DUCKDB_PATH.name + ".wal"), ROOT / "data" / "generator_state.json"):
    p.unlink(missing_ok=True)
for folder in (DROPZONE, PROCESSED, FAILED):
    for f in folder.glob("*"):
        if f.is_file():
            f.unlink()
print("Environment reset. Trigger the DAG with config {\"initial_load\": true}.")