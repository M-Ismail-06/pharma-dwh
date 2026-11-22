import sys

import requests

G = "http://localhost:3000"
AUTH = ("admin", "admin")
DS_NAME = "Staging Postgres"


def get_datasource():
    r = requests.get(f"{G}/api/datasources/name/{DS_NAME}", auth=AUTH)
    if r.status_code != 200:
        for ptype in ("grafana-postgresql-datasource", "postgres"):   # name differs by Grafana version
            body = {"name": DS_NAME, "type": ptype, "access": "proxy", "url": "staging-db:5432",
                    "user": "de", "database": "staging", "secureJsonData": {"password": "de"},
                    "jsonData": {"sslmode": "disable", "postgresVersion": 1500, "database": "staging"}}
            p = requests.post(f"{G}/api/datasources", json=body, auth=AUTH)
            if p.status_code == 200:
                break
            print(f"  data source type '{ptype}' refused: {p.status_code} {p.text[:200]}")
        else:
            sys.exit("Could not create the data source.")
        r = requests.get(f"{G}/api/datasources/name/{DS_NAME}", auth=AUTH)
    ds = r.json()
    h = requests.get(f"{G}/api/datasources/uid/{ds['uid']}/health", auth=AUTH)
    print("Data source health:", h.status_code, h.text[:160])
    return {"type": ds["type"], "uid": ds["uid"]}


STAT = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "colorMode": "value", "graphMode": "none", "textMode": "auto"}
GAUGE = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
         "showThresholdMarkers": True, "orientation": "auto"}
HBAR = {"orientation": "horizontal", "showValue": "auto", "stacking": "none", "barWidth": 0.8,
        "groupWidth": 0.7, "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
        "tooltip": {"mode": "single", "sort": "none"}}
HBAR_LEGEND = {**HBAR, "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}}
DONUT = {"pieType": "donut", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
         "legend": {"showLegend": True, "displayMode": "table", "placement": "right", "values": ["value", "percent"]},
         "displayLabels": ["percent"], "tooltip": {"mode": "single"}}
TABLE = {"showHeader": True, "cellHeight": "sm"}
TS = {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}
LOG = {"custom": {"scaleDistribution": {"type": "log", "log": 10}}}


def panel(pid, ptype, title, ds, sql, x, y, w, h, options=None, defaults=None, fmt="table"):
    return {"id": pid, "type": ptype, "title": title, "datasource": ds,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"refId": "A", "datasource": ds, "format": fmt, "rawQuery": True,
                         "editorMode": "code", "rawSql": sql}],
            "options": options or {}, "fieldConfig": {"defaults": defaults or {}, "overrides": []}}


def push(uid, title, panels, time_from):
    dash = {"uid": uid, "title": title, "tags": ["phase1", "data-engineering"], "timezone": "browser",
            "schemaVersion": 39, "version": 0, "refresh": "", "time": {"from": time_from, "to": "now"},
            "panels": panels}
    r = requests.post(f"{G}/api/dashboards/db", json={"dashboard": dash, "overwrite": True}, auth=AUTH)
    if r.status_code != 200:
        sys.exit(f"Dashboard '{title}' failed: {r.status_code} {r.text[:300]}")
    print(f"  created: {G}{r.json()['url']}")


def stat(pid, title, ds, sql, x, w, unit=None, decimals=None, color="green"):
    d = {"thresholds": {"mode": "absolute", "steps": [{"color": color, "value": None}]}}
    if unit:
        d["unit"] = unit
    if decimals is not None:
        d["decimals"] = decimals
    return panel(pid, "stat", title, ds, sql, x, 0, w, 5, STAT, d)


# ---------------------------------------------------------------- DE-1
def ingestion(ds):
    green_red = {"unit": "percent", "min": 0, "max": 100, "decimals": 1, "thresholds": {"mode": "absolute", "steps": [
        {"color": "red", "value": None}, {"color": "orange", "value": 80}, {"color": "green", "value": 95}]}}
    p = [
        panel(1, "gauge", "Batch success rate", ds,
              "SELECT 100.0 * count(*) FILTER (WHERE status='success') / NULLIF(count(*) FILTER (WHERE status IN ('success','failed')),0) AS success_rate_pct FROM ingestion_log",
              0, 0, 4, 5, GAUGE, green_red),
        stat(2, "Batches loaded", ds, "SELECT count(*) AS batches FROM ingestion_log WHERE status='success'", 4, 4),
        stat(3, "Failed batches", ds, "SELECT count(*) AS failed FROM ingestion_log WHERE status='failed'", 8, 4, color="red"),
        stat(4, "Rows loaded to staging", ds, "SELECT coalesce(sum(rows_loaded),0) AS rows_loaded FROM ingestion_log WHERE status='success'", 12, 4),
        stat(5, "Records dropped by validation", ds, "SELECT coalesce(sum(rows_rejected),0) AS dropped FROM v_batch_quality", 16, 4, color="orange"),
        stat(6, "Dropped record rate", ds, "SELECT round(100.0*sum(rows_rejected)/NULLIF(sum(rows_staged),0),4) AS dropped_pct FROM v_batch_quality", 20, 4, unit="percent", decimals=4, color="orange"),
        panel(7, "barchart", "Load duration per file (seconds)", ds,
              "SELECT file_name, duration_seconds FROM ingestion_log WHERE status='success' ORDER BY log_id",
              0, 5, 12, 10, {**HBAR, "xField": "file_name"}, {"unit": "s"}),
        panel(8, "barchart", "Rows processed per batch (log scale)", ds,
              "SELECT file_name, rows_loaded FROM ingestion_log WHERE status='success' ORDER BY log_id",
              12, 5, 12, 10, {**HBAR, "xField": "file_name"}, LOG),
        panel(9, "barchart", "Rejected records by validation rule", ds,
              "SELECT rule_name, count(*) AS violations FROM rejected_records GROUP BY 1 ORDER BY 2 DESC",
              0, 15, 12, 9, {**HBAR, "xField": "rule_name"}),
        panel(10, "table", "Validation result per batch", ds,
              "SELECT l.file_name, q.rows_staged, q.rows_valid, q.rows_rejected FROM v_batch_quality q LEFT JOIN ingestion_log l ON l.batch_id = q.batch_id AND l.status='success' ORDER BY l.log_id",
              12, 15, 12, 9, TABLE),
        panel(11, "table", "Latest ingestion attempts", ds,
              "SELECT log_id, file_name, status, rows_loaded, duration_seconds, file_size_mb, start_time, left(error_message, 80) AS error FROM ingestion_log ORDER BY log_id DESC LIMIT 20",
              0, 24, 24, 9, TABLE),
    ]
    push("de-ingestion", "DE-1 Batch ingestion", p, "now-30d")


# ---------------------------------------------------------------- DE-2
def storage(ds):
    p = [
        stat(1, "Warehouse file size", ds, "SELECT size_mb FROM v_storage_latest WHERE layer='warehouse file'", 0, 8, unit="mbytes", decimals=1),
        stat(2, "Warehouse fact rows", ds, "SELECT coalesce(sum(row_count),0) AS fact_rows FROM v_storage_latest WHERE table_name LIKE 'fact\\_%'", 8, 8),
        stat(3, "Staging database size (Postgres tables)", ds, "SELECT coalesce(sum(size_mb),0) AS size_mb FROM v_storage_latest WHERE layer='staging (Postgres)'", 16, 8, unit="mbytes", decimals=1),
        panel(4, "barchart", "Row count per table (log scale)", ds,
              "SELECT table_name, row_count FROM v_storage_latest WHERE layer <> 'warehouse file' ORDER BY row_count DESC",
              0, 5, 12, 11, {**HBAR, "xField": "table_name"}, LOG),
        panel(5, "barchart", "Storage footprint per table (MB)", ds,
              "SELECT table_name, size_mb FROM v_storage_latest WHERE layer <> 'warehouse file' ORDER BY size_mb DESC",
              12, 5, 12, 11, {**HBAR, "xField": "table_name"}, {"unit": "mbytes"}),
        panel(6, "table", "Date coverage (min / max)", ds,
              "SELECT table_name, layer, min_date, max_date, (max_date - min_date) AS days_covered FROM v_storage_latest WHERE min_date IS NOT NULL ORDER BY table_name",
              0, 16, 12, 8, TABLE),
        panel(7, "piechart", "Storage by source domain (MB)", ds,
              "SELECT domain, sum(size_mb) AS size_mb FROM v_storage_latest WHERE layer <> 'warehouse file' GROUP BY 1 ORDER BY 2 DESC",
              12, 16, 12, 8, DONUT, {"unit": "mbytes"}),
        panel(8, "timeseries", "Storage growth between snapshots (MB)", ds,
              "SELECT captured_at AS time, layer AS metric, sum(size_mb) AS value FROM storage_metrics WHERE layer <> 'warehouse file' AND $__timeFilter(captured_at) GROUP BY 1, 2 ORDER BY 1",
              0, 24, 24, 8, TS, {"unit": "mbytes", "custom": {"drawStyle": "line", "showPoints": "always", "lineWidth": 2}}, fmt="time_series"),
    ]
    push("de-storage", "DE-2 Storage", p, "now-30d")


# ---------------------------------------------------------------- DE-3
def queries(ds):
    p = [
        stat(1, "Average query time", ds, "SELECT round(avg(duration_ms)::numeric,1) AS avg_ms FROM query_log WHERE status='success'", 0, 6, unit="ms", decimals=1),
        stat(2, "Queries executed", ds, "SELECT count(*) AS queries FROM query_log", 6, 6),
        stat(3, "Error rate", ds, "SELECT round(100.0 * count(*) FILTER (WHERE status='failed') / NULLIF(count(*),0), 2) AS error_pct FROM query_log", 12, 6, unit="percent", decimals=2, color="red"),
        stat(4, "Slowest single run", ds, "SELECT max(duration_ms) AS max_ms FROM query_log WHERE status='success'", 18, 6, unit="ms", decimals=1, color="orange"),
        panel(5, "barchart", "Average execution time per query: baseline vs optimized (ms)", ds,
              "SELECT query_name, round(avg(duration_ms) FILTER (WHERE run_label='baseline')::numeric,1) AS baseline_ms, round(avg(duration_ms) FILTER (WHERE run_label='optimized')::numeric,1) AS optimized_ms FROM query_log WHERE status='success' GROUP BY 1 ORDER BY 1",
              0, 5, 24, 11, {**HBAR_LEGEND, "xField": "query_name"}, {"unit": "ms"}),
        panel(6, "timeseries", "Queries per day", ds,
              "SELECT date_trunc('day', executed_at) AS time, count(*) AS queries FROM query_log WHERE $__timeFilter(executed_at) GROUP BY 1 ORDER BY 1",
              0, 16, 12, 9, TS, {"custom": {"drawStyle": "bars", "fillOpacity": 60, "lineWidth": 1}}, fmt="time_series"),
        panel(7, "table", "Per-query summary", ds,
              "SELECT query_name, count(*) AS runs, round(avg(duration_ms)::numeric,1) AS avg_ms, round(min(duration_ms)::numeric,1) AS min_ms, round(max(duration_ms)::numeric,1) AS max_ms, round(100.0*count(*) FILTER (WHERE status='failed')/count(*),1) AS error_pct FROM query_log GROUP BY 1 ORDER BY 1",
              12, 16, 12, 9, TABLE),
    ]
    push("de-queries", "DE-3 Query performance", p, "now-7d")


if __name__ == "__main__":
    try:
        ds = get_datasource()
    except requests.exceptions.ConnectionError:
        sys.exit("Grafana is not reachable on localhost:3000. Run: docker compose up -d")
    print("Creating dashboards ...")
    ingestion(ds)
    storage(ds)
    queries(ds)