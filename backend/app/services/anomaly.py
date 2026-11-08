"""One anomaly model per facility equipment family: an IsolationForest trained on healthy simulated readings,
plus each reading's healthy range (trees cannot rank points far outside what they were trained on).

The rules stay authoritative (they name the fault and open incidents). The model adds a second opinion:
a reading unlike anything healthy for that family is flagged as unusual even when no rule is broken yet.
Trained once per family at first use (about 0.2 s), seeded, so results repeat. Demo models, not field data."""

from __future__ import annotations

import math
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
    forest = IsolationForest(n_estimators=50, random_state=0).fit(rows)
    healthy = forest.score_samples(rows)
    forest = _Fast(forest)
    # Below the least normal healthy reading, with margin: only clearly unusual readings are flagged.
    threshold = float(min(healthy)) - 0.01
    # Trees cannot rank points far outside the training range, so also keep each reading's healthy range.
    cols = list(zip(*rows))
    ranges = [(min(c) - 3 * (max(c) - min(c) + 0.1), max(c) + 3 * (max(c) - min(c) + 0.1)) for c in cols]
    return forest, fields, threshold, ranges


def _c(n: float) -> float:
    """Average path length of an unsuccessful search in a binary tree of n points (Liu et al., 2008)."""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - 2.0 * (n - 1) / n


class _Fast:
    """The fitted forest walked in plain Python: the same score as score_samples, without sklearn's per-call
    overhead (about 2 ms a reading), so scoring every live reading stays cheap."""

    def __init__(self, forest):
        self.trees = []
        for est, feats in zip(forest.estimators_, forest.estimators_features_):
            t = est.tree_
            self.trees.append((t.children_left.tolist(), t.children_right.tolist(), [int(feats[f]) if f >= 0 else -1
                               for f in t.feature.tolist()], t.threshold.tolist(),
                               [_c(n) for n in t.n_node_samples.tolist()]))
        self.norm = _c(forest.max_samples_)

    def score(self, x: list[float]) -> float:
        total = 0.0
        for left, right, feat, thr, leaf in self.trees:
            node, depth = 0, 0
            while left[node] != -1:
                node = left[node] if x[feat[node]] <= thr[node] else right[node]
                depth += 1
            total += depth + leaf[node]
        return -(2.0 ** (-(total / len(self.trees)) / self.norm))


def score(asset_type: str, values: dict) -> tuple[float, float] | None:
    """(score, threshold): lower is more unusual; below the threshold is an anomaly. None if not scorable."""
    m = model(asset_type)
    if m is None:
        return None
    forest, fields, threshold, ranges = m
    if any(not isinstance(values.get(f), (int, float)) for f in fields):
        return None
    x = [float(values[f]) for f in fields]
    s = forest.score(x)
    if any(not lo <= xi <= hi for xi, (lo, hi) in zip(x, ranges)):
        s = min(s, threshold - 0.1)  # outside anything seen healthy: unusual
    return round(s, 4), round(threshold, 4)
