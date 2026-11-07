"""Maintenance record retrieval (TF-IDF over the records file). Cites record IDs; never invents records."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..core.errors import ApiError
from ..schemas.maintenance import MaintenanceSearchRequest, MaintenanceSearchResponse, MaintenanceSource

MIN_SCORE = 0.05


@lru_cache
def _index(path: str):
    from sklearn.feature_extraction.text import TfidfVectorizer

    p = Path(path)
    if not p.is_file():
        raise ApiError(503, "RETRIEVAL_UNAVAILABLE", "Maintenance records are not loaded.", {"path": path})
    raw = json.loads(p.read_text())
    records = raw["records"]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vec.fit_transform([r["text"] for r in records])
    return raw["source_name"], records, vec, matrix


def search(req: MaintenanceSearchRequest, path: str) -> MaintenanceSearchResponse:
    source, records, vec, matrix = _index(path)
    scores = (matrix @ vec.transform([req.query]).T).toarray().ravel()
    hits = []
    for i in scores.argsort()[::-1]:
        r = records[i]
        if scores[i] < MIN_SCORE:
            break
        if req.asset_id and r["asset_id"] not in (req.asset_id, None):
            continue
        hits.append(MaintenanceSource(record_id=r["record_id"], asset_id=r["asset_id"], recorded_at=r["recorded_at"],
                                      source_name=source, excerpt=r["text"][:400], score=round(float(scores[i]), 4)))
        if len(hits) == req.limit:
            break
    return MaintenanceSearchResponse(items=hits, total=len(hits), status="ok" if hits else "no_evidence")
