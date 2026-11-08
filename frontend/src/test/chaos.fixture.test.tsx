import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { api, createFixtureClient } from '@/api/client';
import { ChaosControl } from '@/components/ChaosControl';

it('reports no approved fixture instead of inventing ChaosStatus and rejects mutations', async () => {
  const client = createFixtureClient();
  await expect(client.fleetChaos()).rejects.toMatchObject({ status: 404, code: 'not_found', message: expect.stringContaining('no approved fixture') });
  await expect(client.setFleetChaos({ enabled: false })).rejects.toMatchObject({ code: 'fixture_mode' });
});
it('does not fetch or mutate chaos in fixture preview', () => {
  const get = vi.spyOn(api, 'fleetChaos'); const post = vi.spyOn(api, 'setFleetChaos');
  render(<QueryClientProvider client={new QueryClient()}><ChaosControl /></QueryClientProvider>);
  fireEvent.click(screen.getByText('Operator controls'));
  expect(screen.getByText(/no approved chaos fixture/)).toBeVisible(); expect(screen.getByRole('switch')).toBeDisabled();
  fireEvent.click(screen.getByRole('switch')); expect(get).not.toHaveBeenCalled(); expect(post).not.toHaveBeenCalled();
  get.mockRestore(); post.mockRestore();
});