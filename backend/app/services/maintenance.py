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


def _same_kind(asset_id: str) -> set[str | None]:
    """The asset itself, site-wide records (None) and other assets of the same type at the same site: a CRAC
    unit can learn from another CRAC unit's repairs, but not from a mining fan wall. Each hit keeps its own
    asset_id, so citations stay honest."""
    from .layout import site_of

    lay = site_of(asset_id)
    if lay is None:
        return {asset_id, None}
    kind = lay.assets[asset_id].asset_type
    return {asset_id, None} | {a for a, x in lay.assets.items() if x.asset_type == kind}


def search(req: MaintenanceSearchRequest, path: str) -> MaintenanceSearchResponse:
    source, records, vec, matrix = _index(path)
    scores = (matrix @ vec.transform([req.query]).T).toarray().ravel()
    allowed = _same_kind(req.asset_id) if req.asset_id else None
    hits = []
    for i in scores.argsort()[::-1]:
        r = records[i]
        if scores[i] < MIN_SCORE:
            break
        if allowed is not None and r["asset_id"] not in allowed:
            continue
        hits.append(MaintenanceSource(record_id=r["record_id"], asset_id=r["asset_id"], recorded_at=r["recorded_at"],
                                      source_name=source, excerpt=r["text"][:400], score=round(float(scores[i]), 4)))
        if len(hits) == req.limit:
            break
    return MaintenanceSearchResponse(items=hits, total=len(hits), status="ok" if hits else "no_evidence")
