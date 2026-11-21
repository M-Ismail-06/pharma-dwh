import pandas as pd
import psycopg2
from config import DB, RAW, FILE_MAP, COLUMN_RENAMES


def csv_columns(prefix):
    f = next(RAW.glob(prefix + "*.csv"))
    cols = pd.read_csv(f, nrows=0).columns
    return [COLUMN_RENAMES.get(c, c).lower() for c in cols]


ddl = []

# One raw staging table per source file: all TEXT + audit columns
for prefix, table in FILE_MAP.items():
    cols = ",\n  ".join(f"{c} TEXT" for c in csv_columns(prefix))
    ddl.append(f"""
CREATE TABLE IF NOT EXISTS {table} (
  {cols},
  batch_id TEXT,
  source_file TEXT,
  load_timestamp TIMESTAMP DEFAULT now()
);""")

ddl.append("""
CREATE TABLE IF NOT EXISTS ingestion_log (
  log_id SERIAL PRIMARY KEY,
  batch_id TEXT,
  file_name TEXT,
  target_table TEXT,
  file_hash TEXT,
  file_size_mb NUMERIC(10,2),
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  duration_seconds NUMERIC(10,2),
  rows_loaded BIGINT,
  status TEXT,
  error_message TEXT
);""")

ddl.append("""
CREATE TABLE IF NOT EXISTS rejected_records (
  reject_id SERIAL PRIMARY KEY,
  batch_id TEXT,
  source_table TEXT,
  record_id TEXT,
  rule_name TEXT,
  reason TEXT,
  raw_row JSONB,
  rejected_at TIMESTAMP DEFAULT now()
);""")

ddl.append("""
CREATE TABLE IF NOT EXISTS query_log (
  query_id SERIAL PRIMARY KEY,
  query_name TEXT,
  run_label TEXT,
  executed_at TIMESTAMP DEFAULT now(),
  duration_ms NUMERIC(12,2),
  rows_returned BIGINT,
  status TEXT,
  error_message TEXT
);""")

conn = psycopg2.connect(**DB)
cur = conn.cursor()
for stmt in ddl:
    cur.execute(stmt)
conn.commit()
conn.close()
print("Staging tables created.")