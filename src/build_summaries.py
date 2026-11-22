import time

import duckdb

from config import DUCKDB_PATH
from load_warehouse import run_sql_file

TABLES = ["sum_monthly_sales", "sum_medicine_month", "sum_pharmacy_month",
          "sum_channel_segment_month", "sum_delivery_otif", "sum_hospital_month"]

con = duckdb.connect(str(DUCKDB_PATH))
t0 = time.time()
run_sql_file(con, "40_build_summaries.sql")
print(f"Summary tables rebuilt in {time.time() - t0:.1f}s\n")
for t in TABLES:
    print(f"  {t:<28} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>8,} rows")
fact_rows = con.execute("SELECT count(*) FROM fact_pharmacy_sales").fetchone()[0]
print(f"  {'fact_pharmacy_sales':<28} {fact_rows:>8,} rows  (for comparison)")

bad = con.execute("""
    SELECT count(*) FROM (
      SELECT f.pharmacy_delivery_id FROM fact_pharmacy_sales f
      JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
      GROUP BY 1
      HAVING count(DISTINCT sp.delivery_otif_flag) > 1 OR count(DISTINCT f.source_warehouse_id) > 1
          OR count(DISTINCT f.delivery_date_key) > 1)""").fetchone()[0]
print(f"\nAssumption check: deliveries with inconsistent OTIF/warehouse/date across lines = {bad}")
con.close()