import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { MOCK_CAMERAS, MOCK_INCIDENTS } from '../api/mockData.ts';
import { CameraPreviews, TodayActivity } from './OverviewWorkspace.tsx';

afterEach(cleanup);

describe('Overview workspace', () => {
  it('keeps online camera metadata separate from an actual running feed', () => {
    render(<MemoryRouter><CameraPreviews cameras={MOCK_CAMERAS} sessions={[]} /></MemoryRouter>);
    expect(screen.getAllByText('No live feed')).toHaveLength(MOCK_CAMERAS.length);
    expect(screen.queryByText('LIVE')).toBeNull();
    expect(screen.getByText('Online')).toBeDefined();
    expect(screen.getByText('Offline')).toBeDefined();
  });

  it('counts only the selected local day and groups alerts by their actual hour', () => {
    const now = new Date(2026, 9, 4, 12);
    const at = (day: number, hour: number) => new Date(2026, 9, day, hour).toISOString();
    const items = [
      { ...MOCK_INCIDENTS[0], id: 'one', confirmed_at: at(4, 9) },
      { ...MOCK_INCIDENTS[0], id: 'two', confirmed_at: at(4, 9) },
      { ...MOCK_INCIDENTS[0], id: 'yesterday', confirmed_at: at(3, 23) },
      { ...MOCK_INCIDENTS[0], id: 'tomorrow', confirmed_at: at(5, 0) },
    ];
    render(<TodayActivity incidents={items} now={now} />);
    expect(screen.getByRole('img', { name: "Today's alerts by local hour: 2 alerts" })).toBeDefined();
    expect(screen.getByText('09:00: 2 alerts')).toBeDefined();
    expect(screen.queryByText('No alerts yet today.')).toBeNull();
    expect(screen.getByText('24:00')).toBeDefined();
  });

  it('shows an honest empty chart with a readable next step', () => {
    render(<TodayActivity incidents={[]} now={new Date(2026, 9, 4, 12)} />);
    expect(screen.getByRole('img', { name: "Today's alerts by local hour: 0 alerts" })).toBeDefined();
    expect(screen.getByText('No alerts yet today.')).toBeDefined();
  });
});
