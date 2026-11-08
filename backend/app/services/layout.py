"""Site layouts from configs/: halls, rows, racks and the machines in them.

Two sites: the data center (configs/datacenter_layout.json) and the crypto mining farm
(configs/mining_layout.json). Rows are expanded into racks, and each rack into its devices
(drives or ASIC miners), so the configs stay short. Device ids run <prefix>-01, <prefix>-02, ...
in hall, row and rack order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..schemas.assets import AssetDetail
from ..schemas.fleet import Placement

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Rack:
    rack_id: str
    hall_id: str
    row: str
    label: str
    x: float
    y: float
    width: float
    depth: float
    cooled_by: tuple[str, ...]
    asset_ids: tuple[str, ...]


@dataclass(frozen=True)
class Hall:
    hall_id: str
    name: str
    kind: str
    width: float
    depth: float
    rack_ids: tuple[str, ...]
    unit_ids: tuple[str, ...]


@dataclass
class Layout:
    site_id: str
    site_name: str
    grid_unit: str
    halls: list[Hall]
    racks: dict[str, Rack]
    assets: dict[str, AssetDetail]
    placements: dict[str, Placement]
    chart_fields: dict[str, list[str]] = field(default_factory=dict)
    specs: dict[str, dict] = field(default_factory=dict)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() or p.is_file() else ROOT / p


@lru_cache
def load(path: str) -> Layout:
    raw = json.loads(_resolve(path).read_text())
    types = raw["asset_types"]
    rack_cfg = raw["rack"]
    halls, racks, assets, placements = [], {}, {}, {}
    device_type, prefix = rack_cfg["device_type"], rack_cfg["device_prefix"]
    device_no = 0

    def add(asset_id, name, asset_type, criticality, location, placement):
        assets[asset_id] = AssetDetail(
            asset_id=asset_id, name=name, asset_type=asset_type, location=location, criticality=criticality,
            compatible_detector=types[asset_type]["detector_id"], data_origin="simulated", current_risk_level=None,
            active_incident_id=None, last_reading_at=None, impact_assumptions=None,
        )
        placements[asset_id] = placement

    for h in raw["halls"]:
        rack_ids, unit_ids = [], []
        for u in h["units"]:
            add(u["asset_id"], u["name"], u["asset_type"], u["criticality"], h["name"],
                Placement(hall_id=h["hall_id"], row=None, rack_id=None, slot=None, x=u["x"], y=u["y"]))
            unit_ids.append(u["asset_id"])
        for row in h["rows"]:
            for i in range(row["racks"]):
                rack_id = f"{row['row']}-{i + 1:02d}"
                x, y = row["x0"] + i * rack_cfg["width"], row["y"]
                device_ids = []
                for slot in range(1, row["devices_per_rack"] + 1):
                    device_no += 1
                    asset_id = f"{prefix}-{device_no:02d}"
                    label = f"{rack_cfg['device_label']} {slot}"
                    add(asset_id, f"Rack {rack_id}, {label}", device_type, rack_cfg["device_criticality"],
                        f"{h['name']}, Row {row['row']}, Rack {rack_id}, {label}",
                        Placement(hall_id=h["hall_id"], row=row["row"], rack_id=rack_id, slot=slot, x=x, y=y))
                    device_ids.append(asset_id)
                racks[rack_id] = Rack(rack_id=rack_id, hall_id=h["hall_id"], row=row["row"], label=f"Rack {rack_id}",
                                      x=x, y=y, width=rack_cfg["width"], depth=rack_cfg["depth"],
                                      cooled_by=tuple(row["cooled_by"]), asset_ids=tuple(device_ids))
                rack_ids.append(rack_id)
        halls.append(Hall(hall_id=h["hall_id"], name=h["name"], kind=h["kind"], width=h["width"], depth=h["depth"],
                          rack_ids=tuple(rack_ids), unit_ids=tuple(unit_ids)))
    return Layout(site_id=raw["site"]["site_id"], site_name=raw["site"]["name"], grid_unit=raw["site"]["grid_unit"], halls=halls, racks=racks,
                  assets=assets, placements=placements,
                  chart_fields={t: list(v["chart_fields"]) for t, v in types.items()},
                  specs={t: dict(v.get("spec", {})) for t, v in types.items()})


def site_paths() -> dict[str, str]:
    from ..core.config import get_settings

    s = get_settings()
    return {"datacenter": s.datacenter_layout_path, "mining": s.mining_layout_path}


def get_layout(site: str = "datacenter") -> Layout:
    return load(site_paths()[site])


def all_layouts() -> list[Layout]:
    return [load(p) for p in site_paths().values()]


def site_of(asset_id: str) -> Layout | None:
    return next((lay for lay in all_layouts() if asset_id in lay.assets), None)
