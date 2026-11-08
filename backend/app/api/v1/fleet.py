from typing import Annotated

from fastapi import APIRouter, Body, Query

from ...schemas.errors import ErrorResponse
from ...schemas.fleet import (ChaosRequest, ChaosStatus, ClearResponse, FaultRequest, FaultResponse, FleetMap, FleetStatus, HealthStatus,
                              LiveStartRequest, LiveStatus, RackDetail, ServerDetail, SiteId, SitesResponse)
from ...services import chaos, fleet_view, live
from ..deps import SettingsDep, StoreDep

router = APIRouter(prefix="/fleet", tags=["fleet"])
History = Annotated[int, Query(ge=0, le=300, description="Recent readings to include per machine")]
Site = Annotated[SiteId, Query(description="datacenter or mining (crypto mining farm)")]


@router.get("/sites", response_model=SitesResponse)
def get_sites(store: StoreDep, settings: SettingsDep) -> SitesResponse:
    """Both sites with summary and metric tiles, for the data center / crypto switch."""
    return fleet_view.sites(store, settings)


@router.get("/map", response_model=FleetMap)
def get_map(store: StoreDep, settings: SettingsDep, history: History = 0, site: Site = "datacenter") -> FleetMap:
    """Whole site for the overview: halls, racks with positions and status, and every machine."""
    return fleet_view.fleet_map(store, settings, history, site)


@router.get("/status", response_model=FleetStatus)
def get_status(store: StoreDep, settings: SettingsDep, history: History = 30, status: HealthStatus | None = None,
               hall_id: str | None = None, site: Site = "datacenter") -> FleetStatus:
    """Every machine with status, latest values and recent history; worst first."""
    return fleet_view.fleet_status(store, settings, history, status, hall_id, site)


@router.get("/racks/{rack_id}", response_model=RackDetail, responses={404: {"model": ErrorResponse}})
def get_rack(rack_id: str, store: StoreDep, settings: SettingsDep, history: History = 60) -> RackDetail:
    return fleet_view.rack_detail(store, settings, rack_id, history)


@router.get("/servers/{server_id}", response_model=ServerDetail, responses={404: {"model": ErrorResponse}})
def get_server(server_id: str, store: StoreDep, settings: SettingsDep, history: History = 60) -> ServerDetail:
    """One GPU server: per-GPU temperature and clock, power supplies, inlet air and its job's cost right now."""
    return fleet_view.server_detail(store, settings, server_id, history)


@router.get("/live", response_model=LiveStatus)
def get_live(store: StoreDep, settings: SettingsDep) -> LiveStatus:
    return live.status(store, settings)


@router.post("/live/start", response_model=LiveStatus, responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def start_live(store: StoreDep, settings: SettingsDep,
               req: Annotated[LiveStartRequest | None, Body()] = None) -> LiveStatus:
    """Start live readings for every machine. Calling it while running returns the current run."""
    return live.start(store, req or LiveStartRequest(), settings)


@router.get("/chaos", response_model=ChaosStatus)
def get_chaos(store: StoreDep, settings: SettingsDep) -> ChaosStatus:
    return chaos.status(store, settings)


@router.post("/chaos", response_model=ChaosStatus)
def set_chaos(req: ChaosRequest, store: StoreDep, settings: SettingsDep) -> ChaosStatus:
    """Demo chaos mode: random GPU server faults and priority changes (starts the live fleet if needed).
    Protected technicians (configs/operations.json chaos) never get chaos work or queue changes."""
    return chaos.set_enabled(store, settings, req.enabled)


@router.post("/live/stop", response_model=LiveStatus)
def stop_live(store: StoreDep, settings: SettingsDep) -> LiveStatus:
    """Stop the readings (charts freeze) and cancel active faults. Data and incidents stay."""
    return live.stop(store, settings)


@router.post("/faults", response_model=FaultResponse, status_code=201,
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def inject_faults(store: StoreDep, settings: SettingsDep,
                  req: Annotated[FaultRequest | None, Body()] = None) -> FaultResponse:
    """Make some machines start failing. Starts the live loop if needed. Detectors open the incidents."""
    return live.inject(store, req or FaultRequest(), settings)


@router.post("/clear", response_model=ClearResponse)
def clear(store: StoreDep, settings: SettingsDep) -> ClearResponse:
    """Delete all readings, predictions and incidents and cancel faults, for a fresh demo. Live keeps running."""
    return live.clear(store, settings)
