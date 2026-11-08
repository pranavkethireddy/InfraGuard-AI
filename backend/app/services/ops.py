"""Operations: the crew, their work orders, the demo clock and maintenance or curtailment windows.

Time runs on a demo clock: every live tick advances it by configs/operations.json
demo_minutes_per_tick, so a 3 h repair takes 90 ticks at 2 minutes per tick. Technicians travel,
work, pause routine jobs when moved to a repair, and resume them afterwards. Technicians walk the floor
plan (services/floor.py) at a demo pace, so travel time is walking distance and the closest qualified
technician is the one who can start soonest. A repair walk goes by the parts store first (configs/operations.json
parts_store) to pick up parts and tools, then to the machine. A technician on a lower-risk repair is moved to a
higher-risk one sent to them (the first is paused and resumed after). A technician claimed by a pager (an iPad)
is device-controlled: jobs are accepted automatically, and the pager confirms the work done. When a repair work order
finishes, the incident is resolved by the technician, the fault on the machine is repaired (readings
recover), and the repair becomes a learned case shared with every site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from ..core.config import Settings
from ..core.errors import ApiError, not_found
from ..schemas.ops import (DispatchRequest, DispatchResponse, FloorPoint, Technician, TechniciansResponse, Window,
                           WorkOrder, WorkOrderCost)
from . import floor
from . import impact as impact_service
from . import mining
from .assets import all_assets
from .incidents import now
from .layout import ROOT, get_layout, site_of
from .store import Store


@lru_cache
def load_config(path: str) -> dict:
    p = Path(path)
    return json.loads((p if p.is_absolute() or p.is_file() else ROOT / p).read_text())


def config(settings: Settings) -> dict:
    return load_config(settings.operations_path)


@dataclass
class Order:
    work_order_id: str
    kind: str
    title: str
    site_id: str
    hall_id: str
    technician_id: str
    hours_total: float
    created_at: datetime
    asset_id: str | None = None
    incident_id: str | None = None
    option: str | None = None
    status: str = "scheduled"
    hours_done: float = 0.0
    travel_left: float = 0.0
    scheduled_start: datetime | None = None
    completed_at: datetime | None = None
    mitigation_active: bool = False
    mitigation_hours: float = 0.0
    displaced_work_order_id: str | None = None
    delay_cost_per_hour: float = 0.0
    overtime: bool = False
    shutdown_seen: bool = False
    cost: WorkOrderCost | None = None
    spot: FloorPoint | None = None
    declined_by: list[str] = field(default_factory=list)
    risk_level: str | None = None  # the incident's risk, kept current each tick
    why: str | None = None


@dataclass
class Tech:
    cfg: dict
    location: str
    pos: FloorPoint
    current: str | None = None
    queue: list[str] = field(default_factory=list)
    path: list[FloorPoint] = field(default_factory=list)
    device: bool = False


@dataclass
class OpsState:
    start: datetime
    ticks: int = 0
    techs: dict[str, Tech] = field(default_factory=dict)
    orders: dict[str, Order] = field(default_factory=dict)
    seq: int = 0
    version: int = 0
    auto_dispatch: bool = True


def tick_hours(settings: Settings) -> float:
    return config(settings)["demo_minutes_per_tick"] / 60


def demo_now(st: OpsState, settings: Settings) -> datetime:
    return st.start + timedelta(minutes=st.ticks * config(settings)["demo_minutes_per_tick"])


def state(store: Store, settings: Settings) -> OpsState:
    """Created on first use (under store.lock): every technician on their routine job, or idle."""
    if store.ops is None:
        cfg = config(settings)
        st = OpsState(start=datetime.now(ZoneInfo(cfg["timezone"])).replace(second=0, microsecond=0),
                      auto_dispatch=settings.auto_dispatch)
        for t in cfg["technicians"]:
            st.techs[t["technician_id"]] = Tech(cfg=t, location=t["home"], pos=hall_spot(t["site"], t["home"]))
        for job in cfg["routine_jobs"]:
            tech = st.techs[job["technician_id"]]
            o = _new(st, settings, kind="routine", title=job["title"], site_id=tech.cfg["site"], hall_id=job["hall_id"],
                     technician_id=tech.cfg["technician_id"], hours_total=job["hours"],
                     delay_cost_per_hour=job["delay_cost_per_hour"], spot=hall_spot(tech.cfg["site"], job["hall_id"]))
            o.status, o.hours_done = "in_progress", job["hours"] * 0.3
            tech.location, tech.current, tech.pos = job["hall_id"], o.work_order_id, o.spot
        store.ops = st
    return store.ops


def hall_spot(site: str, hall_id: str) -> FloorPoint:
    return floor.to_floor(site, floor.spot_for_hall(get_layout(site), hall_id))


def asset_spot(asset_id: str) -> FloorPoint:
    lay = site_of(asset_id)
    return floor.to_floor(lay.site_id, floor.spot_for_asset(lay, asset_id))


def walk_hours(site: str, a: FloorPoint, b: FloorPoint, settings: Settings) -> float:
    pace = config(settings)["walk_cells_per_demo_minute"]
    return floor.length(floor.path(site, a, b)) / pace / 60


def parts_spots(site: str, settings: Settings) -> list[FloorPoint]:
    return [floor.to_floor(site, floor.Spot(p["hall_id"], p["x"], p["y"]))
            for p in config(settings).get("parts_store", {}).get(site, [])]


def repair_path(site: str, a: FloorPoint, b: FloorPoint, settings: Settings) -> list[FloorPoint]:
    """Walk for a repair: by the parts cabinet that makes the shortest trip, then to the machine."""
    trips = [floor.path(site, a, c) + floor.path(site, c, b)[1:] for c in parts_spots(site, settings)]
    return min(trips, key=floor.length) if trips else floor.path(site, a, b)


def repair_walk_hours(site: str, a: FloorPoint, b: FloorPoint, settings: Settings) -> float:
    return floor.length(repair_path(site, a, b, settings)) / config(settings)["walk_cells_per_demo_minute"] / 60


def _new(st: OpsState, settings: Settings, **kw) -> Order:
    st.seq += 1
    o = Order(work_order_id=f"wo-{st.seq:04d}", created_at=demo_now(st, settings), **kw)
    st.orders[o.work_order_id] = o
    return o


# ---- windows -------------------------------------------------------------------------------------

def breakeven_usd_per_mwh(settings: Settings) -> float | None:
    lay = get_layout("mining")
    spec = lay.specs.get("asic_miner", {})
    hp = mining.hashprice(settings.hashprice_data_path)
    if hp is None or not spec:
        return None
    revenue_day = spec["rated_hashrate_ths"] * hp.usd_per_th_day
    mwh_day = spec["rated_power_w"] * 24 / 1e6
    return round(revenue_day / mwh_day, 2)


def _in_window_at(site: str, when: datetime, settings: Settings) -> bool:
    sc = config(settings)["sites"][site]
    if sc["window"]["kind"] == "maintenance_window":
        w = sc["window"]
        return w["start_hour"] <= when.hour < w["end_hour"]
    be = breakeven_usd_per_mwh(settings)
    return be is not None and sc["power_price_usd_per_mwh"][when.hour] > be


def in_window(site: str, hours_from_now: float, st: OpsState, settings: Settings) -> bool:
    return _in_window_at(site, demo_now(st, settings) + timedelta(hours=hours_from_now), settings)


def window(site: str, st: OpsState, settings: Settings) -> Window:
    """Next window (or the current one) in demo hours from now, scanned in 5-minute steps over 2 days."""
    sc = config(settings)["sites"][site]["window"]
    step, start, end, h = 1 / 12, None, None, 0.0
    while h < 48:
        inside = in_window(site, h, st, settings)
        if start is None and inside:
            start = h
        elif start is not None and not inside:
            end = h
            break
        h += step
    start = 0.0 if start is None else start
    return Window(kind=sc["kind"], label=sc["label"], starts_in_hours=round(start, 2),
                  ends_in_hours=round(end if end is not None else start, 2),
                  breakeven_usd_per_mwh=breakeven_usd_per_mwh(settings) if sc["kind"] == "curtailment" else None)


# ---- technicians ---------------------------------------------------------------------------------

@dataclass
class Candidate:
    tech: Tech
    start_in_hours: float
    displaces: Order | None


def queued_repair_hours(st: OpsState, t: Tech) -> float:
    return sum(max(0.0, st.orders[i].hours_total - st.orders[i].hours_done)
               for i in t.queue if st.orders[i].kind == "repair" and st.orders[i].status != "done")


def candidates(st: OpsState, settings: Settings, site: str, asset_type: str, hall_id: str,
               asset_id: str | None = None, exclude: tuple[str, ...] = ()) -> list[Candidate]:
    """Qualified technicians at the site, soonest first (the closest by walking time, or the first to finish
    their current repair). Routine work can be paused; repairs cannot."""
    target = asset_spot(asset_id) if asset_id else hall_spot(site, hall_id)
    out = []
    for t in st.techs.values():
        if t.cfg["site"] != site or asset_type not in t.cfg["skills"] or t.cfg["technician_id"] in exclude:
            continue
        cur = st.orders.get(t.current) if t.current else None
        backlog = queued_repair_hours(st, t)  # repairs already waiting for them come first
        if cur is None:
            out.append(Candidate(t, backlog + repair_walk_hours(site, t.pos, target, settings), None))
        elif cur.kind == "routine":
            out.append(Candidate(t, backlog + repair_walk_hours(site, t.pos, target, settings), cur))
        else:
            left = cur.travel_left + max(0.0, cur.hours_total - cur.hours_done)
            out.append(Candidate(t, backlog + left + repair_walk_hours(site, cur.spot or t.pos, target, settings), None))
    out.sort(key=lambda c: (c.start_in_hours, c.displaces is not None, c.tech.cfg["rate_per_hour"]))
    return out


def _eta_minutes(o: Order, st: OpsState, settings: Settings) -> float | None:
    if o.status == "done":
        return None
    if o.status == "scheduled" and o.scheduled_start is not None:
        return round(max(0.0, (o.scheduled_start - demo_now(st, settings)).total_seconds() / 60), 1)
    return round((o.travel_left + max(0.0, o.hours_total - o.hours_done)) * 60, 1)


def work_order(o: Order, st: OpsState, settings: Settings) -> WorkOrder:
    return WorkOrder(
        work_order_id=o.work_order_id, kind=o.kind, title=o.title, site_id=o.site_id, hall_id=o.hall_id,
        asset_id=o.asset_id, incident_id=o.incident_id, technician_id=o.technician_id, status=o.status, option=o.option,
        mitigation_active=o.mitigation_active, hours_total=round(o.hours_total, 3), hours_done=round(o.hours_done, 3),
        progress=round(min(1.0, o.hours_done / o.hours_total) if o.hours_total else 1.0, 3),
        eta_minutes=_eta_minutes(o, st, settings), scheduled_start=o.scheduled_start, created_at=o.created_at,
        completed_at=o.completed_at, displaced_work_order_id=o.displaced_work_order_id, cost=o.cost, spot=o.spot,
        asset_name=all_assets()[o.asset_id].name if o.asset_id else None)


def technician(t: Tech, st: OpsState, settings: Settings) -> Technician:
    cur = st.orders.get(t.current) if t.current else None
    status = "idle" if cur is None or cur.status == "paged" else ("traveling" if cur.status == "traveling" else "working")
    walking = cur is not None and cur.status == "traveling"
    return Technician(technician_id=t.cfg["technician_id"], name=t.cfg["name"], role=t.cfg["role"], site_id=t.cfg["site"],
                      skills=list(t.cfg["skills"]), rate_per_hour=t.cfg["rate_per_hour"], status=status,
                      location_hall_id=t.location, current_work_order=work_order(cur, st, settings) if cur else None,
                      queued_work_order_ids=list(t.queue), position=t.pos, path=list(t.path) if walking else [],
                      walking_minutes_left=round(cur.travel_left * 60, 1) if walking else None, device_controlled=t.device)


def technicians(store: Store, settings: Settings, site: str | None) -> TechniciansResponse:
    with store.lock:
        st = state(store, settings)
        techs = [technician(t, st, settings) for t in st.techs.values() if site is None or t.cfg["site"] == site]
        orders = [work_order(o, st, settings) for o in st.orders.values()
                  if (site is None or o.site_id == site) and o.status != "done"]
        done = sorted((o for o in st.orders.values() if o.status == "done" and (site is None or o.site_id == site)),
                      key=lambda o: o.completed_at, reverse=True)[:10]
        orders += [work_order(o, st, settings) for o in done]
        return TechniciansResponse(demo_time=demo_now(st, settings),
                                   demo_minutes_per_tick=config(settings)["demo_minutes_per_tick"],
                                   auto_dispatch=st.auto_dispatch,
                                   walk_cells_per_demo_minute=config(settings)["walk_cells_per_demo_minute"],
                                   technicians=techs, work_orders=orders,
                                   assumptions_source=config(settings)["assumptions_source"])


def active_order_for(st: OpsState, incident_id: str) -> Order | None:
    return next((o for o in st.orders.values() if o.incident_id == incident_id and o.status != "done"), None)


def mitigated(store: Store, asset_id: str) -> bool:
    st: OpsState | None = store.ops
    return st is not None and any(o.mitigation_active and o.asset_id == asset_id and o.status != "done"
                                  for o in st.orders.values())


# ---- dispatch ------------------------------------------------------------------------------------

def dispatch(store: Store, settings: Settings, req: DispatchRequest, exclude: tuple[str, ...] = ()) -> DispatchResponse:
    from . import whatif

    with store.lock:
        st = state(store, settings)
        inc = store.incidents.get(req.incident_id)
        if inc is None:
            raise not_found("INCIDENT_NOT_FOUND", f"Incident '{req.incident_id}' does not exist.", incident_id=req.incident_id)
        if inc.status == "resolved":
            raise ApiError(409, "INCIDENT_RESOLVED", "Incident is already resolved.", {"incident_id": inc.incident_id})
        if active_order_for(st, inc.incident_id):
            raise ApiError(409, "ALREADY_DISPATCHED", "A work order is already open for this incident.",
                           {"incident_id": inc.incident_id})
    plan = whatif.compute(store, settings, req.incident_id)
    option = req.option or plan.recommended
    chosen = next((o for o in plan.options if o.option == option), None)
    if chosen is None:
        raise ApiError(422, "OPTION_NOT_AVAILABLE", f"Option '{option}' is not available for this incident.",
                       {"available": [o.option for o in plan.options]})
    with store.lock:
        st = state(store, settings)
        if active_order_for(st, inc.incident_id):  # raced with another dispatch
            raise ApiError(409, "ALREADY_DISPATCHED", "A work order is already open for this incident.",
                           {"incident_id": inc.incident_id})
        asset = all_assets()[inc.asset_id]
        lay = site_of(inc.asset_id)
        hall = lay.placements[inc.asset_id].hall_id
        cands = candidates(st, settings, lay.site_id, asset.asset_type, hall, asset.asset_id, exclude)
        if req.technician_id:
            tech = st.techs.get(req.technician_id)
            if tech is None:
                raise not_found("TECHNICIAN_NOT_FOUND", f"Technician '{req.technician_id}' does not exist.",
                                technician_id=req.technician_id)
            cand = next((c for c in cands if c.tech is tech), None)
            if cand is None:
                raise ApiError(422, "TECHNICIAN_NOT_QUALIFIED", f"{tech.cfg['name']} cannot repair {asset.asset_type} at this site.",
                               {"technician_id": req.technician_id, "asset_type": asset.asset_type, "site_id": lay.site_id})
        elif cands and chosen.start_in_hours is not None and chosen.start_in_hours > cands[0].start_in_hours + 0.05:
            # A later start (e.g. the window): the technician the chosen future was priced with, unless they
            # already have repairs waiting; then the qualified technician with the least work queued.
            priced = next((c for c in cands if c.tech.cfg["technician_id"] == chosen.technician_id), None)
            cand = priced if priced is not None and queued_repair_hours(st, priced.tech) == 0 else \
                min(cands, key=lambda c: (queued_repair_hours(st, c.tech), c.start_in_hours))
        elif cands:  # starts now: the closest qualified technician
            cand = cands[0]
        else:
            raise ApiError(409, "NO_TECHNICIAN", "No qualified technician at this site.", {"asset_type": asset.asset_type})
        tech = cand.tech
        cur = st.orders.get(tech.current) if tech.current else None
        # A busy technician picked by the operator gets the job queued behind their current repair (by level).
        imp = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type)
        hours = imp.estimated_repair_hours if imp and imp.estimated_repair_hours else 1.0
        # The first real step, not the reminder that physical work needs approval.
        steps = [a for a in inc.recommended_actions if "approv" not in a.lower()] or inc.recommended_actions or ["Repair"]
        action = steps[0]
        o = _new(st, settings, kind="repair", title=f"{asset.name}: {action}", site_id=lay.site_id, hall_id=hall,
                 technician_id=tech.cfg["technician_id"], hours_total=hours, asset_id=asset.asset_id,
                 incident_id=inc.incident_id, option=option, mitigation_active=option == "buy_time",
                 spot=asset_spot(asset.asset_id), declined_by=list(exclude), risk_level=inc.risk_level)
        mins = cand.start_in_hours * 60
        takeover = cur is not None and cur.kind == "repair" and _worse(st, o, cur, store)
        if takeover:
            mins = repair_walk_hours(lay.site_id, tech.pos, o.spot, settings) * 60
        o.why = (f"Moved off \"{cur.title}\" ({_describe(store, cur)}): this one is {_describe(store, o)}. " if
                 takeover else "") + ("You were picked by the operator." if req.technician_id else
                 f"Closest qualified technician: about {mins:.0f} demo minutes away." if not cand.displaces else
                 f"Closest qualified technician (about {mins:.0f} demo minutes away); your routine job "
                 f"\"{cand.displaces.title}\" is paused.")
        start_h = chosen.start_in_hours or 0.0
        displaced = None
        if option == "fix_now" or start_h <= cand.start_in_hours + 0.05:  # starts as soon as they can get there
            displaced = _start_now(st, settings, tech, o, store)
        else:
            o.status = "scheduled"
            o.scheduled_start = demo_now(st, settings) + timedelta(hours=start_h)
            tech.queue.append(o.work_order_id)
        inc.work_order_id = o.work_order_id
        if inc.status == "open":
            inc.status, inc.acknowledged_at = "acknowledged", now()
        st.version += 1
        return DispatchResponse(work_order=work_order(o, st, settings), technician=technician(tech, st, settings),
                                displaced=work_order(displaced, st, settings) if displaced else None)


def _start_now(st: OpsState, settings: Settings, tech: Tech, o: Order, store: Store | None = None) -> Order | None:
    """Put the technician on o at once. A routine job is paused and queued; a less urgent repair is paused and
    queued (one awaiting confirmation too: it is kept, and comes back for the tap); an equally or more urgent
    repair stays and o waits behind it."""
    cur = st.orders.get(tech.current) if tech.current else None
    displaced = None
    if cur is not None and cur.kind == "repair" and not _worse(st, o, cur, store):
        o.status = "scheduled"
        tech.queue.insert(0, o.work_order_id)
        return None
    if cur is not None:
        cur.status = "paused"
        tech.queue.append(cur.work_order_id)
        o.displaced_work_order_id = displaced_id = cur.work_order_id
        displaced = st.orders[displaced_id]
    o.overtime = not in_window(o.site_id, 0.0, st, settings)
    tech.current = o.work_order_id
    _set_off(st, settings, tech, o)  # accepted automatically, pager or not
    return displaced


RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def _risk(o: Order) -> int:
    return RISK_RANK.get(o.risk_level, 0) if o.risk_level else -1


# Life-safety equipment comes before everything else, whatever its priority number.
SAFETY_TYPES = {"smoke_detector", "fire_suppression"}


def _level(store: Store | None, o: Order) -> tuple:
    """How urgent a repair is; smaller is more urgent: life safety first, then priority rank (5 = most urgent),
    then risk."""
    inc = store.incidents.get(o.incident_id) if store is not None and o.incident_id else None
    asset = all_assets().get(o.asset_id) if o.asset_id else None
    safety = 0 if asset is not None and asset.asset_type in SAFETY_TYPES else 1
    rank = inc.priority_rank if inc is not None and inc.priority_rank else 0
    return (safety, -rank, -_risk(o))


def _describe(store: Store | None, o: Order) -> str:
    safety, rank, _ = _level(store, o)
    return ("life safety, " if safety == 0 else "") + (f"priority {-rank}, " if rank else "") + f"{o.risk_level or 'unknown'} risk"


def _worse(st: OpsState, new: Order, cur: Order, store: Store | None = None) -> bool:
    """True when new is a repair more urgent than the repair cur the technician is on."""
    return new.kind == "repair" and cur.kind == "repair" and _level(store, new) < _level(store, cur)


def _set_off(st: OpsState, settings: Settings, tech: Tech, o: Order) -> None:
    """Start walking to the job (or start work if already there)."""
    target = o.spot or hall_spot(o.site_id, o.hall_id)
    tech.path = repair_path(o.site_id, tech.pos, target, settings) if o.kind == "repair" and o.hours_done == 0 \
        else floor.path(o.site_id, tech.pos, target)
    o.travel_left = floor.length(tech.path) / config(settings)["walk_cells_per_demo_minute"] / 60
    o.status = "traveling" if o.travel_left > 1e-6 else "in_progress"
    if o.status == "in_progress":
        tech.path, tech.location = [], o.hall_id


# ---- clock ---------------------------------------------------------------------------------------

def _urgency(store: Store, o: Order) -> tuple:
    inc = store.incidents.get(o.incident_id) if o.incident_id else None
    return (o.kind != "repair", _level(store, o), -((inc.priority_index or 0.0) if inc else 0.0), o.created_at)


def advance(store: Store, settings: Settings, powered_off: set[str]) -> list[Order]:
    """One tick of crew work. Called by the live loop under store.lock. Returns repairs finished this tick."""
    st = state(store, settings)
    for o in st.orders.values():  # risk can change every tick
        inc = store.incidents.get(o.incident_id) if o.incident_id else None
        if inc is not None:
            o.risk_level = inc.risk_level
    st.ticks += 1
    h = tick_hours(settings)
    t_now = demo_now(st, settings)
    finished = []
    for o in st.orders.values():
        if o.status != "done" and o.mitigation_active:
            o.mitigation_hours += h
        if o.status != "done" and o.asset_id and (o.asset_id in powered_off or _cools_off(o.asset_id, powered_off)):
            o.shutdown_seen = True
    for tech in st.techs.values():
        # Repairs before routine work, the most urgent incident first (priority can change every tick).
        tech.queue.sort(key=lambda i: _urgency(store, st.orders[i]))
        # A scheduled repair whose time has come takes over from routine work.
        due = next((st.orders[i] for i in tech.queue if st.orders[i].status == "scheduled"
                    and st.orders[i].scheduled_start is not None and st.orders[i].scheduled_start <= t_now), None)
        cur = st.orders.get(tech.current) if tech.current else None
        # A higher-risk repair waiting for this technician takes over from a lower-risk one.
        top = next((st.orders[i] for i in tech.queue if st.orders[i].kind == "repair"
                    and st.orders[i].status in ("scheduled", "paused") and st.orders[i].scheduled_start is None), None)
        if top is not None and cur is not None and cur.kind == "repair" \
                and _worse(st, top, cur, store):
            tech.queue.remove(top.work_order_id)
            _start_now(st, settings, tech, top, store)
            cur = top
        if due is not None and (cur is None or cur.kind == "routine"):
            tech.queue.remove(due.work_order_id)
            _start_now(st, settings, tech, due, store)
            cur = due
        if cur is None:
            nxt = next((st.orders[i] for i in tech.queue if st.orders[i].status in ("paused", "scheduled")
                        and st.orders[i].scheduled_start is None), None)
            if nxt is None:
                continue
            tech.queue.remove(nxt.work_order_id)
            if nxt.kind == "routine":
                tech.current = nxt.work_order_id
                _set_off(st, settings, tech, nxt)
            else:
                _start_now(st, settings, tech, nxt, store)
            cur = nxt
        if cur.status in ("paged", "awaiting_confirmation"):
            continue  # waiting on the pager
        if cur.status == "traveling":
            pace = config(settings)["walk_cells_per_demo_minute"]
            tech.pos, tech.path = floor.walk(tech.path or [tech.pos], pace * h * 60)
            if tech.pos.hall_id:
                tech.location = tech.pos.hall_id
            cur.travel_left = floor.length(tech.path) / pace / 60
            if cur.travel_left <= 1e-9:
                cur.travel_left, cur.status, tech.location, tech.path = 0.0, "in_progress", cur.hall_id, []
            continue
        cur.hours_done += h
        if cur.hours_done + 1e-9 >= cur.hours_total:
            if cur.kind == "routine":  # routine work repeats
                cur.hours_done = 0.0
                continue
            if tech.device:
                cur.hours_done, cur.status = cur.hours_total, "awaiting_confirmation"
                continue
            _finish(store, settings, st, tech, cur, t_now)
            finished.append(cur)
    st.version += 1
    return finished


def _cools_off(asset_id: str, powered_off: set[str]) -> bool:
    lay = site_of(asset_id)
    if lay is None:
        return False
    return any(asset_id in r.cooled_by and any(a in powered_off for a in r.asset_ids) for r in lay.racks.values())


def _finish(store: Store, settings: Settings, st: OpsState, tech: Tech, o: Order, t_now: datetime) -> None:
    from . import learning
    from .incidents import resolve

    cfg = config(settings)
    asset = all_assets()[o.asset_id]
    imp = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type)
    labor = o.hours_total * tech.cfg["rate_per_hour"] * (cfg["overtime_multiplier"] if o.overtime else 1.0)
    failed = o.shutdown_seen or (store.live is not None and _already_failed(store, o.asset_id))
    parts = 0.0 if imp is None else (imp.estimated_repair_cost if failed else (imp.planned_repair_cost or imp.estimated_repair_cost))
    mit = o.mitigation_hours * cfg["thermal"]["mitigation_cost_per_hour"] if asset.asset_type == "cooling_unit" else 0.0
    o.cost = WorkOrderCost(labor=round(labor, 2), parts=round(parts, 2), mitigation=round(mit, 2),
                           total=round(labor + parts + mit, 2))
    o.status, o.completed_at, o.mitigation_active = "done", t_now, False
    tech.current = None
    inc = store.incidents.get(o.incident_id) if o.incident_id else None
    if inc is not None and inc.status != "resolved":
        resolve(store, inc, "technician", cfg_cooldown(settings))
    from . import live

    live.mark_repaired(store, o.asset_id)
    if inc is not None:
        learning.record(store, settings, inc, fix=o.title.split(": ", 1)[-1], hours=o.hours_total, cost=o.cost.total,
                        outcome="fixed_after_shutdown" if o.shutdown_seen else "fixed_before_failure", source="technician")


def _already_failed(store: Store, asset_id: str) -> bool:
    """A hashboard, drive or GPU server fault means the part already failed (unplanned part cost), even with no shutdown."""
    f = store.live.faults.get(asset_id) if store.live is not None else None
    return f is not None and f.kind in ("hashboard_failure", "drive_degradation", "gpu_fault", "psu_failure", "server_crash",
                                    "memory_fault", "nic_failure", "server_fan_failure")


def cfg_cooldown(settings: Settings) -> int:
    return 3


def reset(store: Store) -> None:
    """Back to the starting roster (used by /fleet/clear). Learned cases are kept."""
    store.ops = None
