"""Copy the six DuckDB summary tables into Postgres (bi_* tables) so Grafana can chart them."""
import duckdb
import psycopg2
from psycopg2.extras import execute_values

from config import DB, DUCKDB_PATH

TABLES = {
    "sum_monthly_sales": "bi_monthly_sales",
    "sum_medicine_month": "bi_medicine_month",
    "sum_pharmacy_month": "bi_pharmacy_month",
    "sum_channel_segment_month": "bi_channel_segment_month",
    "sum_delivery_otif": "bi_delivery_otif",
    "sum_hospital_month": "bi_hospital_month",
}
FLOATS = ("DECIMAL", "DOUBLE", "FLOAT", "HUGEINT")
INTS = ("BIGINT", "INTEGER", "SMALLINT", "TINYINT", "UBIGINT", "UINTEGER")


def run():
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pg = psycopg2.connect(**DB)
    cur = pg.cursor()
    for src, dst in TABLES.items():
        cols = [(r[0], r[1].upper()) for r in con.execute(f"DESCRIBE {src}").fetchall()]
        select, ddl = [], []
        for name, typ in cols:
            if typ.startswith(FLOATS):
                select.append(f'CAST("{name}" AS DOUBLE) AS "{name}"')
                ddl.append(f'"{name}" DOUBLE PRECISION')
            elif typ.startswith(INTS):
                select.append(f'CAST("{name}" AS BIGINT) AS "{name}"')
                ddl.append(f'"{name}" BIGINT')
            else:
                select.append(f'CAST("{name}" AS VARCHAR) AS "{name}"')
                ddl.append(f'"{name}" TEXT')
        rows = con.execute(f"SELECT {', '.join(select)} FROM {src}").fetchall()
        cur.execute(f"DROP TABLE IF EXISTS {dst}")
        cur.execute(f"CREATE TABLE {dst} ({', '.join(ddl)})")
        if rows:
            execute_values(cur, f"INSERT INTO {dst} VALUES %s", rows, page_size=5000)
        pg.commit()
        print(f"{dst}: {len(rows):,} rows")
    pg.close()
    con.close()


if __name__ == "__main__":
    run()