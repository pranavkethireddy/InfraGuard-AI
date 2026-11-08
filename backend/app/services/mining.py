"""Mining revenue from real daily Bitcoin hashprice (CloudMineCrypto open data, CC BY 4.0).

Hashprice is the expected gross mining revenue per TH/s per day. Lost revenue for a miner is
its rated hashrate times hashprice; for a cooling unit it is every miner in the racks it cools.
Rated hashrate comes from configs/mining_layout.json (spec-sheet-class demo value).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .layout import ROOT, site_of

SOURCE = "CloudMineCrypto open data (CC BY 4.0), https://cloudminecrypto.com/data"


@dataclass(frozen=True)
class Hashprice:
    usd_per_th_day: float
    as_of: str
    avg_30d_usd_per_th_day: float
    network_hashrate_eh: float | None


@lru_cache
def hashprice(path: str) -> Hashprice | None:
    """Latest day with a reading. Empty cells mean no reliable reading and are skipped, never guessed."""
    p = Path(path)
    p = p if p.is_absolute() or p.is_file() else ROOT / p
    if not p.is_file():
        return None
    rows = [r for r in csv.DictReader(p.open()) if r.get("hashprice_usd_per_th_day")]
    if not rows:
        return None
    last = rows[-1]
    recent = [float(r["hashprice_usd_per_th_day"]) for r in rows[-30:]]
    eh = last.get("network_hashrate_eh")
    return Hashprice(usd_per_th_day=float(last["hashprice_usd_per_th_day"]), as_of=last["date"],
                     avg_30d_usd_per_th_day=sum(recent) / len(recent), network_hashrate_eh=float(eh) if eh else None)


def rated_hashrate_ths(asset_id: str) -> float:
    """Rated TH/s an asset puts at risk: the miner itself, or every miner a cooling unit serves."""
    lay = site_of(asset_id)
    if lay is None or "asic_miner" not in lay.specs:
        return 0.0
    rated = float(lay.specs["asic_miner"]["rated_hashrate_ths"])
    asset = lay.assets[asset_id]
    if asset.asset_type == "asic_miner":
        return rated
    served = [a for r in lay.racks.values() if asset_id in r.cooled_by for a in r.asset_ids]
    return rated * len(served)


def revenue_per_day(asset_id: str, path: str) -> float | None:
    hp = hashprice(path)
    return None if hp is None else rated_hashrate_ths(asset_id) * hp.usd_per_th_day
