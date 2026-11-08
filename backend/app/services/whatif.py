"""What-if: run an incident forward under three choices and price each future.

- fix_now: the best qualified technician goes now (a routine job may be paused; overtime outside the window).
- wait_for_window: repair in the next maintenance window (data center) or power-price curtailment
  window (mining: miners would be off anyway, so repair hours lose no revenue).
- buy_time: mitigate now (move load and boost the neighbouring cooling unit, or underclock a hot miner),
  then repair in the window. Only where a mitigation exists.

The projection starts from the latest reading and its observed trend (least squares over recent readings,
in demo hours) and steps forward until the repair is done. Thermal paths shut machines down at the limits in
configs/operations.json. Costs use configs/impact_assumptions.json and, for mining, the real hashprice.
Drive and machine models give a 30-day risk, not a failure time, so for them the failure timing is not
projected and the risk is stated instead. Everything here is a labelled projection, not a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Settings
from ..core.errors import not_found
from ..schemas.ops import CurvePoint, OptionCosts, WhatIf, WhatIfOption
from . import impact as impact_service
from . import mining, ops
from .assets import all_assets
from .incidents import now
from .layout import site_of
from .store import Store

STEP = 0.05  # demo hours per projection step
TREND_READINGS = 38  # about one period of the simulator's slow wave, so it averages out


def trend_per_hour(values: list[float], settings: Settings) -> float:
    """Theil-Sen slope (median of pairwise slopes) of the last readings, per demo hour. Robust to the
    sensor wobble and to the jump when a fault starts."""
    ys = values[-TREND_READINGS:]
    n = len(ys)
    if n < 3:
        return 0.0
    slopes = sorted((ys[j] - ys[i]) / (j - i) for i in range(n) for j in range(i + 1, n))
    return slopes[len(slopes) // 2] / ops.tick_hours(settings)


@dataclass
class Path_:
    metric: str | None
    unit: str | None
    value: float | None
    trend: float
    threshold: float | None
    baseline: float | None
    loss_pre: float  # $/h while degraded but running
    loss_down: float  # $/h while shut down
    mitigation: str | None
    rise_factor: float
    mitigation_cost: float  # $/h
    mitigated_loss_pre: float
    risk_note: str | None
    rated: float | None = None


def _series(store: Store, asset_id: str, field: str) -> list[float]:
    with store.lock:
        rows = store.readings.get(asset_id, [])[-TREND_READINGS:]
    return [float(r.reading.values[field]) for r in rows if field in r.reading.values]


def _path(store: Store, settings: Settings, inc, asset, imp) -> Path_:
    cfg = ops.config(settings)
    per_h = imp.cost_per_hour if imp else 0.0
    if inc.detector_id == "cooling-rule-v1":
        ys = _series(store, asset.asset_id, "temperature_c")
        th = cfg["thermal"]
        return Path_("temperature_c", "C", ys[-1] if ys else None, max(0.0, trend_per_hour(ys, settings)),
                     th["rack_shutdown_c"], min(ys) if ys else None, 0.0, per_h, th["mitigation"],
                     th["mitigated_rise_factor"], th["mitigation_cost_per_hour"], 0.0, None)
    if inc.detector_id == "miner-rule-v1":
        hp = mining.hashprice(settings.hashprice_data_path)
        price_h = (hp.usd_per_th_day / 24) if hp else 0.0
        chip = _series(store, asset.asset_id, "chip_temp_c")
        ths = _series(store, asset.asset_id, "hashrate_ths")
        rated = float(store.readings[asset.asset_id][-1].reading.values.get("rated_hashrate_ths", 0)) \
            if store.readings.get(asset.asset_id) else 0.0
        lost_now = max(0.0, rated - (ths[-1] if ths else rated)) * price_h
        mc = cfg["miner"]
        rising = trend_per_hour(chip, settings)
        heat = {e.field for e in inc.evidence} & {"chip_temp_c", "fan_speed_rpm"}
        if chip and heat:  # fan or overheating fault: heading for thermal shutdown
            under = rated * (1 - mc["underclock_hashrate_factor"]) * price_h
            return Path_("chip_temp_c", "C", chip[-1], max(0.0, rising), mc["chip_shutdown_c"], min(chip), lost_now,
                         per_h, mc["mitigation"], mc["mitigated_rise_factor"], 0.0, max(lost_now, under), None)
        return Path_("hashrate_ths", "TH/s", ths[-1] if ths else None, 0.0, None, None, lost_now, per_h, None, 1.0,
                     0.0, lost_now, None, rated=rated)
    cost_fail = impact_service.compute(imp).cost_if_it_fails if imp else None
    note = ("The model gives a high 30-day failure risk, not a failure time, so the timing is not projected. "
            f"If it fails before the repair: about ${cost_fail:,.0f} (downtime plus unplanned repair)." if cost_fail
            else "Failure timing is not projected for this detector.")
    return Path_(None, None, None, 0.0, None, None, 0.0, per_h, None, 1.0, 0.0, 0.0, note)


def _project(p: Path_, start: float | None, repair_h: float, mitigate: bool, site: str, st, settings: Settings,
             horizon: float, restart_h: float):
    """Step forward. Returns (curve, shutdown_at, downtime_h, loss, done_at)."""
    done = None if start is None else start + repair_h
    end = max(horizon, (done or 0) + restart_h + STEP)
    v = p.value
    rise = p.trend * (p.rise_factor if mitigate else 1.0)
    pre = p.mitigated_loss_pre if mitigate else p.loss_pre
    off, shutdown_at, downtime, loss = False, None, 0.0, 0.0
    curve, t, next_pt = [], 0.0, 0.0
    curtail = site == "mining"
    while t <= end + 1e-9:
        fixed = done is not None and t >= done
        if t + 1e-9 >= next_pt and t <= horizon + 1e-9:
            curve.append(CurvePoint(hour=round(t, 2), value=None if v is None else round(v, 2),
                                    power_state="off" if off else "on"))
            next_pt += 0.5
        if v is not None:
            if p.threshold is not None:
                v = v + rise * STEP if not fixed else max(p.baseline or v, v - 6.0 * STEP)
            elif p.rated is not None and fixed:
                v = p.rated
        if p.threshold is not None and not off and not fixed and v is not None and v >= p.threshold:
            off, shutdown_at = True, round(t, 2)
        if off and fixed and t >= done + restart_h:
            off = False
        curtailed = curtail and ops.in_window(site, t, st, settings)
        if off:
            downtime += STEP
        if not curtailed:
            loss += (p.loss_down if off else (0.0 if fixed else pre)) * STEP
        t += STEP
    return curve, shutdown_at, round(downtime, 2), loss, done


def compute(store: Store, settings: Settings, incident_id: str) -> WhatIf:
    cfg = ops.config(settings)
    with store.lock:
        inc = store.incidents.get(incident_id)
        if inc is None:
            raise not_found("INCIDENT_NOT_FOUND", f"Incident '{incident_id}' does not exist.", incident_id=incident_id)
        inc = inc.model_copy()
        st = ops.state(store, settings)
        asset = all_assets()[inc.asset_id]
        lay = site_of(inc.asset_id)
        hall = lay.placements[inc.asset_id].hall_id
        cands = ops.candidates(st, settings, lay.site_id, asset.asset_type, hall)
        win = ops.window(lay.site_id, st, settings)
        t_demo = ops.demo_now(st, settings)
    imp = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type)
    p = _path(store, settings, inc, asset, imp)
    repair_h = imp.estimated_repair_hours if imp and imp.estimated_repair_hours else 1.0
    horizon = float(cfg["projection_hours"])
    restart_h = cfg["thermal"]["restart_hours"]
    already_failed = inc.detector_id == "miner-rule-v1" and p.metric == "hashrate_ths"

    def option(oid: str, label: str, desc: str, cand, start: float | None, mitigate: bool) -> WhatIfOption:
        curve, sd, down, loss, done = _project(p, start, repair_h, mitigate, lay.site_id, st, settings, horizon, restart_h)
        rate = cand.tech.cfg["rate_per_hour"] if cand else 0.0
        overtime = start is not None and not ops.in_window(lay.site_id, start, st, settings)
        labor = repair_h * rate * (cfg["overtime_multiplier"] if overtime else 1.0)
        failed = sd is not None or already_failed
        parts = 0.0 if imp is None else (imp.estimated_repair_cost if failed else (imp.planned_repair_cost or imp.estimated_repair_cost))
        mit = p.mitigation_cost * (done if done is not None else horizon) if mitigate else 0.0
        disp = cand.displaces.delay_cost_per_hour * (repair_h + (start or 0)) if (cand and cand.displaces and oid == "fix_now") else 0.0
        total = labor + parts + loss + mit + disp
        return WhatIfOption(
            option=oid, label=label, description=desc,
            technician_id=cand.tech.cfg["technician_id"] if cand else None,
            technician_name=cand.tech.cfg["name"] if cand else None,
            displaces=cand.displaces.title if (cand and cand.displaces and oid == "fix_now") else None,
            start_in_hours=None if start is None else round(start, 2), done_in_hours=None if done is None else round(done, 2),
            shutdown_at_hours=sd, downtime_hours=down,
            costs=OptionCosts(labor=round(labor, 2), parts=round(parts, 2), downtime_or_lost_revenue=round(loss, 2),
                              mitigation=round(mit, 2), displaced_work=round(disp, 2), total=round(total, 2)),
            risk_note=p.risk_note if oid != "fix_now" else None, curve=curve)

    best = cands[0] if cands else None
    now_start = best.start_in_hours if best else None
    # For a planned repair, prefer someone free (not pulled off a job) and only wait for the window to open.
    later = next((c for c in cands if c.displaces is None), best)
    win_start = None if later is None else max(win.starts_in_hours, later.start_in_hours)
    where = "curtailment window (miners are off then, so repair loses no revenue)" if win.kind == "curtailment" \
        else "nightly maintenance window"
    move = f", moving {best.tech.cfg['name']} off \"{best.displaces.title}\"" if best and best.displaces else ""
    opts = [
        option("fix_now", "Fix now", f"Send {best.tech.cfg['name'] if best else 'a technician'} now{move}.", best, now_start, False),
        option("wait_for_window", f"Wait for the {win.label.lower()}",
               f"Repair in the {where}, starting in {win.starts_in_hours:.1f} h.", later, win_start, False),
    ]
    if p.mitigation:
        # Mitigate now; repair in the window if the mitigation holds until then, otherwise start the repair now.
        mit_sd = _project(p, win_start, repair_h, True, lay.site_id, st, settings, horizon, restart_h)[1]
        if mit_sd is None or win_start is None:
            opts.append(option("buy_time", "Buy time, then fix in the window",
                               f"{p.mitigation} now, then repair in the {where}.", later, win_start, True))
        else:
            opts.append(option("buy_time", "Buy time and fix now",
                               f"{p.mitigation} now so it holds while {best.tech.cfg['name'] if best else 'a technician'}"
                               f" repairs it (the window is too far away).", best, now_start, True))
    worst = max(o.costs.total for o in opts)
    if p.metric is None:  # failure timing unknown: do not gamble on waiting
        rec = opts[0]
        reason = ("Failure timing cannot be predicted from a 30-day risk score, so the safe choice is to fix it now "
                  f"for ${rec.costs.total:,.0f}.")
    else:
        rec = min(opts, key=lambda o: o.costs.total)
        others = ", ".join(f"{o.label.lower()} ${o.costs.total:,.0f}" for o in opts if o is not rec)
        hit = [o.shutdown_at_hours for o in opts if o.shutdown_at_hours is not None]
        sd = f" It avoids the shutdown the other choices hit after {min(hit)} h." if rec.shutdown_at_hours is None and hit else ""
        reason = f"Lowest total cost: ${rec.costs.total:,.0f} (vs {others}).{sd}"
    nothing = _project(p, None, repair_h, False, lay.site_id, st, settings, horizon, restart_h)[1]
    src = cfg["assumptions_source"] + "; " + (imp.assumptions_source if imp else "no impact assumptions")
    return WhatIf(incident_id=inc.incident_id, asset_id=asset.asset_id, asset_name=asset.name, site_id=lay.site_id,
                  generated_at=now(), demo_time=t_demo, metric=p.metric, unit=p.unit,
                  current_value=None if p.value is None else round(p.value, 2),
                  trend_per_hour=round(p.trend, 3) if p.metric else None, shutdown_threshold=p.threshold,
                  shutdown_in_hours=nothing, window=win, options=opts, recommended=rec.option, reason=reason,
                  savings_vs_worst=round(worst - rec.costs.total, 2), assumptions_source=src)


def plan(store: Store, settings: Settings, site: str):
    """Repair plan for one site: open incidents ranked by money saved per technician-hour, each with
    the recommended choice and a technician, moving people off routine work where it pays."""
    from ..schemas.ops import PlanItem, PlanResponse
    from .layout import get_layout

    lay = get_layout(site)
    with store.lock:
        st = ops.state(store, settings)
        incs = [i.model_copy() for i in store.incidents.values() if i.status != "resolved" and i.asset_id in lay.assets]
        t_demo = ops.demo_now(st, settings)
        active = {i.incident_id: ops.active_order_for(st, i.incident_id) for i in incs}
        names = {t: x.cfg["name"] for t, x in st.techs.items()}
    rows = []
    for inc in incs:
        asset = lay.assets[inc.asset_id]
        imp = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type)
        hours = imp.estimated_repair_hours if imp and imp.estimated_repair_hours else 1.0
        savings = impact_service.compute(imp).savings_if_fixed_now if imp else 0.0
        o = active[inc.incident_id]
        if o is not None:
            rows.append((savings / hours, PlanItem(
                incident_id=inc.incident_id, asset_id=asset.asset_id, asset_name=asset.name, title=inc.title,
                risk_level=inc.risk_level, status="dispatched", recommended_option=o.option or "fix_now",
                technician_id=o.technician_id, technician_name=names.get(o.technician_id), move_from=None,
                action=f"{names.get(o.technician_id)} is on it ({o.status.replace('_', ' ')}).", savings=round(savings, 2),
                repair_hours=hours, savings_per_tech_hour=round(savings / hours, 2), work_order_id=o.work_order_id), None))
            continue
        w = compute(store, settings, inc.incident_id)
        rows.append((savings / hours, None, (inc, asset, w, savings, hours)))
    rows.sort(key=lambda r: r[0], reverse=True)
    taken: set[str] = {r[1].technician_id for r in rows if r[1] is not None and r[1].technician_id}
    items = []
    for score, done_item, pending in rows:
        if done_item is not None:
            items.append(done_item)
            continue
        inc, asset, w, savings, hours = pending
        rec = next(o for o in w.options if o.option == w.recommended)
        with store.lock:
            cands = ops.candidates(ops.state(store, settings), settings, site, asset.asset_type,
                                   lay.placements[asset.asset_id].hall_id)
        pick = next((c for c in cands if c.tech.cfg["technician_id"] == rec.technician_id
                     and rec.technician_id not in taken), None) or next(
            (c for c in cands if c.tech.cfg["technician_id"] not in taken), None)
        if pick is None:
            items.append(PlanItem(
                incident_id=inc.incident_id, asset_id=asset.asset_id, asset_name=asset.name, title=inc.title,
                risk_level=inc.risk_level, status="waiting_for_technician", recommended_option=w.recommended,
                technician_id=None, technician_name=None, move_from=None,
                action="Every qualified technician is assigned above; this waits for the next one free.",
                savings=round(savings, 2), repair_hours=hours, savings_per_tech_hour=round(score, 2), work_order_id=None))
            continue
        taken.add(pick.tech.cfg["technician_id"])
        move = pick.displaces.title if (pick.displaces and w.recommended == "fix_now") else None
        action = f"{rec.label}: {pick.tech.cfg['name']} to {asset.name}" + (f", moving off \"{move}\"" if move else "") + "."
        items.append(PlanItem(
            incident_id=inc.incident_id, asset_id=asset.asset_id, asset_name=asset.name, title=inc.title,
            risk_level=inc.risk_level, status="ready", recommended_option=w.recommended,
            technician_id=pick.tech.cfg["technician_id"], technician_name=pick.tech.cfg["name"], move_from=move,
            action=action, savings=round(savings, 2), repair_hours=hours, savings_per_tech_hour=round(score, 2),
            work_order_id=None))
    return PlanResponse(site_id=site, demo_time=t_demo, items=items,
                        total_savings=round(sum(i.savings for i in items), 2),
                        assumptions_source=ops.config(settings)["assumptions_source"])
