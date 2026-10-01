import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EventFeed } from './EventFeed.tsx';
import { MOCK_WS_EVENTS } from '../../api/mockData.ts';

afterEach(() => {
  cleanup();
});

describe('EventFeed (P6-006)', () => {
  it('renders live events newest-first with connection state', () => {
    render(<EventFeed connection="connected" events={MOCK_WS_EVENTS} onReconnect={vi.fn()} />);
    expect(screen.getByText(/Event stream: connected/)).toBeDefined();
    expect(screen.getByRole('list', { name: /live events/i })).toBeDefined();
    expect(screen.getByText('fall.confirmed')).toBeDefined();
  });

  it('shows disconnected state with retry that calls reconnect', () => {
    const onReconnect = vi.fn();
    render(<EventFeed connection="disconnected" events={MOCK_WS_EVENTS} onReconnect={onReconnect} />);
    expect(screen.getByRole('alert')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onReconnect).toHaveBeenCalledTimes(1);
  });

  it('labels unknown event types instead of dropping them', () => {
    render(
      <EventFeed
        connection="connected"
        events={[
          {
            event_id: 'ev-x',
            event_type: 'mystery.type',
            occurred_at: '2026-09-23T09:30:00Z',
            camera_id: null,
            incident_id: null,
            payload: {},
          },
        ]}
        onReconnect={vi.fn()}
      />,
    );
    expect(screen.getByText('unknown type')).toBeDefined();
  });

  it('shows empty state when the stream is quiet', () => {
    render(<EventFeed connection="connected" events={[]} onReconnect={vi.fn()} />);
    expect(screen.getByText(/No events yet/)).toBeDefined();
  });
});
