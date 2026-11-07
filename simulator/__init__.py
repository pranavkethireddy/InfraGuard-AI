"""Deterministic demo sensor values. No model, incident, or cost calculations."""

from .generator import SAMPLE_COUNT, SCENARIOS, generate, readings_payload

__all__ = ["SAMPLE_COUNT", "SCENARIOS", "generate", "readings_payload"]
