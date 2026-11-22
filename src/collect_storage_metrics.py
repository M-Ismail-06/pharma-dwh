from datetime import datetime

import duckdb
import psycopg2

from config import DB, DUCKDB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS storage_metrics (
  metric_id SERIAL PRIMARY KEY, captured_at TIMESTAMP, layer TEXT, table_name TEXT, domain TEXT,
  row_count BIGINT, size_mb NUMERIC(12,2), min_date DATE, max_date DATE, size_basis TEXT);
CREATE OR REPLACE VIEW v_storage_latest AS
  SELECT * FROM storage_metrics WHERE captured_at = (SELECT max(captured_at) FROM storage_metrics);
"""

PG_TABLES = {   # table: (domain, date column or None)
    "stg_master_data": ("Master data", "effectivefromdate"),
    "stg_pharmacy_sales": ("Pharmacy sales", "salesdate"),
    "stg_hospital_demand": ("Hospital demand", "demandmonth"),
    "ingestion_log": ("Pipeline logs", None),
    "rejected_records": ("Pipeline logs", None),
    "query_log": ("Pipeline logs", None),
}
DUCK_TABLES = {
    "dim_date": "Shared dimensions", "dim_geography": "Shared dimensions", "dim_medicine": "Master data",
    "dim_pharmacy": "Pharmacy sales", "dim_sales_profile": "Pharmacy sales", "fact_pharmacy_sales": "Pharmacy sales",
    "dim_hospital": "Hospital demand", "dim_demand_flags": "Hospital demand", "fact_hospital_demand": "Hospital demand",
    "sum_monthly_sales": "Pharmacy sales", "sum_medicine_month": "Pharmacy sales",
    "sum_pharmacy_month": "Pharmacy sales", "sum_channel_segment_month": "Pharmacy sales",
    "sum_delivery_otif": "Pharmacy sales", "sum_hospital_month": "Hospital demand",
}
FACT_DATES = {"fact_pharmacy_sales": "sales_date_key", "fact_hospital_demand": "demand_month_date_key"}

now = datetime.now()
rows = []

pg = psycopg2.connect(**DB)
cur = pg.cursor()
cur.execute(DDL)
for table, (domain, datecol) in PG_TABLES.items():
    if datecol:
        cur.execute(f"SELECT count(*), min(safe_date({datecol})), max(safe_date({datecol})) FROM {table}")
        n, mn, mx = cur.fetchone()
    else:
        cur.execute(f"SELECT count(*) FROM {table}")
        n, mn, mx = cur.fetchone()[0], None, None
    cur.execute("SELECT pg_total_relation_size(%s)", (table,))
    mb = cur.fetchone()[0] / 1_048_576
    rows.append((now, "staging (Postgres)", table, domain, n, round(mb, 2), mn, mx, "exact"))

d = duckdb.connect(str(DUCKDB_PATH), read_only=True)
existing = {r[0] for r in d.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
block = d.execute("SELECT block_size FROM pragma_database_size()").fetchone()[0]
for table, domain in DUCK_TABLES.items():
    if table not in existing:
        continue
    n = d.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    blocks = d.execute(f"SELECT count(DISTINCT block_id) FROM pragma_storage_info('{table}') "
                       f"WHERE block_id IS NOT NULL").fetchone()[0]
    mn = mx = None
    if table in FACT_DATES:
        mn, mx = d.execute(f"SELECT min(dd.full_date), max(dd.full_date) FROM {table} f "
                           f"JOIN dim_date dd ON dd.date_key = f.{FACT_DATES[table]}").fetchone()
    rows.append((now, "warehouse (DuckDB)", table, domain, n, round(blocks * block / 1_048_576, 2), mn, mx, "approx"))
d.close()
rows.append((now, "warehouse file", "pharma_dwh.duckdb (whole file)", "Warehouse file total", None,
             round(DUCKDB_PATH.stat().st_size / 1_048_576, 2), None, None, "exact"))

cur.executemany("""INSERT INTO storage_metrics
  (captured_at, layer, table_name, domain, row_count, size_mb, min_date, max_date, size_basis)
  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
pg.commit()
pg.close()

print(f"{'layer':<20}{'table':<34}{'rows':>10}{'MB':>9}   dates")
for r in rows:
    print(f"{r[1]:<20}{r[2]:<34}{(r[4] if r[4] is not None else 0):>10,}{float(r[5]):>9.2f}   {r[6] or ''} {r[7] or ''}")