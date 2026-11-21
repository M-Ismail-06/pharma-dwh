from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from ingest import ingest_file

app = FastAPI(title="Pharma ingestion API")


class IngestRequest(BaseModel):
    file_path: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest):
    return ingest_file(Path(req.file_path))