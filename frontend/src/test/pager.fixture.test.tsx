import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { PagerPage } from '@/pages/PagerPage';
it('opens no fixture stream and disables all pager mutations', async () => {
  const source = vi.fn(); vi.stubGlobal('EventSource', source);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={qc}><PagerPage onTechnicianChange={vi.fn()} /></QueryClientProvider>);
  expect(await screen.findByRole('button', { name: 'Accept job' })).toBeDisabled(); expect(screen.getByRole('button', { name: 'Decline job' })).toBeDisabled(); expect(screen.getByRole('button', { name: 'Release control' })).toBeDisabled();
  expect(source).not.toHaveBeenCalled(); view.unmount(); expect(source).not.toHaveBeenCalled(); vi.unstubAllGlobals();
});