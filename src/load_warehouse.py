import sys
import time

import duckdb
import psycopg2

from config import DB, DUCKDB_PATH, SQL_DIR

STAGING = {"master": "stg_master_data", "hospital": "stg_hospital_demand", "sales": "stg_pharmacy_sales"}


def connect():
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("INSTALL postgres")
    con.execute("LOAD postgres")
    dsn = (f"host={DB['host']} port={DB['port']} dbname={DB['dbname']} "
           f"user={DB['user']} password={DB['password']}")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres, READ_ONLY)")
    return con


def run_sql_file(con, name, params=None):
    text = (SQL_DIR / name).read_text(encoding="utf-8")
    for key, value in (params or {}).items():
        text = text.replace("{" + key + "}", value)
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
    for stmt in text.split(";"):
        if stmt.strip():
            con.execute(stmt)


def ready_batches(table):
    """Batches that are fully validated (no pending rows) and contain valid rows."""
    conn = psycopg2.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT batch_id FROM {table} GROUP BY batch_id
                        HAVING count(*) FILTER (WHERE validation_status IS NULL) = 0
                           AND count(*) FILTER (WHERE validation_status = 'valid') > 0""")
        return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def stage_increment(con):
    for key, table in STAGING.items():
        loaded = {r[0] for r in con.execute(
            "SELECT batch_id FROM etl_loaded_batches WHERE source_table = ?", [table]).fetchall()}
        pending = sorted(ready_batches(table) - loaded)
        in_list = ",".join("'" + b.replace("'", "''") + "'" for b in pending) or "''"
        pg_query = f"SELECT * FROM {table} WHERE validation_status = 'valid' AND batch_id IN ({in_list})"
        literal = pg_query.replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE etl_raw_{key} AS "
                    f"SELECT * FROM postgres_query('pg', '{literal}')")
        n = con.execute(f"SELECT count(*) FROM etl_raw_{key}").fetchone()[0]
        print(f"  {table:<22} {len(pending)} new batch(es), {n:,} valid rows to load")


def load_dimensions(con):
    t0 = time.time()
    run_sql_file(con, "10_dwh_ddl.sql")
    print("Reading new validated batches from staging ...")
    stage_increment(con)
    run_sql_file(con, "12_prepare_increment.sql")
    dates = [r[0] for r in con.execute("SELECT DISTINCT effective_date FROM etl_new_master ORDER BY 1").fetchall()]
    for d in dates:
        print(f"  SCD2 pass for effective date {d}")
        run_sql_file(con, "21_scd2_medicine.sql", {"eff_date": d.isoformat()})
    run_sql_file(con, "20_load_dimensions.sql")
    print(f"Dimensions done in {time.time() - t0:.1f}s")


def load_facts(con):
    t0 = time.time()
    run_sql_file(con, "10_dwh_ddl.sql")
    try:
        con.execute("SELECT 1 FROM etl_raw_sales LIMIT 1")
    except duckdb.Error:
        sys.exit("No staged increment found. Run the dimension step first.")
    run_sql_file(con, "30_load_facts.sql")
    for key, table in STAGING.items():
        con.execute(f"""INSERT OR IGNORE INTO etl_loaded_batches
                        SELECT '{table}', batch_id, current_timestamp, count(*)
                        FROM etl_raw_{key} GROUP BY batch_id""")
    print(f"Facts done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--rebuild" in args:
        for suffix in ("", ".wal"):
            p = DUCKDB_PATH.parent / (DUCKDB_PATH.name + suffix)
            if p.exists():
                p.unlink()
        print("Warehouse deleted. Rebuilding from staging.")
    step = next((a for a in args if a in ("dims", "facts")), "all")
    con = connect()
    try:
        if step in ("dims", "all"):
            load_dimensions(con)
        if step in ("facts", "all"):
            load_facts(con)
    finally:
        con.close()