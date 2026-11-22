"""Phase 1 master pipeline: generate -> ingest -> validate -> dimensions -> facts -> summaries -> metrics.
Trigger with config {"initial_load": true} to load the original CSVs instead of generating a new month."""
import sys
from datetime import datetime

sys.path.insert(0, "/opt/airflow/src")

from airflow import DAG
from airflow.operators.python import PythonOperator

import pipeline_tasks as t

with DAG(
    dag_id="phase1_pipeline",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["phase1"],
    doc_md=__doc__,
    params={"initial_load": False},
) as dag:

    generate_data = PythonOperator(
        task_id="generate_data", python_callable=t.generate_data,
        op_kwargs={"initial_load": "{{ dag_run.conf.get('initial_load', False) }}"})
    ingest_to_staging = PythonOperator(task_id="ingest_to_staging", python_callable=t.ingest_to_staging)
    validate = PythonOperator(task_id="validate", python_callable=t.validate_staging)
    load_dimensions = PythonOperator(task_id="load_dimensions", python_callable=t.load_dimensions)
    load_facts = PythonOperator(task_id="load_facts", python_callable=t.load_facts)
    build_summaries = PythonOperator(task_id="build_summaries", python_callable=t.build_summaries)
    log_metrics = PythonOperator(task_id="log_metrics", python_callable=t.log_metrics)

    (generate_data >> ingest_to_staging >> validate >> load_dimensions
     >> load_facts >> build_summaries >> log_metrics)