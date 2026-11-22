"""Task functions for the Phase 1 Airflow DAG. Each wraps code already tested on the PC."""
import runpy
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import RAW, DROPZONE  # noqa: E402


def generate_data(initial_load=False):
    """Normal run: generate the next month. initial_load: drop the original CSVs into the drop zone."""
    if str(initial_load).lower() == "true":
        DROPZONE.mkdir(parents=True, exist_ok=True)
        for f in sorted(RAW.glob("*.csv")):
            shutil.copy(f, DROPZONE / f.name)
            print(f"copied original file {f.name} to the drop zone")
        return "initial_load"
    from generator import run_refresh
    return run_refresh()


def ingest_to_staging():
    from ingest import ingest_file
    files = sorted(DROPZONE.glob("*.csv"))
    if not files:
        print("Drop zone is empty (the watcher may already have ingested the files).")
        return []
    results, failed = [], []
    for f in files:
        r = ingest_file(f)
        print(r)
        results.append({k: r[k] for k in ("file", "status", "rows_loaded")})
        if r["status"] == "failed":
            failed.append(r["file"])
    if failed:
        raise RuntimeError(f"Ingestion failed for: {failed}")
    return results


def validate_staging():
    import validate
    validate.run()


def load_dimensions():
    import load_warehouse as lw
    con = lw.connect()
    try:
        lw.load_dimensions(con)
    finally:
        con.close()


def load_facts():
    import load_warehouse as lw
    con = lw.connect()
    try:
        lw.load_facts(con)
    finally:
        con.close()


def build_summaries():
    runpy.run_path(str(SRC / "build_summaries.py"), run_name="__main__")


def log_metrics():
    runpy.run_path(str(SRC / "collect_storage_metrics.py"), run_name="__main__")
    import run_queries
    run_queries.run("pipeline", replace=False)   # feeds the query dashboard on every pipeline run