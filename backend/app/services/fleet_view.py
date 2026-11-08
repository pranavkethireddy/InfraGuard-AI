"""Floor map, rack status and machine status, built from stored readings, predictions and incidents.

Two sites (data center and crypto mining farm); every view takes a site id.
Status per machine:
- critical: an unresolved high-risk incident, or the latest prediction is high risk
- warning: latest prediction is medium, or any other unresolved incident
- healthy: latest prediction is low
- no_data: no prediction yet
A rack takes the worst status of its machines, and is at least "warning" when a cooling unit
that serves it is not healthy. A hall takes the worst status of its racks and machines.
"""

from __future__ import annotations

from ..core.config import Settings
from ..core.errors import not_found
from ..schemas.fleet import (FleetMap, FleetStatus, FleetSummary, HallMap, HistoryPoint, IncidentBrief,
                             MachineStatus, RackDetail, RackStatus, ServerDetail, SiteInfo, SiteMetric, SitesResponse,
                             WorkOrderBrief)
from ..schemas.incidents import IncidentDetail
from . import impact as impact_service
from . import gpus, live, mining, ops, whatif
from .incidents import now, summary
from .layout import Layout, Rack, all_layouts, get_layout
from .store import Store

RANK = {"no_data": 0, "healthy": 1, "warning": 2, "critical": 3}
_RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def worst(statuses) -> str:
    return max(statuses, key=RANK.__getitem__, default="no_data")


class Snapshot:
    """One consistent read of the store under its lock."""

    def __init__(self, store: Store, layout: Layout, history: int, settings: Settings):
        self.layout = layout
        self.settings = settings
        with store.lock:
            self.latest = dict(store.latest_prediction)
            self.readings = {a: [r.reading for r in rows[-max(history, 1):]] for a, rows in store.readings.items()}
            self.open: dict[str, IncidentDetail] = {}
            for inc in store.incidents.values():
                if inc.status == "resolved" or inc.asset_id not in layout.assets:
                    continue
                cur = self.open.get(inc.asset_id)
                if cur is None or _RISK_RANK[inc.risk_level] > _RISK_RANK[cur.risk_level]:
                    self.open[inc.asset_id] = inc.model_copy()
            self.faults = {a: live.fault_for(store, a) for a in layout.assets}
            self.power_off = live.power_off(store)
            st = ops.state(store, settings)
            names = {t: x.cfg["name"] for t, x in st.techs.items()}
            self.orders = {}
            for o in st.orders.values():
                if o.asset_id in layout.assets and o.status != "done":
                    self.orders[o.asset_id] = WorkOrderBrief(
                        work_order_id=o.work_order_id, technician_id=o.technician_id,
                        technician_name=names.get(o.technician_id, o.technician_id), status=o.status, option=o.option,
                        progress=round(min(1.0, o.hours_done / o.hours_total) if o.hours_total else 1.0, 3),
                        eta_minutes=ops.work_order(o, st, settings).eta_minutes)
            self.techs_busy = sum(1 for t in st.techs.values() if t.cfg["site"] == layout.site_id and t.current
                                  and st.orders[t.current].kind == "repair")
            self.techs_total = sum(1 for t in st.techs.values() if t.cfg["site"] == layout.site_id)
            self.in_window = ops.in_window(layout.site_id, 0.0, st, settings)
            self.jobs = gpus.jobs(store, layout)
            trend_rows = {a: [r.reading for r in store.readings.get(a, [])[-whatif.TREND_READINGS:]]
                          for a, x in layout.assets.items() if x.asset_type in ("cooling_unit", "asic_miner")}
        self.eta = self._etas(trend_rows)
        self.live = live.status(store, settings)
        self.history = history
        self.settings = settings
        self.machines = {a: self._machine(a) for a in layout.assets}

    def _machine(self, asset_id: str) -> MachineStatus:
        asset = self.layout.assets[asset_id]
        pred = self.latest.get(asset_id)
        inc = self.open.get(asset_id)
        rows = self.readings.get(asset_id, [])
        if (inc and inc.risk_level == "high") or (pred and pred.risk_level == "high"):
            st = "critical"
        elif (pred and pred.risk_level == "medium") or inc:
            st = "warning"
        else:
            st = "healthy" if pred else "no_data"
        brief = None
        if inc is not None:
            brief = IncidentBrief(
                incident_id=inc.incident_id, title=inc.title, status=inc.status, risk_level=inc.risk_level,
                opened_at=inc.opened_at, estimated_total_impact=inc.impact.estimated_total_impact if inc.impact else None,
                cost_per_day=inc.impact.cost_per_day if inc.impact else None, investigation_status=inc.investigation_status)
        off = self.power_off.get(asset_id)
        eta = self.eta.get(asset_id)
        if off:
            st = "critical"
        return MachineStatus(
            power_state="off" if off else ("at_risk" if eta is not None else "on"), power_reason=off,
            shutdown_eta_minutes=None if off else eta, work_order=self.orders.get(asset_id),
            asset_id=asset_id, name=asset.name, asset_type=asset.asset_type, criticality=asset.criticality,
            detector_id=asset.compatible_detector, location=asset.location, placement=self.layout.placements[asset_id],
            status=st, risk_level=pred.risk_level if pred else None, risk_score=pred.risk_score if pred else None,
            latest_values=dict(rows[-1].values) if rows else None, last_reading_at=rows[-1].observed_at if rows else None,
            chart_fields=self.layout.chart_fields.get(asset.asset_type, []), active_incident=brief,
            simulated_fault=self.faults.get(asset_id),
            history=[HistoryPoint(observed_at=r.observed_at, values=r.values) for r in rows[-self.history:]] if self.history else [],
        )

    def _etas(self, rows: dict) -> dict[str, float]:
        """Demo minutes until thermal shutdown from the observed trend, if within the projection horizon.
        A cooling unit's ETA also applies to every machine in the racks it cools."""
        cfg = ops.config(self.settings)
        horizon_min = cfg["projection_hours"] * 60
        out: dict[str, float] = {}

        alert = {"cooling_unit": 32.0, "asic_miner": 85.0}  # only machines already past their alert level

        def eta(vals: list[float], limit: float, floor: float) -> float | None:
            if len(vals) < 3 or vals[-1] >= limit or vals[-1] <= floor:
                return None
            rise = whatif.trend_per_hour(vals, self.settings)
            if rise <= 0.05:
                return None
            m = (limit - vals[-1]) / rise * 60
            return round(m, 1) if m <= horizon_min else None

        for a, rs in rows.items():
            t = self.layout.assets[a].asset_type
            fld, limit = ("temperature_c", cfg["thermal"]["rack_shutdown_c"]) if t == "cooling_unit" else \
                ("chip_temp_c", cfg["miner"]["chip_shutdown_c"])
            v = eta([float(r.values[fld]) for r in rs if fld in r.values], limit, alert[t])
            if v is None or a in self.power_off:
                continue
            if t == "cooling_unit":
                for rack in self.layout.racks.values():
                    if a in rack.cooled_by:
                        for m in rack.asset_ids:
                            out[m] = min(out.get(m, v), v)
            else:
                out[a] = min(out.get(a, v), v)
        return out

    def rack(self, rack: Rack) -> RackStatus:
        ms = [self.machines[a] for a in rack.asset_ids]
        reasons, statuses = [], [m.status for m in ms]
        if any(m.power_state == "off" for m in ms):
            reasons.append(next(m.power_reason for m in ms if m.power_state == "off"))
        etas = [m.shutdown_eta_minutes for m in ms if m.shutdown_eta_minutes is not None]
        if etas:
            reasons.append(f"Projected thermal shutdown in about {min(etas):.0f} min (demo time) unless fixed")
        for m in ms:
            if m.status in ("warning", "critical") and m.power_state != "off":
                # Incident titles already name the machine.
                reasons.append(m.active_incident.title if m.active_incident else f"{m.name}: {m.risk_level} risk reading")
        hot = sum(int((m.latest_values or {}).get("gpus_throttled", 0)) for m in ms
                  if m.asset_type == "gpu_server" and m.power_state != "off")
        if hot:
            reasons.append(f"{hot} GPUs throttling from heat")
        for c in rack.cooled_by:
            cu = self.machines.get(c)
            if cu is not None and cu.status in ("warning", "critical"):
                reasons.append(f"Cooling unit {cu.name} serving this rack is {cu.status}")
                statuses.append("warning")
        return RackStatus(
            rack_id=rack.rack_id, hall_id=rack.hall_id, row=rack.row, label=rack.label, x=rack.x, y=rack.y,
            width=rack.width, depth=rack.depth, status=worst(statuses), reasons=reasons, cooled_by=list(rack.cooled_by),
            machine_ids=list(rack.asset_ids),
            open_incident_ids=[m.active_incident.incident_id for m in ms if m.active_incident],
            power_state="off" if any(m.power_state == "off" for m in ms) else ("at_risk" if etas else "on"),
            shutdown_eta_minutes=min(etas) if etas else None)

    def summary(self, racks: list[RackStatus]) -> FleetSummary:
        counts = {k: 0 for k in RANK}
        for m in self.machines.values():
            counts[m.status] += 1
        impacts = [i.impact for i in self.open.values() if i.impact]
        per_day = sum(m.cost_per_day or 0.0 for m in impacts)
        any_impact = next((i.impact for i in self.open.values() if i.impact), None)
        currency, source = "USD", None
        if any_impact is not None:
            currency, source = any_impact.currency, any_impact.assumptions_source
        else:
            a = next(iter(self.layout.assets.values()))
            dflt = impact_service.for_asset(self.settings.impact_assumptions_path, a.asset_id, a.asset_type)
            if dflt is not None:
                currency, source = dflt.currency, dflt.assumptions_source
        return FleetSummary(
            machines=len(self.machines), racks=len(self.layout.racks), healthy=counts["healthy"],
            warning=counts["warning"], critical=counts["critical"], no_data=counts["no_data"],
            open_incidents=sum(1 for _ in self.open.values()),
            racks_affected=sum(1 for r in racks if r.status in ("warning", "critical")),
            downtime_cost_per_day_at_risk=round(per_day, 2), currency=currency, assumptions_source=source,
            machines_powered_off=sum(m.power_state == "off" for m in self.machines.values()),
            machines_at_risk_of_shutdown=sum(m.power_state == "at_risk" for m in self.machines.values()),
            cost_if_all_fail=round(sum(m.cost_if_it_fails or 0.0 for m in impacts), 2),
            cost_to_fix_all_now=round(sum(m.cost_to_fix_now or 0.0 for m in impacts), 2),
            savings_if_fixed_now=round(sum(m.savings_if_fixed_now or 0.0 for m in impacts), 2))

    def metrics(self) -> list[SiteMetric]:
        ms = list(self.machines.values())
        scored = [m for m in ms if m.status != "no_data"]
        live_src = "live readings (simulated)"
        healthy = round(100 * sum(m.status == "healthy" for m in scored) / len(scored), 1) if scored else None
        ops_src = "crew model (configs/operations.json, demo assumption)"
        out = [SiteMetric(key="healthy_pct", label="Machines healthy", value=healthy, unit="%", source=live_src),
               SiteMetric(key="powered_off", label="Machines powered off", value=sum(m.power_state == "off" for m in ms),
                          unit="machines", source=live_src),
               SiteMetric(key="technicians_on_repairs", label="Technicians on repairs", value=self.techs_busy,
                          unit=f"of {self.techs_total}", source=ops_src)]
        if self.layout.site_id == "mining":
            return out + self._mining(ms, live_src)
        if self.jobs:
            gsrc = f"live GPU readings (simulated) x GPU-hour price ({gpus.PRICE_SOURCE})"
            out += [
                SiteMetric(key="gpus_throttling", label="GPUs slowed by heat",
                           value=sum(j.gpus_throttled for j in self.jobs), unit=f"of {sum(j.gpus for j in self.jobs)}",
                           source="live GPU readings (simulated)"),
                SiteMetric(key="gpu_compute_lost_per_hour", label="GPU compute lost right now",
                           value=round(sum(j.lost_usd_per_hour for j in self.jobs), 2), unit="USD/h", source=gsrc),
                SiteMetric(key="gpu_jobs_full_speed", label="GPU jobs at full speed",
                           value=sum(j.pace_pct >= 99 for j in self.jobs), unit=f"of {len(self.jobs)}",
                           source="live GPU readings (simulated)"),
            ]
        drives = [m for m in ms if m.asset_type == "storage_drive"]
        coolers = [m.latest_values["temperature_c"] for m in ms if m.asset_type == "cooling_unit" and m.latest_values]
        return out + [
            SiteMetric(key="drives_at_risk", label="Drives predicted to fail (30 days)",
                       value=sum(m.risk_level in ("medium", "high") for m in drives), unit="drives",
                       source="drive-failure-v1, trained on Backblaze Drive Stats"),
            SiteMetric(key="max_supply_temp_c", label="Hottest cooling unit", value=max(coolers) if coolers else None,
                       unit="C", source=live_src),
        ]

    def _mining(self, ms: list[MachineStatus], live_src: str) -> list[SiteMetric]:
        # A powered-off miner earns nothing; count it at zero hashrate and power.
        miners = [m.latest_values if m.power_state != "off" else
                  {"hashrate_ths": 0.0, "rated_hashrate_ths": m.latest_values["rated_hashrate_ths"], "power_w": 0.0}
                  for m in ms if m.asset_type == "asic_miner" and m.latest_values]
        hp = mining.hashprice(self.settings.hashprice_data_path)
        actual = sum(float(v["hashrate_ths"]) for v in miners)
        rated = sum(float(v["rated_hashrate_ths"]) for v in miners)
        lost_ths = sum(max(0.0, float(v["rated_hashrate_ths"]) - float(v["hashrate_ths"])) for v in miners)
        power_w = sum(float(v.get("power_w", 0)) for v in miners)
        price = hp.usd_per_th_day if hp else None
        hp_src = f"{mining.SOURCE}, {hp.as_of}" if hp else "hashprice data missing"
        have = bool(miners)
        return [
            SiteMetric(key="hashrate_phs", label="Farm hashrate", value=round(actual / 1000, 2) if have else None,
                       unit="PH/s", source=live_src),
            SiteMetric(key="hashrate_availability_pct", label="Hashrate vs rated",
                       value=round(100 * actual / rated, 1) if rated else None, unit="%", source=live_src),
            SiteMetric(key="revenue_per_day", label="Mining revenue per day",
                       value=round(actual * price, 2) if have and price else None, unit="USD/day",
                       source=f"farm hashrate x hashprice ({hp_src})"),
            SiteMetric(key="revenue_lost_per_day", label="Revenue lost to faults per day",
                       value=round(lost_ths * price, 2) if have and price else None, unit="USD/day",
                       source=f"hashrate below rated x hashprice ({hp_src})"),
            SiteMetric(key="efficiency_j_per_th", label="Energy efficiency",
                       value=round(power_w / actual, 2) if actual else None, unit="J/TH", source=live_src),
            SiteMetric(key="power_kw", label="Power draw", value=round(power_w / 1000, 1) if have else None,
                       unit="kW", source=live_src),
            SiteMetric(key="hashprice_usd_per_th_day", label="Hashprice", value=price, unit="USD/TH/day", source=hp_src),
            SiteMetric(key="breakeven_power_usd_per_mwh", label="Break-even power price",
                       value=ops.breakeven_usd_per_mwh(self.settings), unit="USD/MWh",
                       source=f"hashprice x rated hashrate / rated power ({hp_src})"),
            SiteMetric(key="curtailed_now", label="In curtailment window (power costs more than mining earns)",
                       value=1.0 if self.in_window else 0.0, unit="bool",
                       source=ops.config(self.settings)["sites"]["mining"]["power_price_source"]),
        ]


def fleet_map(store: Store, settings: Settings, history: int, site: str = "datacenter") -> FleetMap:
    layout = get_layout(site)
    snap = Snapshot(store, layout, history, settings)
    racks = {r.rack_id: snap.rack(r) for r in layout.racks.values()}
    halls = []
    for h in layout.halls:
        hr = [racks[r] for r in h.rack_ids]
        units = [snap.machines[u] for u in h.unit_ids]
        rack_machines = [snap.machines[a] for r in h.rack_ids for a in layout.racks[r].asset_ids]
        halls.append(HallMap(hall_id=h.hall_id, name=h.name, kind=h.kind, width=h.width, depth=h.depth,
                             status=worst([r.status for r in hr] + [u.status for u in units]),
                             racks=hr, machines=units + rack_machines))
    return FleetMap(site_id=layout.site_id, site_name=layout.site_name, grid_unit=layout.grid_unit, generated_at=now(),
                    live=snap.live, summary=snap.summary(list(racks.values())), site_metrics=snap.metrics(), halls=halls,
                    jobs=snap.jobs)


def fleet_status(store: Store, settings: Settings, history: int, status: str | None, hall_id: str | None,
                 site: str = "datacenter") -> FleetStatus:
    layout = get_layout(site)
    snap = Snapshot(store, layout, history, settings)
    racks = [snap.rack(r) for r in layout.racks.values()]
    ms = [m for m in snap.machines.values()
          if (status is None or m.status == status) and (hall_id is None or m.placement.hall_id == hall_id)]
    ms.sort(key=lambda m: (-RANK[m.status], m.asset_id))
    return FleetStatus(site_id=layout.site_id, generated_at=now(), live=snap.live, summary=snap.summary(racks),
                       site_metrics=snap.metrics(), machines=ms)


def sites(store: Store, settings: Settings) -> SitesResponse:
    """Both sites with their summary and metric tiles, for the site switcher."""
    out, live_status = [], None
    for layout in all_layouts():
        snap = Snapshot(store, layout, 0, settings)
        live_status = snap.live
        out.append(SiteInfo(site_id=layout.site_id, name=layout.site_name, machines=len(layout.assets),
                            racks=len(layout.racks), summary=snap.summary([snap.rack(r) for r in layout.racks.values()]),
                            site_metrics=snap.metrics()))
    return SitesResponse(generated_at=now(), live=live_status, sites=out)


def rack_detail(store: Store, settings: Settings, rack_id: str, history: int) -> RackDetail:
    layout = next((lay for lay in all_layouts() if rack_id in lay.racks), get_layout())
    rack = layout.racks.get(rack_id)
    if rack is None:
        raise not_found("RACK_NOT_FOUND", f"Rack '{rack_id}' does not exist.", rack_id=rack_id)
    snap = Snapshot(store, layout, history, settings)
    with store.lock:
        incs = [summary(i) for i in store.incidents.values() if i.asset_id in rack.asset_ids]
    incs.sort(key=lambda i: i.opened_at, reverse=True)
    return RackDetail(**snap.rack(rack).model_dump(), machines=[snap.machines[a] for a in rack.asset_ids],
                      server_ids=list(rack.server_ids),
                      cooling_units=[snap.machines[c] for c in rack.cooled_by if c in snap.machines], incidents=incs)


def server_detail(store: Store, settings: Settings, server_id: str, history: int) -> ServerDetail:
    """One GPU server: its 8 GPUs, power supplies, inlet air, and the job it is part of."""
    layout = next((lay for lay in all_layouts() if server_id in lay.assets), None)
    if layout is None or layout.assets[server_id].asset_type != "gpu_server":
        raise not_found("SERVER_NOT_FOUND", f"GPU server '{server_id}' does not exist.", server_id=server_id)
    snap = Snapshot(store, layout, history, settings)
    m = snap.machines[server_id]
    rack = layout.racks[m.placement.rack_id]
    v = m.latest_values if m.power_state != "off" else None
    job = layout.job_of(server_id)
    num = lambda k: v.get(k) if v else None  # noqa: E731
    return ServerDetail(
        machine=m, rack_id=rack.rack_id, inlet_temp_c=num("inlet_temp_c"),
        online=None if v is None else bool(v.get("online", 1)), psus_ok=num("psu_ok"), psus_total=2,
        ecc_errors=num("ecc_errors"), power_w=0.0 if m.power_state == "off" else num("power_w"),
        gpus=gpus.gpu_list(v, layout) if m.power_state != "off" else
        [g.model_copy(update={"status": "offline", "clock_pct": 0.0}) for g in gpus.gpu_list(None, layout)],
        job=next((j for j in snap.jobs if job and j.job_id == job.job_id), None),
        cooled_by=[snap.machines[c] for c in rack.cooled_by if c in snap.machines])
