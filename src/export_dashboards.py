"""Write the three Grafana dashboards defined in make_dashboards.py to grafana/dashboards/*.json.

Run from the repo root (Grafana does not need to be running):
    python src/export_dashboards.py

The JSON files are what Grafana loads on start-up through grafana/provisioning/.
make_dashboards.py stays the single source of truth: change a panel there, re-run this, commit the JSON.
"""
import json as jsonlib
from pathlib import Path

import make_dashboards as md

OUT = Path(__file__).resolve().parent.parent / "grafana" / "dashboards"
# must match uid and type in grafana/provisioning/datasources/datasource.yml
DS = {"type": "grafana-postgresql-datasource", "uid": "staging-postgres"}
FILES = {
    "de-ingestion": "de-1-batch-ingestion.json",
    "de-storage": "de-2-storage.json",
    "de-queries": "de-3-query-performance.json",
}


class _Ok:
    status_code = 200

    def json(self):
        return {"url": "  <- file export only, nothing was sent to Grafana"}


def _capture(url, json=None, auth=None):
    """Stands in for the Grafana API call inside make_dashboards.push() and saves the dashboard instead."""
    dash = json["dashboard"]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / FILES[dash["uid"]]
    path.write_text(jsonlib.dumps(dash, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(OUT.parent.parent)}")
    return _Ok()


if __name__ == "__main__":
    md.requests.post = _capture
    print("Exporting dashboards ...")
    md.ingestion(DS)
    md.storage(DS)
    md.queries(DS)
