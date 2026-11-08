"""GPU servers and the jobs they run: per-GPU status and what slow or stopped GPUs cost right now.

Each data-center row runs one synchronous GPU job across all its servers (configs/datacenter_layout.json).
In a synchronous job every GPU waits for the slowest one at each step, so:
- a throttled GPU slows the whole job to its clock speed;
- a stopped server, a GPU that dropped off the bus, or a powered-off rack stalls the whole job.
A server whose repair work order has "drain" mitigation active has had the job restarted without it,
so only its own GPUs are lost. Prices are the labelled demo assumption in the layout spec.
"""

from __future__ import annotations

from ..schemas.fleet import GpuStatus, JobStatus
from .layout import Job, Layout, site_of
from .store import Store

PRICE_SOURCE = "demo assumption (configs/datacenter_layout.json gpu_server spec), not a quote"


def spec(lay: Layout) -> dict:
    return lay.specs.get("gpu_server", {})


def job_rate(server_id: str) -> tuple[str, int, float] | None:
    """(job name, GPUs in the job, $ per GPU-hour) for a GPU server, None if it runs no job."""
    lay = site_of(server_id)
    job = lay.job_of(server_id) if lay else None
    if job is None:
        return None
    sp = spec(lay)
    return job.name, len(job.server_ids) * int(sp.get("gpus", 8)), float(sp.get("gpu_hour_usd", 0.0))


def _last(store: Store, asset_id: str) -> dict | None:
    rows = store.readings.get(asset_id)
    return rows[-1].reading.values if rows else None


def gpu_list(values: dict | None, lay: Layout) -> list[GpuStatus]:
    sp = spec(lay)
    n, limit = int(sp.get("gpus", 8)), float(sp.get("throttle_c", 83.0))
    out = []
    for i in range(1, n + 1):
        t = values.get(f"gpu{i}_temp_c") if values else None
        c = values.get(f"gpu{i}_clock_pct") if values else None
        if t is None or c is None:
            state = "no_data"
        elif c <= 0:
            state = "offline"
        elif c < 99:
            state = "throttling"
        else:
            state = "ok"
        out.append(GpuStatus(index=i, temp_c=t, clock_pct=c, status=state, throttle_c=limit))
    return out


def job_status(store: Store, lay: Layout, job: Job, power_off: dict[str, str], drained: set[str]) -> JobStatus:
    """Call under store.lock."""
    sp = spec(lay)
    per_server, price = int(sp.get("gpus", 8)), float(sp.get("gpu_hour_usd", 0.0))
    active = [s for s in job.server_ids if s not in drained]
    gpus = len(job.server_ids) * per_server
    pace, throttled, down, reasons = 1.0, 0, [], []
    for s in active:
        v = _last(store, s)
        name = lay.assets[s].name
        if s in power_off:
            down.append(s)
            reasons.append(f"{name} is powered off")
            continue
        if v is None:
            continue
        if not v.get("online", 1):
            down.append(s)
            reasons.append(f"{name} is not responding")
            continue
        if v.get("gpus_online", per_server) < per_server:
            down.append(s)
            reasons.append(f"{name} lost a GPU")
            continue
        throttled += int(v.get("gpus_throttled", 0))
        pace = min(pace, float(v.get("min_gpu_clock_pct", 100.0)) / 100)
    if down:
        pace = 0.0
    elif throttled:
        reasons.append(f"{throttled} GPUs are throttling from heat; the job runs at the slowest GPU's speed")
    running = len(active) * per_server
    lost = (gpus - running) * price + running * price * (1 - pace)
    if drained:
        reasons.append(f"Restarted without {len(drained)} server(s) waiting for repair")
    return JobStatus(job_id=job.job_id, name=job.name, row=job.row, hall_id=job.hall_id, server_ids=list(job.server_ids),
                     gpus=gpus, gpus_running=0 if down else running, pace_pct=round(100 * pace, 1),
                     gpus_throttled=throttled, servers_down=down, lost_usd_per_hour=round(lost, 2),
                     gpu_hour_usd=price, reasons=reasons, assumptions_source=PRICE_SOURCE)


def jobs(store: Store, lay: Layout) -> list[JobStatus]:
    """Every job on a site. Call under store.lock."""
    from . import live, ops

    off = live.power_off(store)
    drained = {s for j in lay.jobs.values() for s in j.server_ids if ops.mitigated(store, s)}
    return [job_status(store, lay, j, off, drained & set(j.server_ids)) for j in lay.jobs.values()]


def lost_per_hour_from_cooling(store: Store, cooling_id: str) -> float:
    """$/h being lost now by jobs on racks this cooling unit serves. Call under store.lock."""
    lay = site_of(cooling_id)
    if lay is None:
        return 0.0
    rows = {r.row for r in lay.racks.values() if cooling_id in r.cooled_by}
    return round(sum(j.lost_usd_per_hour for j in jobs(store, lay) if j.row in rows), 2)
