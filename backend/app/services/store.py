"""In-memory runtime state (readings, predictions, incidents, simulations, rule state).

One Store per app instance, guarded by one lock. Data is lost on restart; the SQLite
layer (backend/app/db) can replace this later without changing the API.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..schemas.incidents import IncidentDetail
from ..schemas.predictions import PredictionResponse
from ..schemas.readings import StoredReading
from ..schemas.simulations import SimulationResponse


@dataclass
class RuleState:
    consecutive_above: int = 0
    cooldown_remaining: int = 0


@dataclass
class StoredReadingRow:
    reading: StoredReading
    simulation_id: str | None


@dataclass
class Store:
    lock: threading.RLock = field(default_factory=threading.RLock)
    readings: dict[str, list[StoredReadingRow]] = field(default_factory=dict)
    predictions: dict[tuple[str, str, datetime], PredictionResponse] = field(default_factory=dict)
    incidents: dict[str, IncidentDetail] = field(default_factory=dict)
    simulations: dict[str, SimulationResponse] = field(default_factory=dict)
    sim_stop: dict[str, threading.Event] = field(default_factory=dict)
    rule_state: dict[str, RuleState] = field(default_factory=dict)
    # Newest prediction per asset (by observed_at), so status views never scan every prediction.
    latest_prediction: dict[str, PredictionResponse] = field(default_factory=dict)
    # Live fleet demo state (services/live.py); None until first started.
    live: Any = None
    # Background pool for automatic AI investigations, created on first use.
    investigator: Any = None
    # services.ops.OpsState (crew and work orders) and services.learning cases, created on first use.
    ops: Any = None
    learning: Any = None
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):06d}"

    def remember_latest(self, pred: PredictionResponse) -> None:
        cur = self.latest_prediction.get(pred.asset_id)
        if cur is None or pred.observed_at >= cur.observed_at:
            self.latest_prediction[pred.asset_id] = pred

    def rebuild_latest(self) -> None:
        self.latest_prediction.clear()
        for p in self.predictions.values():
            self.remember_latest(p)

    def active_incident(self, asset_id: str, detector_id: str) -> IncidentDetail | None:
        for inc in self.incidents.values():
            if inc.asset_id == asset_id and inc.detector_id == detector_id and inc.status != "resolved":
                return inc
        return None
