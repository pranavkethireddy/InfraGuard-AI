import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { createFixtureClient } from '@/api/client';
import { facilityFixtures as f } from '@/api/facility-fixtures';
import { EquipmentDirectory, EquipmentDetails } from '@/components/FacilityEquipment';
import { EquipmentFaultControl } from '@/components/EquipmentFaultControl';
import { FleetRackPane, fieldUnit } from '@/components/FleetWorkspace';
import { SiteFloor } from '@/components/SiteFloor';
import { EquipmentPage } from '@/pages/EquipmentPage';
import { facilityFaults, equipmentPath } from '@/api/facility-spec';
import { pagerFixtures } from '@/api/pager-fixtures';

it('serves exact approved facility fixtures and preserves unsupported-ID errors', async () => {
  const api = createFixtureClient();
  expect(await api.fleetMap('datacenter')).toEqual(f.map);
  expect(await api.fleetStatus('datacenter')).toEqual(f.status);
  expect(await api.opsFloor('datacenter')).toEqual(f.floor);
  expect(await api.fleetRack('A1-01')).toEqual(f.rack);
  await expect(api.fleetRack('unknown')).rejects.toMatchObject({ status: 404 });
  await expect(api.getAsset('ups-01')).rejects.toMatchObject({ status: 404 });
  await expect(api.injectFaults({ asset_ids: ['ups-01'], kind: 'ups_on_battery' })).rejects.toMatchObject({ code: 'fixture_mode' });
});
it('makes every one of the 170 returned IDs accessible exactly once and filters all facility categories', () => {
  const select = vi.fn(); render(<EquipmentDirectory halls={f.map.halls} selected={null} onSelect={select} />);
  const inventory = screen.getByRole('list', { name: 'Facility equipment inventory' });
  const buttons = within(inventory).getAllByRole('button');
  expect(buttons).toHaveLength(170);
  expect(buttons.map((b) => b.textContent)).toEqual(f.map.halls.flatMap((h) => h.machines).map((m) => `${m.asset_id} · ${m.status}${m.name} · ${m.asset_type.replaceAll('_', ' ')}`));
  for (const type of Object.keys(facilityFaults)) {
    fireEvent.change(screen.getByLabelText('Equipment category'), { target: { value: type } });
    expect(within(inventory).getAllByRole('button')).toHaveLength(f.status.machines.filter((m) => m.asset_type === type).length);
  }
  fireEvent.change(screen.getByLabelText('Equipment category'), { target: { value: 'all' } });
  fireEvent.change(screen.getByLabelText('Equipment room'), { target: { value: 'electrical' } });
  expect(within(inventory).getAllByRole('button')).toHaveLength(5);
  fireEvent.click(within(inventory).getByRole('button', { name: /ups-01/ })); expect(select).toHaveBeenCalledWith('ups-01');
  fireEvent.change(screen.getByLabelText('Find equipment'), { target: { value: 'no-such-unit' } });
  expect(screen.getByText('No equipment matches the selected filters.')).toBeInTheDocument();
});
it('translates all six rooms once, retains global technician paths and independent selection', () => {
  const technician = { ...pagerFixtures.paged.technician, position: { x: 52, y: 2, hall_id: 'electrical' }, path: [{ x: 52, y: 13, hall_id: null }, { x: 52, y: 2, hall_id: 'electrical' }] };
  const select = vi.fn(); const equip = vi.fn();
  render(<SiteFloor floor={f.floor} halls={f.map.halls} technicians={[technician]} selected={null} onSelect={select} onEquipmentSelect={equip} />);
  for (const h of f.floor.halls) expect(document.querySelector(`[data-hall="${h.hall_id}"]`)).toHaveAttribute('transform', `translate(${h.x} ${h.y})`);
  expect(document.querySelector('[data-equipment="ups-01"]')).toHaveAttribute('cx', '2');
  expect(document.querySelector('[data-technician="tech-03"]')).toHaveAttribute('cx', '52');
  expect(document.querySelector('[data-technician-path="tech-03"]')).toHaveAttribute('points', '52,13 52,2');
  fireEvent.click(screen.getByRole('button', { name: /^Sam Rivera:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^UPS A:/ }));
  expect(equip).toHaveBeenCalledWith('ups-01'); expect(select).not.toHaveBeenCalled();
  expect(screen.getByRole('region', { name: 'Selected technician' })).toBeInTheDocument();
});
it('shows nullable rack PDU and ToR independently, without folding them into rack machine_ids', () => {
  render(<FleetRackPane rack={f.rack} />);
  expect(screen.getByRole('region', { name: 'Equipment details · pdu-A1-01' })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Equipment details · tor-A1-01' })).toBeInTheDocument();
  expect(f.rack.machine_ids).not.toContain('pdu-A1-01');
  expect(screen.getAllByRole('link', { name: 'pdu-A1-01' })[0]).toHaveAttribute('href', '/fleet/equipment/pdu-A1-01?site=datacenter');
});
it('keeps missing PDU/ToR data honest without deriving a device from the ID', () => {
  const { tor_id, ...legacyRack } = f.rack; void tor_id;
  render(<FleetRackPane rack={{ ...legacyRack, pdu: null, tor: null, pdu_id: null, machines: [], cooling_units: [] }} />);
  expect(screen.getAllByText('Not reported')).toHaveLength(2);
  expect(screen.queryByRole('region', { name: /Equipment details/ })).not.toBeInTheDocument();
});
it('shows zero, null, unknown units and history gaps without conversion or interpolation', () => {
  const m = f.status.machines.find((m) => m.asset_id === 'cdu-a'); if (!m) throw new Error('Missing CDU');
  render(<EquipmentDetails machine={{ ...m, latest_values: { flow_lps: 0, pressure_kpa: null, mystery: 7 }, chart_fields: ['flow_lps', 'pressure_kpa'], history: [{ observed_at: '2026-11-08T00:00:00Z', values: { flow_lps: 0 } }, { observed_at: '2026-11-08T00:00:02Z', values: { flow_lps: null, pressure_kpa: 250 } }] }} />);
  fireEvent.click(screen.getByText('Reading history'));
  expect(screen.getAllByText('L/s').length).toBeGreaterThan(0); expect(screen.getAllByText('kPa').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Not reported').length).toBeGreaterThan(1); expect(screen.getByText('Not provided')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Equipment reading history' })).toHaveTextContent('0');
  expect(equipmentPath('pdu /?#')).toBe('/fleet/equipment/pdu%20%2F%3F%23?site=datacenter');
});
it.each([['output_kw', 'kW'], ['input_voltage_v', 'V'], ['flow_lps', 'L/s'], ['pressure_kpa', 'kPa'], ['humidity_pct', '%'], ['on_battery', 'binary 0/1'], ['links_down', 'count'], ['port_errors_per_min', 'count/min'], ['optic_rx_dbm', 'dBm'], ['obscuration_pct_per_m', '%/m'], ['transfer_time_ms', 'ms'], ['unknown_hz', 'Not provided']])('uses reference-native unit for %s', (field, unit) => { expect(fieldUnit(field)).toBe(unit); });
it('blocks facility controls in fixture mode and never invents inventory', () => {
  const qc = new QueryClient(); render(<QueryClientProvider client={qc}><EquipmentFaultControl machines={f.status.machines} /></QueryClientProvider>);
  fireEvent.click(screen.getByText('Facility fault controls', { selector: 'summary' }));
  expect(screen.getByLabelText('Facility equipment')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Inject equipment fault' })).toBeDisabled();
});
it('renders an honest unknown-equipment page', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } }); render(<QueryClientProvider client={qc}><EquipmentPage id="unknown" site="datacenter" /></QueryClientProvider>);
  expect(await screen.findByText('Equipment unknown was not found in returned inventory.')).toBeInTheDocument();
});