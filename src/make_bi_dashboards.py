"""Write the 3 BI dashboards (Phase 1) to grafana/dashboards/*.json. Grafana loads them within ~30 s.
Run from the repo root:  python src/make_bi_dashboards.py"""
import json
from pathlib import Path

import make_dashboards as md

OUT = Path(__file__).resolve().parent.parent / "grafana" / "dashboards"
DS = {"type": "grafana-postgresql-datasource", "uid": "staging-postgres"}
T = "to_timestamp(year_month || '-01', 'YYYY-MM-DD')"
LINE = {"custom": {"drawStyle": "line", "showPoints": "always", "lineWidth": 2}}


def save(uid, title, panels, fname):
    dash = {"uid": uid, "title": title, "tags": ["phase1", "bi"], "timezone": "browser", "schemaVersion": 39,
            "version": 0, "refresh": "", "time": {"from": "2022-12-01T00:00:00.000Z", "to": "now"},
            "panels": panels}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / fname).write_text(json.dumps(dash, indent=2) + "\n", encoding="utf-8")
    print("wrote", fname)


def bar(pid, title, sql, x, y, w, h, field, unit=None):
    return md.panel(pid, "barchart", title, DS, sql, x, y, w, h, {**md.HBAR, "xField": field},
                    {"unit": unit} if unit else {})


def hospital():
    p = [
        md.stat(1, "Consumption / forecast ratio", DS, "SELECT round((100.0*sum(consumed_packs)/NULLIF(sum(forecast_packs),0))::numeric,1) AS ratio_pct FROM bi_hospital_month", 0, 6, unit="percent", decimals=1),
        md.stat(2, "Unfulfilled demand (packs)", DS, "SELECT sum(unfulfilled_packs) AS packs FROM bi_hospital_month", 6, 6, color="red"),
        md.stat(3, "Unfulfilled share of requests", DS, "SELECT round((100.0*sum(unfulfilled_packs)/NULLIF(sum(requested_packs),0))::numeric,2) AS pct FROM bi_hospital_month", 12, 6, unit="percent", decimals=2, color="orange"),
        md.stat(4, "Stockout days (total)", DS, "SELECT sum(stockout_days) AS days FROM bi_hospital_month", 18, 6, color="orange"),
        md.panel(5, "timeseries", "Forecast vs actual consumption per month (packs)", DS,
                 f"SELECT {T} AS time, sum(forecast_packs) AS forecast, sum(consumed_packs) AS consumed FROM bi_hospital_month GROUP BY 1 ORDER BY 1",
                 0, 5, 24, 9, md.TS, LINE, fmt="time_series"),
        md.panel(6, "timeseries", "Consumption / forecast ratio per month (%)", DS,
                 f"SELECT {T} AS time, round((100.0*sum(consumed_packs)/NULLIF(sum(forecast_packs),0))::numeric,1) AS ratio_pct FROM bi_hospital_month GROUP BY 1 ORDER BY 1",
                 0, 14, 12, 9, md.TS, LINE, fmt="time_series"),
        md.panel(7, "timeseries", "Unfulfilled demand per month (packs)", DS,
                 f"SELECT {T} AS time, sum(unfulfilled_packs) AS unfulfilled FROM bi_hospital_month GROUP BY 1 ORDER BY 1",
                 12, 14, 12, 9, md.TS, {"custom": {"drawStyle": "bars", "fillOpacity": 60}}, fmt="time_series"),
        bar(8, "Unfulfilled demand by hospital (packs)", "SELECT hospital_name, sum(unfulfilled_packs) AS unfulfilled FROM bi_hospital_month GROUP BY 1 ORDER BY 2 DESC", 0, 23, 12, 10, "hospital_name"),
        bar(9, "Unfulfilled demand by therapeutic class (packs)", "SELECT therapeutic_class, sum(unfulfilled_packs) AS unfulfilled FROM bi_hospital_month GROUP BY 1 ORDER BY 2 DESC", 12, 23, 12, 10, "therapeutic_class"),
    ]
    save("bi-hospital", "BI-1 Hospital forecast vs actual and unfulfilled demand", p, "bi-1-hospital-demand.json")


def channel():
    p = [
        md.stat(1, "Net sales (USD)", DS, "SELECT sum(net_sales_usd) AS net FROM bi_monthly_sales", 0, 8, unit="currencyUSD", decimals=0),
        md.stat(2, "Gross margin (USD)", DS, "SELECT sum(gross_margin_usd) AS margin FROM bi_monthly_sales", 8, 8, unit="currencyUSD", decimals=0),
        md.stat(3, "Gross margin %", DS, "SELECT round((100.0*sum(gross_margin_usd)/NULLIF(sum(net_sales_usd),0))::numeric,1) AS pct FROM bi_monthly_sales", 16, 8, unit="percent", decimals=1),
        md.panel(4, "timeseries", "Net sales per month by channel (USD)", DS,
                 f"SELECT {T} AS time, sales_channel AS metric, sum(net_sales_usd) AS value FROM bi_monthly_sales GROUP BY 1, 2 ORDER BY 1",
                 0, 5, 24, 9, md.TS, LINE, fmt="time_series"),
        md.panel(5, "piechart", "Revenue split by channel", DS,
                 "SELECT sales_channel, sum(net_sales_usd) AS net_sales FROM bi_monthly_sales GROUP BY 1 ORDER BY 2 DESC",
                 0, 14, 8, 10, md.DONUT),
        bar(6, "Gross margin % by channel", "SELECT sales_channel, round((100.0*sum(gross_margin_usd)/NULLIF(sum(net_sales_usd),0))::numeric,1) AS margin_pct FROM bi_monthly_sales GROUP BY 1 ORDER BY 2 DESC", 8, 14, 8, 10, "sales_channel", "percent"),
        bar(7, "Gross margin % by pharmacy type", "SELECT pharmacy_type, round((100.0*sum(gross_margin_usd)/NULLIF(sum(net_sales_usd),0))::numeric,1) AS margin_pct FROM bi_monthly_sales GROUP BY 1 ORDER BY 2 DESC", 16, 14, 8, 10, "pharmacy_type", "percent"),
        md.panel(8, "table", "Channel comparison", DS,
                 "SELECT sales_channel, sum(txn_count) AS transactions, round(sum(net_sales_usd)::numeric,0) AS net_sales_usd, round(sum(gross_margin_usd)::numeric,0) AS gross_margin_usd, round((100.0*sum(gross_margin_usd)/NULLIF(sum(net_sales_usd),0))::numeric,1) AS margin_pct FROM bi_monthly_sales GROUP BY 1 ORDER BY 3 DESC",
                 0, 24, 24, 7, md.TABLE),
    ]
    save("bi-channel", "BI-2 Channel revenue split and gross margin", p, "bi-2-channel-revenue.json")


def movers():
    p = [
        bar(1, "Top 10 fast-moving medicines (packs sold)", "SELECT generic_name, sum(qty_sold_packs) AS packs FROM bi_medicine_month GROUP BY 1 ORDER BY 2 DESC LIMIT 10", 0, 0, 12, 11, "generic_name"),
        bar(2, "Top 10 slow-moving medicines (packs sold)", "SELECT generic_name, sum(qty_sold_packs) AS packs FROM bi_medicine_month GROUP BY 1 ORDER BY 2 ASC LIMIT 10", 12, 0, 12, 11, "generic_name"),
        bar(3, "Packs sold by therapeutic class", "SELECT therapeutic_class, sum(qty_sold_packs) AS packs FROM bi_medicine_month GROUP BY 1 ORDER BY 2 DESC", 0, 11, 12, 10, "therapeutic_class"),
        md.panel(4, "table", "Fastest and slowest medicine in each therapeutic class", DS,
                 "WITH t AS (SELECT therapeutic_class, generic_name, sum(qty_sold_packs) AS packs FROM bi_medicine_month GROUP BY 1, 2), "
                 "r AS (SELECT *, row_number() OVER (PARTITION BY therapeutic_class ORDER BY packs DESC) AS hi, "
                 "row_number() OVER (PARTITION BY therapeutic_class ORDER BY packs ASC) AS lo FROM t) "
                 "SELECT therapeutic_class, "
                 "max(CASE WHEN hi = 1 THEN generic_name END) AS fastest, max(CASE WHEN hi = 1 THEN packs END) AS fastest_packs, "
                 "max(CASE WHEN lo = 1 THEN generic_name END) AS slowest, max(CASE WHEN lo = 1 THEN packs END) AS slowest_packs "
                 "FROM r GROUP BY 1 ORDER BY 1",
                 12, 11, 12, 10, md.TABLE),
        md.panel(5, "timeseries", "Packs sold per month, top 5 medicines", DS,
                 f"SELECT {T} AS time, generic_name AS metric, sum(qty_sold_packs) AS value FROM bi_medicine_month "
                 "WHERE generic_name IN (SELECT generic_name FROM bi_medicine_month GROUP BY 1 ORDER BY sum(qty_sold_packs) DESC LIMIT 5) GROUP BY 1, 2 ORDER BY 1",
                 0, 21, 24, 9, md.TS, LINE, fmt="time_series"),
    ]
    save("bi-movers", "BI-3 Fast vs slow moving medicines by therapeutic class", p, "bi-3-medicine-movers.json")


if __name__ == "__main__":
    hospital()
    channel()
    movers()
