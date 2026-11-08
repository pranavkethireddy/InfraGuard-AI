"""One anomaly model per facility equipment family: an IsolationForest trained on healthy simulated readings,
plus each reading's healthy range (trees cannot rank points far outside what they were trained on).

The rules stay authoritative (they name the fault and open incidents). The model adds a second opinion:
a reading unlike anything healthy for that family is flagged as unusual even when no rule is broken yet.
Trained once per family at first use (about 0.2 s), seeded, so results repeat. Demo models, not field data."""

from __future__ import annotations

import random
from functools import lru_cache

N_TRAIN = 400


@lru_cache(maxsize=None)
def model(asset_type: str):
    """(fitted IsolationForest, field order, alert threshold) or None when the family has no simulator."""
    try:
        from sklearn.ensemble import IsolationForest

        from simulator import fleet
    except ImportError:
        return None
    if asset_type not in fleet.FACILITY:
        return None
    rows, fields, r = [], None, random.Random(asset_type)
    for i in range(N_TRAIN):
        prof = fleet.profile(asset_type, f"train-{i % 20}", i)
        v = fleet.sample(asset_type, prof, i, random.Random(i))
        fields = fields or sorted(v)
        # Small jitter so readings that never change when healthy (on/off flags) still give the forest a range.
        rows.append([float(v[f]) + r.uniform(-0.02, 0.02) * (1 + abs(float(v[f])) * 0.01) for f in fields])
    forest = IsolationForest(n_estimators=100, random_state=0).fit(rows)
    healthy = forest.score_samples(rows)
    # Below the least normal healthy reading, with margin: only clearly unusual readings are flagged.
    threshold = float(min(healthy)) - 0.01
    # Trees cannot rank points far outside the training range, so also keep each reading's healthy range.
    cols = list(zip(*rows))
    ranges = [(min(c) - 3 * (max(c) - min(c) + 0.1), max(c) + 3 * (max(c) - min(c) + 0.1)) for c in cols]
    return forest, fields, threshold, ranges


def score(asset_type: str, values: dict) -> tuple[float, float] | None:
    """(score, threshold): lower is more unusual; below the threshold is an anomaly. None if not scorable."""
    m = model(asset_type)
    if m is None:
        return None
    forest, fields, threshold, ranges = m
    if any(not isinstance(values.get(f), (int, float)) for f in fields):
        return None
    x = [float(values[f]) for f in fields]
    s = float(forest.score_samples([x])[0])
    if any(not lo <= xi <= hi for xi, (lo, hi) in zip(x, ranges)):
        s = min(s, threshold - 0.1)  # outside anything seen healthy: unusual
    return round(s, 4), round(threshold, 4)
