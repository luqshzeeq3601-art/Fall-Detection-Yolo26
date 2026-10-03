import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import type { Incident } from '../../api/types.ts';
import { MOCK_INCIDENTS } from '../../api/mockData.ts';
import { ShiftTimeline } from './ShiftTimeline.tsx';

afterEach(() => cleanup());

const now = new Date(2026, 9, 3, 18, 0);
const at = (hour: number): string => new Date(2026, 9, 3, hour, 0).toISOString();
const base = MOCK_INCIDENTS[0];

describe('ShiftTimeline', () => {
  it("places today's alerts on the track with their review state", () => {
    const incidents: Incident[] = [
      { ...base, id: 'a', confirmed_at: at(9), review_label: null },
      { ...base, id: 'b', confirmed_at: at(14), review_label: 'confirmed_fall' },
      { ...base, id: 'c', confirmed_at: new Date(2026, 9, 2, 23, 0).toISOString(), review_label: null },
    ];
    render(<MemoryRouter><ShiftTimeline incidents={incidents} cameraName={() => 'Hallway'} now={now} /></MemoryRouter>);
    const markers = screen.getAllByRole('link');
    expect(markers).toHaveLength(2);
    expect(markers[0].getAttribute('aria-label')).toMatch(/Hallway, .*Not reviewed/);
    expect(markers[1].getAttribute('aria-label')).toMatch(/Real fall/);
    expect(markers[1].getAttribute('href')).toBe('/app/incidents?selected=b');
  });

  it('says so when there are no alerts today', () => {
    render(<MemoryRouter><ShiftTimeline incidents={[]} cameraName={(id) => id} now={now} /></MemoryRouter>);
    expect(screen.getByText('No alerts yet today.')).toBeDefined();
  });
});
