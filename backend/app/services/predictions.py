"""POST /predictions and POST /readings logic, shared by the API and the simulation runner."""

from __future__ import annotations

from ..core.config import Settings
from ..core.errors import ApiError
from ..schemas.predictions import PredictionRequest, PredictionResponse
from ..schemas.readings import ReadingsRequest, StoredReading
from . import assets as asset_service
from . import detectors, incidents
from .model_registry import COOLING_RULE_ID, list_models
from .store import RuleState, Store, StoredReadingRow


def store_readings(store: Store, req: ReadingsRequest) -> int:
    asset_service.get_asset(req.asset_id)
    with store.lock:
        rows = store.readings.setdefault(req.asset_id, [])
        for r in req.readings:
            rows.append(StoredReadingRow(StoredReading(observed_at=r.observed_at, values=r.values,
                                                       data_origin=req.data_origin), req.simulation_id))
        rows.sort(key=lambda x: x.reading.observed_at)
    return len(req.readings)


def predict(store: Store, req: PredictionRequest, settings: Settings) -> tuple[PredictionResponse, bool]:
    """Returns (prediction, created). A repeat of (asset, detector, observed_at) returns the stored one."""
    asset = asset_service.get_asset(req.asset_id)
    if asset.compatible_detector != req.detector_id:
        raise ApiError(422, "UNSUPPORTED_DETECTOR", f"Asset '{asset.asset_id}' uses {asset.compatible_detector}.",
                       {"asset_id": asset.asset_id, "detector_id": req.detector_id,
                        "compatible_detector": asset.compatible_detector})
    info = {m.detector_id: m for m in list_models(settings)}[req.detector_id]
    detectors.check_fields(info, req.readings)
    key = (req.asset_id, req.detector_id, req.observed_at)
    with store.lock:
        if key in store.predictions:
            return store.predictions[key], False
        if req.detector_id == COOLING_RULE_ID:
            result = detectors.cooling(info, req.readings, store.rule_state.setdefault(req.asset_id, RuleState()))
            source = "rule"
        else:
            if info.status != "available":
                raise ApiError(503, "MODEL_UNAVAILABLE", f"{info.detector_id} is not trained.", {})
            result = detectors.model(info, req.readings, detectors.artifact_for(req.detector_id, settings))
            source = "template"
        pred = PredictionResponse(
            prediction_id=store.next_id("pred"), asset_id=req.asset_id, detector_id=req.detector_id,
            observed_at=req.observed_at, generated_at=incidents.now(), data_origin=req.data_origin,
            model_name=info.model_name, model_version=info.model_version, target=info.target,
            risk_score=result.risk_score, score_kind=info.score_kind, risk_level=result.risk_level,
            prediction_horizon_hours=info.prediction_horizon_hours, explanation=result.explanation,
            explanation_source=source, evidence=result.evidence, maintenance_sources=[],
            limitations=info.limitations, incident_id=None, simulation_id=req.simulation_id,
        )
        if result.triggered:
            inc = incidents.open_or_update(store, pred, asset, settings)
            pred = pred.model_copy(update={"incident_id": inc.incident_id})
            inc.latest_prediction = pred
        store.predictions[key] = pred
    return pred, True
