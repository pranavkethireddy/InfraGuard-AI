// Approved public contract fixtures, imported verbatim from contracts/fixtures.
// The `Widen<T>` assignments below are compile-time compatibility checks: JSON imports
// widen string literals, so each contract type is widened the same way before comparing.
// Enum values are additionally checked at runtime in fixtures.test.ts.
import type {
  Asset, AssetDetail, DetectorModel, IncidentDetail, IncidentSummary, Paginated, ReadingsPage, Simulation, SimulationReset,
} from "../types";
import assetsList from "./contracts/assets.list.response.json";
import assetDetail from "./contracts/asset.detail.response.json";
import assetReadings from "./contracts/asset.readings.response.json";
import incidentsList from "./contracts/incidents.list.response.json";
import incidentDetail from "./contracts/incident.detail.response.json";
import modelsList from "./contracts/models.list.response.json";
import simulationStatus from "./contracts/simulation.status.response.json";
import simulationReset from "./contracts/simulation.reset.response.json";

export type Widen<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends null | undefined
        ? T
        : T extends (infer U)[]
          ? Widen<U>[]
          : T extends object
            ? { [K in keyof T]: Widen<T[K]> }
            : T;

const _assetsList: Widen<Paginated<Asset>> = assetsList;
const _assetDetail: Widen<AssetDetail> = assetDetail;
const _assetReadings: Widen<ReadingsPage> = assetReadings;
const _incidentsList: Widen<Paginated<IncidentSummary>> = incidentsList;
const _incidentDetail: Widen<IncidentDetail> = incidentDetail;
const _modelsList: Widen<Paginated<DetectorModel>> = modelsList;
const _simulationStatus: Widen<Simulation> = simulationStatus;
const _simulationReset: Widen<SimulationReset> = simulationReset;
void [_assetsList, _assetDetail, _assetReadings, _incidentsList, _incidentDetail, _modelsList, _simulationStatus, _simulationReset];

// Literal enum values are validated by fixtures.test.ts, so these casts are safe.
export const fixtures = {
  assetsList: assetsList as unknown as Paginated<Asset>,
  assetDetail: assetDetail as unknown as AssetDetail,
  assetReadings: assetReadings as unknown as ReadingsPage,
  incidentsList: incidentsList as unknown as Paginated<IncidentSummary>,
  incidentDetail: incidentDetail as unknown as IncidentDetail,
  modelsList: modelsList as unknown as Paginated<DetectorModel>,
  simulationStatus: simulationStatus as unknown as Simulation,
  simulationReset: simulationReset as unknown as SimulationReset,
};
