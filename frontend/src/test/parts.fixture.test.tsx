import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { createFixtureClient } from '@/api/client';
import { partsFixtures as f } from '@/api/parts-fixtures';
import { serverComponentsQuery, serverComponentQuery } from '@/api/parts-queries';
import { ServerParts } from '@/components/ServerParts';
import { ServerFaultControl } from '@/components/ServerFaultControl';
import { gpuFixtures } from '@/api/gpu-fixtures';
import { FailureModePanel } from '@/components/FailureModePanel';
const mount = (c: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{c}</QueryClientProvider>);
it('serves only exact approved component and incident playbook fixtures', async () => {
  const api = createFixtureClient();
  expect(await api.fleetServerComponents('srv-A1-01-1')).toEqual(f.components);
  expect(await api.fleetServerComponent('srv-A1-01-1', 'fan5')).toEqual(f.component);
  expect(await api.getIncident('inc-000793')).toEqual(f.incident);
  expect(f.components.components).toHaveLength(39);
});
it.each([['missing', 'fan5', 'SERVER_NOT_FOUND'], ['srv-A1-01-1', 'gpu1', 'COMPONENT_NOT_FOUND']])('rejects unsupplied fixture %s/%s with %s', async (id, cid, code) => {
  await expect(createFixtureClient().fleetServerComponent(id, cid)).rejects.toMatchObject({ status: 404, code });
});
it('does not poll parts in fixture mode and disables every explicit server fault choice', () => {
  expect(serverComponentsQuery('x').refetchInterval).toBe(false); expect(serverComponentQuery('x', 'y').refetchInterval).toBe(false);
  mount(<ServerFaultControl servers={[gpuFixtures.server.machine]} selectedServerId={gpuFixtures.server.machine.asset_id} />);
  expect(screen.getByRole('button', { name: 'Inject server fault' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Server fault choice' })).toBeDisabled();
});
it('links exactly 39 returned IDs with all returned statuses and groups', async () => {
  mount(<ServerParts id="srv-A1-01-1" />);
  const region = await screen.findByRole('region', { name: 'Server parts' });
  expect(within(region).getAllByRole('link')).toHaveLength(39);
  for (const part of f.components.components) {
    const link = region.querySelector(`a[href="/fleet/servers/srv-A1-01-1/components/${part.component_id}"]`);
    expect(link).not.toBeNull(); expect(link).toHaveTextContent(part.name); expect(link).toHaveTextContent(part.status);
  }
  expect(within(region).getAllByRole('group')).toHaveLength(8);
});
it.each([undefined, null])('reports missing old failure_mode honestly without an inferred cause', (mode) => {
  render(<FailureModePanel mode={mode} />); expect(screen.getByText('Failure mode: Not reported')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Failure mode' })).not.toBeInTheDocument();
});