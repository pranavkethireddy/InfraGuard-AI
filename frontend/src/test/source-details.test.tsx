import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { FleetMetrics } from '@/components/FleetWorkspace';
import { fleetFixtures } from '@/api/fleet-fixtures';
import { ModeBanner } from '@/components/AppShell';

it('keeps returned fleet assumptions and metric provenance collapsed but inspectable', () => {
  const { summary, site_metrics } = fleetFixtures.status;
  render(<FleetMetrics summary={summary} metrics={site_metrics} />);
  const source = screen.getByText(`assumptions_source: ${summary.assumptions_source}`);
  expect(source).not.toBeVisible();
  const details = source.closest('details');
  if (!details) throw new Error('Missing fleet assumptions');
  fireEvent.click(within(details).getByText('Source details', { selector: 'summary' }));
  expect(source).toBeVisible();
  expect(screen.getByText(/not measured costs or actual billing/)).toBeVisible();
  for (const metric of site_metrics) {
    const value = screen.getByText(metric.label).closest('div');
    if (!value) throw new Error('Missing metric');
    const provenance = within(value).getByText(`Source: ${metric.source}`);
    expect(provenance).not.toBeVisible();
    fireEvent.click(within(value).getByText('Source details', { selector: 'summary' }));
    expect(provenance).toBeVisible();
  }
  expect(screen.queryByText(/Estimate ·/)).toBeNull();
});

it('retains the unmistakable offline fixture notice', () => {
  render(<ModeBanner />);
  expect(screen.getByText('Fixture preview — illustrative data, not live.')).toBeVisible();
  expect(screen.getByText(/Actions that change data are disabled/)).toBeVisible();
});