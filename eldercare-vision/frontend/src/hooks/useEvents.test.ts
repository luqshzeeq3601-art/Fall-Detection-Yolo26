import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  MockEventSocket,
  useEvents,
  type SocketFactory,
} from './useEvents.ts';
import { MOCK_WS_EVENTS } from '../api/mockData.ts';
import type { WsEvent } from '../api/types.ts';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function makeFactory(instances: MockEventSocket[], autoReplay = true): SocketFactory {
  return () => {
    const socket = new MockEventSocket(autoReplay);
    instances.push(socket);
    return socket;
  };
}

function laterEvent(): WsEvent {
  return {
    event_id: 'ev-later',
    event_type: 'fall.confirmed',
    occurred_at: '2026-09-23T09:00:00Z',
    camera_id: 'cam-01',
    incident_id: null,
    payload: {},
  };
}

describe('useEvents (P6-006)', () => {
  it('connects and replays the deterministic fixture stream', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    expect(result.current.events).toHaveLength(MOCK_WS_EVENTS.length);
    expect(result.current.latestByCamera['cam-01'].event_id).toBe('ev-0001');
  });

  it('ignores duplicate event_ids', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    const event = laterEvent();
    act(() => {
      instances[0].emit(event);
      instances[0].emit(event);
    });
    expect(result.current.events).toHaveLength(1);
  });

  it('drops malformed frames but keeps valid ones', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    act(() => {
      instances[0].emitRaw('not-json');
      instances[0].emitRaw('{"event_id":"x"}');
      instances[0].emitRaw(
        '{"event_id":"bad-date","event_type":"fall.confirmed","occurred_at":"yesterday"}',
      );
      instances[0].emit(laterEvent());
    });
    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].event_id).toBe('ev-later');
  });

  it('never lets stale timestamps overwrite newer per-camera state', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    const newer: WsEvent = { ...laterEvent(), event_id: 'ev-new', occurred_at: '2026-09-23T09:00:00Z' };
    const older: WsEvent = { ...laterEvent(), event_id: 'ev-old', occurred_at: '2026-09-23T08:00:00Z' };
    act(() => {
      instances[0].emit(newer);
    });
    act(() => {
      instances[0].emit(older);
    });
    expect(result.current.events).toHaveLength(2);
    expect(result.current.latestByCamera['cam-01'].event_id).toBe('ev-new');
  });

  it('tolerates unknown additive fields and types', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    act(() => {
      instances[0].emitRaw(
        JSON.stringify({
          event_id: 'ev-future',
          event_type: 'something brand new',
          occurred_at: '2026-09-23T09:30:00Z',
          camera_id: 'cam-09',
          incident_id: null,
          payload: {},
          brand_new_field: 'ignored by shape already',
        }),
      );
    });
    expect(result.current.events).toHaveLength(1);
  });

  it('reports reconnecting on server close and supports manual retry', async () => {
    const instances: MockEventSocket[] = [];
    const { result } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    act(() => {
      instances[0].serverClose();
    });
    await waitFor(() => expect(result.current.connection).toBe('connecting'));
    act(() => {
      result.current.reconnect();
    });
    await waitFor(() => expect(instances.length).toBe(2));
  });

  it('closes the socket on unmount', async () => {
    const instances: MockEventSocket[] = [];
    const { result, unmount } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    unmount();
    expect(instances[0].closed).toBe(true);
  });
});
