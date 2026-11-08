import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { FleetPage } from '@/pages/FleetPage';
import { ServerPage } from '@/pages/ServerPage';
import { gpuFixtures } from '@/api/gpu-fixtures';
it('disables every fleet mutation in fixture mode, including snapshot running state', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><FleetPage site="datacenter" onSiteChange={() => {}} /></QueryClientProvider>);
  await waitFor(() => expect(screen.getByText(/Loop: running/)).toBeInTheDocument());
  for (const name of ['Start live loop', 'Stop live loop', 'Inject 3 faults', 'Clear fleet']) expect(screen.getByRole('button', { name })).toBeDisabled();
});
it('disables targeted server fault mutations in fixture preview', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><ServerPage id={gpuFixtures.server.machine.asset_id} gpuIndex={1} onGpuChange={() => {}} /></QueryClientProvider>);
  expect(await screen.findByRole('button', { name: 'Inject server fault' })).toBeDisabled();
});