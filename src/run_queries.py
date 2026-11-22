import argparse
import time

import duckdb
import pandas as pd
import psycopg2

from config import DB, DUCKDB_PATH
from queries import QUERIES

REPEATS = 5


def run(label, replace):
    sql_key = "baseline" if label == "baseline" else "optimized"
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pg = psycopg2.connect(**DB)
    cur = pg.cursor()
    if replace:
        cur.execute("DELETE FROM query_log WHERE run_label = %s", (label,))
        pg.commit()

    print(f"Run label: {label}   ({REPEATS} runs per query)\n")
    for q in QUERIES:
        times, rows = [], None
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            try:
                rows = con.execute(q[sql_key]).fetchall()
                ms = (time.perf_counter() - t0) * 1000
                status, err, n = "success", None, len(rows)
                times.append(ms)
            except Exception as e:
                ms = (time.perf_counter() - t0) * 1000
                status, err, n = "failed", str(e)[:500], None
            cur.execute("""INSERT INTO query_log (query_name, run_label, duration_ms, rows_returned, status, error_message)
                           VALUES (%s, %s, %s, %s, %s, %s)""", (q["name"], label, round(ms, 2), n, status, err))
        pg.commit()
        if times:
            line = f"  {q['name']:<36} avg {sum(times)/len(times):9.1f} ms   best {min(times):9.1f} ms   rows {len(rows)}"
        else:
            line = f"  {q['name']:<36} FAILED: {err}"
        if label != "baseline" and rows is not None:
            same = con.execute(q["baseline"]).fetchall() == rows
            line += "   results identical to baseline: " + ("YES" if same else "NO  <-- investigate")
        print(line)
    con.close()
    pg.close()


def compare():
    pg = psycopg2.connect(**DB)
    cur = pg.cursor()
    cur.execute("""SELECT query_name, run_label, avg(duration_ms)::float AS avg_ms
                   FROM query_log WHERE status = 'success' AND run_label IN ('baseline', 'optimized')
                   GROUP BY 1, 2""")
    df = pd.DataFrame(cur.fetchall(), columns=["query_name", "run_label", "avg_ms"])
    pg.close()
    t = df.pivot(index="query_name", columns="run_label", values="avg_ms")
    t["speedup_x"] = (t["baseline"] / t["optimized"]).round(1)
    print(t.round(1).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("label", choices=["baseline", "optimized", "compare"])
    ap.add_argument("--replace", action="store_true", help="delete earlier rows with the same label first")
    a = ap.parse_args()
    compare() if a.label == "compare" else run(a.label, a.replace)