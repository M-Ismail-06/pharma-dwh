import psycopg2
import pandas as pd
from config import DB

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 70)


def show(title, sql):
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(sql)
    df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    conn.close()
    print(f"\n{title}")
    print(df.to_string(index=False) if not df.empty else "(none)")


show("QUALITY PER BATCH",
     """SELECT l.file_name, q.rows_staged, q.rows_valid, q.rows_rejected, q.rows_pending
        FROM v_batch_quality q LEFT JOIN ingestion_log l ON l.batch_id = q.batch_id
        ORDER BY l.log_id""")
show("REJECTIONS BY RULE",
     "SELECT source_table, rule_name, violations, rows_affected FROM v_rejection_summary ORDER BY 1, 2")
show("LATEST REJECTED RECORDS",
     "SELECT source_table, record_id, rule_name, reason FROM rejected_records ORDER BY reject_id DESC LIMIT 20")