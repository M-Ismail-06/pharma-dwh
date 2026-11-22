import duckdb
import psycopg2
import pandas as pd
from config import DB, DUCKDB_PATH

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
pg = psycopg2.connect(**DB).cursor()


def stg(sql):
    pg.execute(sql)
    return pg.fetchone()


def q(sql):
    return con.execute(sql).fetchdf()


def line(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}")


print("== Reconciliation with validated staging ==")
s_rows, s_net = stg("SELECT count(*), sum(netsalesamountusd::numeric) FROM stg_pharmacy_sales WHERE validation_status='valid'")
f_rows, f_net = con.execute("SELECT count(*), sum(net_sales_usd) FROM fact_pharmacy_sales").fetchone()
line("sales row count", s_rows == f_rows, f"staging={s_rows:,} warehouse={f_rows:,}")
line("sales net amount", abs(float(s_net) - float(f_net)) < 0.5, f"staging={float(s_net):,.2f} warehouse={float(f_net):,.2f}")
h_rows, = stg("SELECT count(*) FROM stg_hospital_demand WHERE validation_status='valid'")
fh_rows, = con.execute("SELECT count(*) FROM fact_hospital_demand").fetchone()
line("hospital row count", h_rows == fh_rows, f"staging={h_rows:,} warehouse={fh_rows:,}")

print("\n== Dimension sizes ==")
print(q("""SELECT 'dim_date' t, count(*) n FROM dim_date UNION ALL SELECT 'dim_medicine', count(*) FROM dim_medicine
          UNION ALL SELECT 'dim_pharmacy', count(*) FROM dim_pharmacy UNION ALL SELECT 'dim_hospital', count(*) FROM dim_hospital
          UNION ALL SELECT 'dim_geography', count(*) FROM dim_geography UNION ALL SELECT 'dim_sales_profile', count(*) FROM dim_sales_profile
          UNION ALL SELECT 'dim_demand_flags', count(*) FROM dim_demand_flags""").to_string(index=False))

print("\n== Unknown-member usage (-1 keys) ==")
unk = q("""SELECT count(*) FILTER (WHERE medicine_key=-1) medicine, count(*) FILTER (WHERE pharmacy_key=-1) pharmacy,
                  count(*) FILTER (WHERE geography_key=-1) geography, count(*) FILTER (WHERE sales_profile_key=-1) profile,
                  count(*) FILTER (WHERE hospital_key=-1) hospital_not_applicable, count(*) FILTER (WHERE hospital_key<>-1) hospital_sales
           FROM fact_pharmacy_sales""")
print(unk.to_string(index=False))
line("no unknown medicine/pharmacy/geography/profile in sales",
     int(unk.iloc[0][["medicine", "pharmacy", "geography", "profile"]].sum()) == 0)
unk2 = q("""SELECT count(*) FILTER (WHERE medicine_key=-1 OR hospital_key=-1 OR geography_key=-1 OR demand_flags_key=-1) bad
            FROM fact_hospital_demand""")
line("no unknown keys in hospital demand", int(unk2.iloc[0, 0]) == 0)

print("\n== SCD Type 2 integrity ==")
bad_current = q("""SELECT medicine_id, count(*) FILTER (WHERE is_current) AS n_current FROM dim_medicine
                   WHERE medicine_key>0 GROUP BY 1 HAVING n_current <> 1""")
line("exactly one current version per medicine", bad_current.empty)
gaps = q("""SELECT count(*) AS n FROM (SELECT valid_to, lead(valid_from) OVER (PARTITION BY medicine_id ORDER BY valid_from) AS nxt
            FROM dim_medicine WHERE medicine_key>0) WHERE nxt IS NOT NULL AND nxt <> valid_to""")
line("versions are contiguous (no gaps or overlaps)", int(gaps.iloc[0, 0]) == 0)

print("\n== SCD2 in action: price charged per medicine version ==")
print(q("""SELECT m.medicine_id, m.generic_name, m.valid_from, m.valid_to, m.recommended_retail_price_usd AS version_retail_price,
                  count(f.sales_key) AS sales_rows, round(avg(f.unit_retail_price_usd), 2) AS avg_price_charged
           FROM dim_medicine m LEFT JOIN fact_pharmacy_sales f ON f.medicine_key = m.medicine_key
           WHERE m.medicine_id IN (SELECT medicine_id FROM dim_medicine GROUP BY 1 HAVING count(*) > 1 ORDER BY 1 LIMIT 3)
           GROUP BY ALL ORDER BY m.medicine_id, m.valid_from""").to_string(index=False))

print("\n== Date coverage ==")
print(q("""SELECT 'sales' AS fact, min(d.full_date) AS first_date, max(d.full_date) AS last_date
           FROM fact_pharmacy_sales f JOIN dim_date d ON d.date_key = f.sales_date_key
           UNION ALL SELECT 'hospital demand', min(d.full_date), max(d.full_date)
           FROM fact_hospital_demand f JOIN dim_date d ON d.date_key = f.demand_month_date_key""").to_string(index=False))