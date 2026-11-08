"""Parts inside a GPU server (GPUs, CPUs, memory DIMMs, fans, PSUs, network ports, NVMe drives, BMC), each with its
readings and a status, built from the server's readings. Limits are demo assumptions."""

from __future__ import annotations

from ..core.errors import not_found
from ..schemas.fleet import Component, ComponentDetail, ComponentHistoryPoint, ServerComponents
from . import diagnosis
from .layout import site_of
from .store import Store

GPUS, CPUS, DIMMS, FANS, PSUS, NICS, NVMES = 8, 2, 16, 6, 2, 2, 2


def _server(server_id: str) -> None:
    layout = site_of(server_id)
    if layout is None or layout.assets[server_id].asset_type != "gpu_server":
        raise not_found("SERVER_NOT_FOUND", f"GPU server '{server_id}' does not exist.", server_id=server_id)


def _parts(v: dict) -> list[Component]:
    online = v.get("online", 1) >= 1
    out: list[Component] = []

    def add(cid, kind, name, status, metrics, note=None):
        if not online and kind != "bmc":
            status, note = "offline", "Server is not responding."
        out.append(Component(component_id=cid, kind=kind, name=name, status=status,
                             metrics={k: x for k, x in metrics.items() if isinstance(x, (int, float))}, note=note))

    for i in range(1, GPUS + 1):
        t, c = v.get(f"gpu{i}_temp_c"), v.get(f"gpu{i}_clock_pct")
        st, note = "ok", None
        if c == 0:
            st, note = "failed", "Dropped off the bus."
        elif c is not None and c < 99:
            st, note = "warning", f"Throttling to {c:.0f}% clock to protect itself from heat."
        add(f"gpu{i}", "gpu", f"GPU {i}", st, {"temp_c": t, "clock_pct": c}, note)
    for i in range(1, CPUS + 1):
        t = v.get(f"cpu{i}_temp_c")
        st = "warning" if t is not None and t > 85 else "ok"
        add(f"cpu{i}", "cpu", f"CPU {i}", st, {"temp_c": t, "util_pct": v.get("cpu_util_pct")},
            "Running hot." if st == "warning" else None)
    for i in range(1, DIMMS + 1):
        e = v.get(f"dimm{i}_ecc", 0)
        st = "failed" if e > 300 else "warning" if e > 100 else "ok"
        add(f"dimm{i}", "dimm", f"Memory DIMM {i}", st, {"ecc_errors": e},
            f"{e:.0f} correctable memory errors." if e else None)
    for i in range(1, FANS + 1):
        r = v.get(f"fan{i}_rpm")
        st = "failed" if r is not None and r < 500 else "warning" if r is not None and r < 3000 else "ok"
        add(f"fan{i}", "fan", f"Fan {i}", st, {"rpm": r}, "Stopped." if st == "failed" else "Slow." if st == "warning" else None)
    for i in range(1, PSUS + 1):
        w = v.get(f"psu{i}_w")
        dead = v.get("psu_ok", 2) < 2 and w == 0
        add(f"psu{i}", "psu", f"Power supply {i}", "failed" if dead else "ok", {"watts": w},
            "No output: the server is running on the other supply." if dead else None)
    for i in range(1, NICS + 1):
        link = v.get(f"nic{i}_link", 1)
        crc = v.get("nic_crc_errors", 0) if link == 0 or v.get("nic_links_up", NICS) < NICS else 0
        st = "failed" if link == 0 else "warning" if v.get("nic_crc_errors", 0) > 100 and v.get("nic_links_up", 2) == 2 else "ok"
        add(f"nic{i}", "nic", f"Network port {i}", st, {"link_up": link, "crc_errors": crc},
            "Link down." if st == "failed" else None)
    for i in range(1, NVMES + 1):
        wear = v.get(f"nvme{i}_wear_pct")
        st = "warning" if wear is not None and wear > 80 else "ok"
        add(f"nvme{i}", "nvme", f"NVMe drive {i}", st, {"wear_pct": wear, "temp_c": v.get("nvme_temp_c")})
    add("bmc", "bmc", "Management controller (BMC)", "ok" if v.get("bmc_ok", 1) else "failed", {"ok": v.get("bmc_ok", 1)})
    return out


def _values(store: Store, server_id: str, n: int) -> list:
    with store.lock:
        return list(store.readings.get(server_id, [])[-n:])


def server_components(store: Store, server_id: str) -> ServerComponents:
    _server(server_id)
    rows = _values(store, server_id, 1)
    v = dict(rows[-1].reading.values) if rows else {}
    return ServerComponents(server_id=server_id, observed_at=rows[-1].reading.observed_at if rows else None,
                            components=_parts(v) if v else [])


def component_detail(store: Store, server_id: str, component_id: str, history: int) -> ComponentDetail:
    _server(server_id)
    rows = _values(store, server_id, max(1, history))
    if not rows:
        raise not_found("COMPONENT_NOT_FOUND", "No readings for this server yet.", server_id=server_id)
    latest = next((c for c in _parts(dict(rows[-1].reading.values)) if c.component_id == component_id), None)
    if latest is None:
        raise not_found("COMPONENT_NOT_FOUND", f"Server '{server_id}' has no part '{component_id}'.",
                        server_id=server_id, component_id=component_id)
    hist = []
    for r in rows:
        c = next(x for x in _parts(dict(r.reading.values)) if x.component_id == component_id)
        hist.append(ComponentHistoryPoint(observed_at=r.reading.observed_at, status=c.status, metrics=c.metrics))
    mode = None
    if latest.status in ("warning", "failed", "offline"):
        mode = diagnosis.diagnose("gpu_server", [dict(r.reading.values) for r in rows])
    return ComponentDetail(server_id=server_id, component=latest, history=hist, failure_mode=mode)
