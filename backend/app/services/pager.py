"""Technician pager (e.g. an iPad): claim a technician, see their job, accept, decline or confirm done.

A claimed technician is device-controlled: a repair sent to them waits as "paged" until the pager
accepts it, then they walk to it and work; when the planned hours are used up the job waits as
"awaiting_confirmation" until the pager confirms done (they can also confirm earlier). Declining hands
the job to the next closest qualified technician. Automatic dispatch sends every new incident to the
closest qualified technician as soon as it opens.
"""

from __future__ import annotations

import logging

from ..core.config import Settings
from ..core.errors import ApiError, not_found
from ..schemas.ops import DispatchRequest, PagerActionRequest, PagerJob, PagerView
from . import impact as impact_service
from . import ops
from .assets import all_assets
from .store import Store

log = logging.getLogger(__name__)


def _tech(st: ops.OpsState, tech_id: str) -> ops.Tech:
    t = st.techs.get(tech_id)
    if t is None:
        raise not_found("TECHNICIAN_NOT_FOUND", f"Technician '{tech_id}' does not exist.", technician_id=tech_id)
    return t


def claim(store: Store, settings: Settings, tech_id: str, on: bool) -> PagerView:
    with store.lock:
        st = ops.state(store, settings)
        t = _tech(st, tech_id)
        from . import chaos

        if not on and chaos.holds_device(store, settings, tech_id):
            return view(store, settings, tech_id)  # stays on the iPad while chaos mode runs
        t.device = on
        cur = st.orders.get(t.current) if t.current else None
        if not on and cur is not None and cur.status == "paged":
            ops._set_off(st, settings, t, cur)  # released: the simulation takes the job on
        if not on and cur is not None and cur.status == "awaiting_confirmation":
            _done(store, settings, st, t, cur)
        st.version += 1
    return view(store, settings, tech_id)


def view(store: Store, settings: Settings, tech_id: str) -> PagerView:
    with store.lock:
        st = ops.state(store, settings)
        t = _tech(st, tech_id)
        cur = st.orders.get(t.current) if t.current else None
        if cur is not None and cur.kind != "repair":
            cur = None
        job = _job(store, settings, st, t, cur) if cur else None
        queue = [ops.work_order(st.orders[i], st, settings) for i in t.queue if st.orders[i].kind == "repair"]
        return PagerView(technician=ops.technician(t, st, settings), job=job, queue=queue,
                         demo_time=ops.demo_now(st, settings), version=st.version)


def _job(store: Store, settings: Settings, st: ops.OpsState, t: ops.Tech, o: ops.Order) -> PagerJob:
    inc = store.incidents.get(o.incident_id) if o.incident_id else None
    asset = all_assets().get(o.asset_id) if o.asset_id else None
    imp = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type) if asset else None
    business = impact_service.compute(imp) if imp else None
    actions = {"traveling": ["done"], "in_progress": ["done"],
               "awaiting_confirmation": ["done"]}.get(o.status, [])
    steps = list(inc.recommended_actions) if inc else [o.title]
    return PagerJob(
        work_order=ops.work_order(o, st, settings), asset_id=o.asset_id, asset_name=asset.name if asset else None,
        location=asset.location if asset else None, incident_id=o.incident_id, risk_level=inc.risk_level if inc else None,
        problem=inc.problem if inc else None, likely_cause=inc.likely_cause if inc else None, steps=steps,
        why_you=o.why or "Assigned by the operator.",
        savings_if_fixed_now=business.savings_if_fixed_now if business else None,
        cost_per_hour_while_down=imp.cost_per_hour if imp else None,
        walking_minutes_left=round(o.travel_left * 60, 1) if o.status == "traveling" else None, actions=actions)


def act(store: Store, settings: Settings, tech_id: str, req: PagerActionRequest) -> PagerView:
    redispatch = None
    with store.lock:
        st = ops.state(store, settings)
        t = _tech(st, tech_id)
        o = st.orders.get(req.work_order_id)
        if o is None or o.technician_id != tech_id or o.kind != "repair" or o.status == "done":
            raise ApiError(409, "NOT_YOUR_JOB", "This work order is not an open repair for this technician.",
                           {"work_order_id": req.work_order_id, "technician_id": tech_id})
        if req.action == "accept":
            if o.status != "paged":
                raise ApiError(409, "NOT_PAGED", "Only a paged job can be accepted.", {"status": o.status})
            ops._set_off(st, settings, t, o)
        elif req.action == "decline":
            if o.status != "paged":
                raise ApiError(409, "NOT_PAGED", "Only a paged job can be declined.", {"status": o.status})
            t.current = None
            o.status, o.completed_at = "done", ops.demo_now(st, settings)  # closed, handed to someone else
            o.title = f"{o.title} (declined by {t.cfg['name']})"
            inc = store.incidents.get(o.incident_id)
            if inc is not None:
                inc.work_order_id = None
            redispatch = (o.incident_id, o.option, (*o.declined_by, tech_id))
        else:  # done
            if o.status not in ("traveling", "in_progress", "awaiting_confirmation"):
                raise ApiError(409, "NOT_STARTED", "Accept the job before confirming it done.", {"status": o.status})
            _done(store, settings, st, t, o)
        st.version += 1
    if redispatch is not None:
        inc_id, option, excluded = redispatch
        try:
            ops.dispatch(store, settings, DispatchRequest(incident_id=inc_id, option=option), exclude=excluded)
        except ApiError as e:
            log.info("no one else to take %s: %s", inc_id, e.code)
    return view(store, settings, tech_id)


def _done(store: Store, settings: Settings, st: ops.OpsState, t: ops.Tech, o: ops.Order) -> None:
    """Finish now; labor counts the hours actually worked (at least a quarter hour)."""
    if o.status == "traveling":
        t.pos, t.path, t.location = o.spot or t.pos, [], o.hall_id
    o.travel_left = 0.0
    o.hours_total = max(0.25, min(o.hours_total, o.hours_done)) if o.status != "awaiting_confirmation" else o.hours_total
    o.hours_done = o.hours_total
    ops._finish(store, settings, st, t, o, ops.demo_now(st, settings))


def set_auto(store: Store, settings: Settings, enabled: bool) -> bool:
    with store.lock:
        st = ops.state(store, settings)
        st.auto_dispatch = enabled
        st.version += 1
        return st.auto_dispatch


def escalate(store: Store, settings: Settings, incident_id: str, exclude: tuple[str, ...] = (),
             prefer: str | None = None, option: str | None = None) -> None:
    """An incident got more urgent: page someone if nobody has it yet. A repair already planned stops waiting for
    the maintenance window and moves up its technician's queue (queues follow priority); the job the technician
    is doing now is never interrupted."""
    with store.lock:
        st = ops.state(store, settings)
        inc = store.incidents.get(incident_id)
        if not st.auto_dispatch or inc is None or inc.status == "resolved":
            return
        o = ops.active_order_for(st, incident_id)
        if o is not None:
            if o.status == "scheduled" and o.scheduled_start is not None:
                tech = st.techs[o.technician_id]
                o.scheduled_start, o.option = None, "fix_now"
                o.why = f"Escalated to priority {inc.priority_rank} ({inc.risk_level} risk): next in your queue."
                if o.work_order_id not in tech.queue:
                    tech.queue.append(o.work_order_id)
                st.version += 1
            return
    auto_dispatch(store, settings, incident_id, exclude, prefer, option)


def auto_dispatch(store: Store, settings: Settings, incident_id: str, exclude: tuple[str, ...] = (),
                  prefer: str | None = None, option: str | None = None) -> None:
    """Send a newly opened incident to the closest qualified technician (recommended option), or to `prefer`
    first when given (falls back to the closest if they cannot take it)."""
    with store.lock:
        st = ops.state(store, settings)
        inc = store.incidents.get(incident_id)
        if not st.auto_dispatch or inc is None or inc.status == "resolved" or ops.active_order_for(st, incident_id):
            return
    if prefer is not None:
        try:
            ops.dispatch(store, settings, DispatchRequest(incident_id=incident_id, technician_id=prefer, option=option),
                         exclude)
            return
        except ApiError as e:  # not qualified or on another repair: the closest one goes instead
            log.info("auto dispatch: %s cannot take %s (%s)", prefer, incident_id, e.code)
    try:
        ops.dispatch(store, settings, DispatchRequest(incident_id=incident_id, option=option), exclude)
    except ApiError as e:
        if option is not None:  # that option is not on this incident's plan: use the recommended one
            auto_dispatch(store, settings, incident_id, exclude, prefer)
            return
        log.info("auto dispatch skipped for %s: %s", incident_id, e.code)
