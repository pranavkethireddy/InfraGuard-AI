import incident from './fixtures/contracts/incident.detail.playbook.response.json';
import components from './fixtures/contracts/fleet.server.components.response.json';
import component from './fixtures/contracts/fleet.server.component.response.json';
import type { IncidentDetail } from './types';
import type { ComponentDetail, ServerComponent, ServerComponents } from './parts-types';
import type { JsonShape } from './ops-fixtures';
// Heterogeneous JSON arrays widen absent metric keys to optional undefined in the SPA compiler.
type ImportedComponents = Omit<JsonShape<ServerComponents>, 'components'> & { components: (JsonShape<Omit<ServerComponent, 'metrics'>> & { metrics: Record<string, number | undefined> })[] };
const checks: [JsonShape<Omit<IncidentDetail, 'priority_rank'>> & { priority_rank: number | null }, ImportedComponents, JsonShape<ComponentDetail>] = [incident, components, component];
void checks;
// Check actual entries, not widened optional keys; retain the exact imported object.
const componentData: unknown = components;
function assertComponents(value: unknown): asserts value is ServerComponents {
  if (value !== components || components.components.some((c) => !['gpu', 'cpu', 'dimm', 'fan', 'psu', 'nic', 'nvme', 'bmc'].includes(c.kind) || !['ok', 'warning', 'failed', 'offline'].includes(c.status) || Object.values(c.metrics).some((v) => typeof v !== 'number'))) throw new Error('Invalid approved components fixture');
}
assertComponents(componentData);
export const partsFixtures = { incident: incident as IncidentDetail, components: componentData, component: component as ComponentDetail };