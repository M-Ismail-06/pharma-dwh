import hashlib
import io
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2

from config import (DB, FILE_MAP, COLUMN_RENAMES, CHUNK_ROWS,
                    PROCESSED, FAILED)

AUDIT = {"batch_id", "source_file", "load_timestamp"}


def get_conn():
    return psycopg2.connect(**DB)


def resolve_table(name):
    for prefix, table in FILE_MAP.items():
        if name.startswith(prefix):
            return table
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def table_columns(cur, table):
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = %s ORDER BY ordinal_position""", (table,))
    return [r[0] for r in cur.fetchall() if r[0] not in AUDIT]


def already_loaded(file_hash):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT 1 FROM ingestion_log
                       WHERE file_hash = %s AND status = 'success' LIMIT 1""",
                    (file_hash,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def write_log(batch_id, path, table, file_hash, size_mb, start, end,
              rows, status, error):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ingestion_log
              (batch_id, file_name, target_table, file_hash, file_size_mb,
               start_time, end_time, duration_seconds, rows_loaded,
               status, error_message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (batch_id, path.name, table, file_hash, round(size_mb, 2), start,
             end, round((end - start).total_seconds(), 2), rows, status, error))
        conn.commit()
    finally:
        conn.close()


def move_file(path, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{path.stem}_{datetime.now():%Y%m%d%H%M%S}{path.suffix}"
    shutil.move(str(path), str(dest))


def ingest_file(path):
    path = Path(path)
    batch_id = uuid.uuid4().hex[:12]
    start = datetime.now()
    table = resolve_table(path.name)
    rows, status, error, file_hash, size_mb = 0, "success", None, None, 0.0

    try:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
        size_mb = path.stat().st_size / 1_000_000
        if table is None:
            raise ValueError("Unknown file: name must start with one of "
                             + ", ".join(FILE_MAP))
        file_hash = sha256(path)
        if already_loaded(file_hash):
            status = "skipped"
            error = "Identical file already loaded"
        else:
            conn = get_conn()
            try:
                cur = conn.cursor()
                expected = set(table_columns(cur, table))
                for chunk in pd.read_csv(path, dtype=str, chunksize=CHUNK_ROWS):
                    chunk = chunk.rename(columns=COLUMN_RENAMES)
                    chunk.columns = [c.strip().lower() for c in chunk.columns]
                    # schema validation
                    got = set(chunk.columns)
                    if got != expected:
                        raise ValueError(
                            f"Schema mismatch. Missing: {sorted(expected - got)} "
                            f"Unexpected: {sorted(got - expected)}")
                    chunk["batch_id"] = batch_id
                    chunk["source_file"] = path.name
                    buf = io.StringIO()
                    chunk.to_csv(buf, index=False, header=False, na_rep="")
                    buf.seek(0)
                    cols = ",".join(chunk.columns)
                    cur.copy_expert(
                        f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
                    rows += len(chunk)
                conn.commit()          # all chunks or nothing
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
    except Exception as e:
        status, error, rows = "failed", str(e)[:1000], 0

    end = datetime.now()
    write_log(batch_id, path, table, file_hash, size_mb, start, end,
              rows, status, error)

    try:
        if path.exists():
            move_file(path, FAILED if status == "failed" else PROCESSED)
    except Exception as e:
        error = f"{error or ''} (could not move file: {e})"

    return {"batch_id": batch_id, "file": path.name, "table": table,
            "status": status, "rows_loaded": rows,
            "duration_seconds": round((end - start).total_seconds(), 2),
            "error": error}