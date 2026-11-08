"""Failure playbooks (configs/failure_catalog.json): name the failure mode a machine's readings point to.

Each equipment type lists its modes most specific first; a mode matches when all its 'when' conditions hold.
The last mode of each type has no conditions, so a cause is always named. The playbook gives the cause, the
reasoning (filled in with the actual readings), the repair steps, and planning hours and parts cost."""

from __future__ import annotations

import json
import operator
import string
from functools import lru_cache
from pathlib import Path

from ..schemas.incidents import FailureMode

CATALOG_PATH = Path(__file__).resolve().parents[3] / "configs" / "failure_catalog.json"
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


@lru_cache(maxsize=1)
def catalog() -> dict[str, list[dict]]:
    by_type: dict[str, list[dict]] = {}
    for m in json.loads(CATALOG_PATH.read_text())["modes"]:
        by_type.setdefault(m["asset_type"], []).append(m)
    return by_type


def modes(asset_type: str) -> list[dict]:
    return catalog().get(asset_type, [])


def _holds(cond: list, values: dict) -> bool:
    metric, op, want = cond
    v = values.get(metric)
    return isinstance(v, (int, float)) and not isinstance(v, bool) and OPS[op](v, want)


def _match(asset_type: str, values: dict) -> dict | None:
    """The first specific (conditional) mode whose conditions all hold."""
    return next((m for m in modes(asset_type) if m["when"] and all(_holds(c, values) for c in m["when"])), None)


class _Values(dict):
    def __missing__(self, key):
        return "?"


class _Fmt(string.Formatter):
    def format_field(self, value, spec):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return format(value, spec) if spec else (f"{value:,.0f}" if abs(value) >= 1000 else str(value))
        return str(value)


def _fill(text: str, values: dict) -> str:
    try:
        return _Fmt().vformat(text, (), _Values(values))
    except (ValueError, IndexError, KeyError):
        return text


def to_model(mode: dict, values: dict) -> FailureMode:
    return FailureMode(
        mode_id=mode["mode_id"], title=mode["title"], cause=_fill(mode["cause"], values),
        reasoning=_fill(mode["reasoning"], values), signals=list(mode["signals"]), steps=list(mode["steps"]),
        repair_hours=mode.get("repair_hours"), parts_cost_usd=mode.get("parts_cost_usd"),
        evidence={s: values[s] for s in mode["signals"] if isinstance(values.get(s), (int, float))})


def diagnose(asset_type: str, recent: list[dict]) -> FailureMode | None:
    """The newest reading that shows a specific pattern names the mode (a fault that has since recovered still
    names its cause); otherwise the type's general mode, filled from the newest reading."""
    if not modes(asset_type):
        return None
    for values in reversed(recent):
        m = _match(asset_type, values)
        if m is not None:
            return to_model(m, values)
    return to_model(modes(asset_type)[-1], recent[-1] if recent else {})


def likely_cause(asset_type: str, values: dict | None) -> str | None:
    """One sentence for a single reading, or None when no specific pattern matches."""
    m = _match(asset_type, values or {})
    return f"{m['title']}: {_fill(m['reasoning'], values)}" if m else None


def is_unknown(text: str | None) -> bool:
    return not text or "unknown" in text.lower() or "not clear" in text.lower() or "cannot be determined" in text.lower()
