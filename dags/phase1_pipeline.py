from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def _generate():
    import sys
    sys.path.insert(0, "/opt/airflow/src")
    from generator import run_refresh
    return run_refresh()


with DAG(
    dag_id="phase1_pipeline",
    start_date=datetime(2026, 1, 1),
    schedule=None,          # manual trigger for now
    catchup=False,
    tags=["phase1"],
) as dag:
    generate_data = PythonOperator(task_id="generate_data", python_callable=_generate)