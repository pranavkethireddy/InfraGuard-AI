"""Site floor plan for walking technicians: where each hall sits, its door, and the paths between spots.

Halls are laid out left to right with a gap, and a corridor runs along the bottom of the site. Each hall
has a service lane (two cells in from its left wall, between the cooling units and the first rack) that
leads to its door on the corridor. A walk goes: along the lane to the target's level and across to it;
between halls it goes down the lane, out of the door, along the corridor and up the other hall's lane.
Coordinates are floor cells (the layout's grid unit). A hall-local point (x, y) is at (hall.x + x, y).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from ..schemas.ops import FloorHall, FloorPlan, FloorPoint
from .layout import Layout, get_layout

GAP = 2.0  # cells between halls
LANE = 2.0  # service lane, cells in from a hall's left wall


@dataclass(frozen=True)
class Spot:
    hall_id: str
    x: float  # hall-local
    y: float


@lru_cache(maxsize=8)
def plan(site: str) -> FloorPlan:
    lay = get_layout(site)
    halls, x = [], 0.0
    corridor = max(h.depth for h in lay.halls) + 1.0
    for h in lay.halls:
        halls.append(FloorHall(hall_id=h.hall_id, name=h.name, x=x, y=0.0, width=h.width, depth=h.depth,
                               door=FloorPoint(x=x + LANE, y=h.depth, hall_id=h.hall_id)))
        x += h.width + GAP
    return FloorPlan(site_id=site, width=x - GAP, depth=corridor + 1.0, corridor_y=corridor, lane_offset=LANE,
                     grid_unit=lay.grid_unit, halls=halls)


def _hall(site: str, hall_id: str) -> FloorHall:
    return next(h for h in plan(site).halls if h.hall_id == hall_id)


def to_floor(site: str, spot: Spot) -> FloorPoint:
    h = _hall(site, spot.hall_id)
    return FloorPoint(x=round(h.x + spot.x, 2), y=round(spot.y, 2), hall_id=spot.hall_id)


def spot_for_asset(lay: Layout, asset_id: str) -> Spot:
    """Where a technician stands to work on a machine: the aisle in front of its rack, or beside a unit."""
    p = lay.placements[asset_id]
    if p.rack_id:
        r = lay.racks[p.rack_id]
        return Spot(p.hall_id, r.x + r.width / 2, r.y + r.depth + 0.5)
    return Spot(p.hall_id, p.x + 1.0, p.y)


def spot_for_hall(lay: Layout, hall_id: str) -> Spot:
    """Default spot for hall-level work (routine jobs): the middle of the service lane."""
    h = next(x for x in lay.halls if x.hall_id == hall_id)
    return Spot(hall_id, LANE, h.depth / 2)


def path(site: str, a: FloorPoint, b: FloorPoint) -> list[FloorPoint]:
    """Waypoints from a to b (both included, consecutive duplicates removed)."""
    fp = plan(site)
    pts: list[FloorPoint] = [a]
    if a.hall_id is not None and a.hall_id == b.hall_id:
        lane = _hall(site, a.hall_id).x + LANE
        pts += [FloorPoint(x=lane, y=a.y, hall_id=a.hall_id), FloorPoint(x=lane, y=b.y, hall_id=b.hall_id)]
    else:
        if a.hall_id is not None:
            ha = _hall(site, a.hall_id)
            pts += [FloorPoint(x=ha.door.x, y=a.y, hall_id=a.hall_id), ha.door,
                    FloorPoint(x=ha.door.x, y=fp.corridor_y, hall_id=None)]
        else:
            pts.append(FloorPoint(x=a.x, y=fp.corridor_y, hall_id=None))
        if b.hall_id is not None:
            hb = _hall(site, b.hall_id)
            pts += [FloorPoint(x=hb.door.x, y=fp.corridor_y, hall_id=None), hb.door,
                    FloorPoint(x=hb.door.x, y=b.y, hall_id=b.hall_id)]
        else:
            pts.append(FloorPoint(x=b.x, y=fp.corridor_y, hall_id=None))
    pts.append(b)
    out = [pts[0]]
    for p in pts[1:]:
        if (p.x, p.y) != (out[-1].x, out[-1].y):
            out.append(p)
    return out


def length(pts: list[FloorPoint]) -> float:
    return sum(math.dist((p.x, p.y), (q.x, q.y)) for p, q in zip(pts, pts[1:]))


def walk(pts: list[FloorPoint], cells: float) -> tuple[FloorPoint, list[FloorPoint]]:
    """Move `cells` along the path. Returns (new position, remaining waypoints starting at it)."""
    pos, rest = pts[0], pts[1:]
    while rest and cells > 1e-9:
        nxt = rest[0]
        d = math.dist((pos.x, pos.y), (nxt.x, nxt.y))
        if d <= cells:
            cells -= d
            pos, rest = nxt, rest[1:]
            continue
        f = cells / d
        pos = FloorPoint(x=round(pos.x + (nxt.x - pos.x) * f, 2), y=round(pos.y + (nxt.y - pos.y) * f, 2),
                         hall_id=nxt.hall_id if nxt.hall_id == pos.hall_id else pos.hall_id)
        cells = 0.0
    return pos, [pos, *rest]
