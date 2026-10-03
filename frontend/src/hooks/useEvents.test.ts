import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  MockEventSocket,
  useEvents,
  type SocketFactory,
  type EventSocket,
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

function eventWithId(eventId: string): WsEvent {
  return {
    event_id: eventId,
    event_type: 'camera.online',
    occurred_at: '2026-09-23T09:00:00Z',
    camera_id: null,
    incident_id: null,
    payload: {},
  };
}

class ControlledSocket implements EventSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  open(): void {
    this.onopen?.();
  }

  fail(): void {
    this.onerror?.();
  }

  closeFromServer(): void {
    this.onclose?.();
  }

  emit(event: WsEvent): void {
    if (this.closed) return;
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  close(): void {
    this.closed = true;
  }
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

  it('coalesces error followed by close and clears the pending reconnect on unmount', () => {
    vi.useFakeTimers();
    try {
      const instances: ControlledSocket[] = [];
      const factory: SocketFactory = () => {
        const socket = new ControlledSocket();
        instances.push(socket);
        return socket;
      };
      const { result, unmount } = renderHook(() => useEvents(factory));
      expect(instances).toHaveLength(1);

      act(() => {
        instances[0].open();
        instances[0].fail();
        instances[0].closeFromServer();
      });
      expect(result.current.connection).toBe('connecting');
      expect(vi.getTimerCount()).toBe(1);

      unmount();
      act(() => {
        vi.runAllTimers();
      });
      expect(instances).toHaveLength(1);
      expect(instances[0].closed).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancels the pending retry deadline when manual reconnect replaces the socket', () => {
    vi.useFakeTimers();
    try {
      const instances: ControlledSocket[] = [];
      const factory: SocketFactory = () => {
        const socket = new ControlledSocket();
        instances.push(socket);
        return socket;
      };
      const { result, unmount } = renderHook(() => useEvents(factory));

      act(() => {
        instances[0].open();
        instances[0].closeFromServer();
      });
      expect(vi.getTimerCount()).toBe(1);

      act(() => {
        result.current.reconnect();
      });
      expect(instances).toHaveLength(2);
      expect(instances[0].closed).toBe(true);

      act(() => {
        vi.advanceTimersByTime(2500);
      });
      expect(instances).toHaveLength(2);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('detaches obsolete socket handlers before a replacement can receive late callbacks', () => {
    vi.useFakeTimers();
    try {
      const instances: ControlledSocket[] = [];
      const factory: SocketFactory = () => {
        const socket = new ControlledSocket();
        instances.push(socket);
        return socket;
      };
      const { result, unmount } = renderHook(() => useEvents(factory));
      const first = instances[0];

      act(() => {
        first.open();
        first.closeFromServer();
      });
      const staleHandlers = {
        onmessage: first.onmessage,
        onclose: first.onclose,
        onerror: first.onerror,
      };

      act(() => {
        result.current.reconnect();
      });
      expect(first.onopen).toBeNull();
      expect(first.onmessage).toBeNull();
      expect(first.onclose).toBeNull();
      expect(first.onerror).toBeNull();

      act(() => {
        staleHandlers.onmessage?.({ data: JSON.stringify(eventWithId('stale')) });
        staleHandlers.onclose?.();
        staleHandlers.onerror?.();
        vi.advanceTimersByTime(2500);
      });
      expect(instances).toHaveLength(2);
      expect(result.current.events).toHaveLength(0);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('closes the replacement socket when the hook unmounts', () => {
    const instances: ControlledSocket[] = [];
    const factory: SocketFactory = () => {
      const socket = new ControlledSocket();
      instances.push(socket);
      return socket;
    };
    const { result, unmount } = renderHook(() => useEvents(factory));

    act(() => {
      instances[0].open();
      result.current.reconnect();
    });
    expect(instances).toHaveLength(2);

    unmount();
    expect(instances[1].closed).toBe(true);
    expect(instances[1].onopen).toBeNull();
    expect(instances[1].onmessage).toBeNull();
    expect(instances[1].onclose).toBeNull();
    expect(instances[1].onerror).toBeNull();
  });

  it('evicts only old event ids from the bounded dedupe set', () => {
    const instances: ControlledSocket[] = [];
    const factory: SocketFactory = () => {
      const socket = new ControlledSocket();
      instances.push(socket);
      return socket;
    };
    const { result, unmount } = renderHook(() => useEvents(factory));

    act(() => {
      instances[0].open();
      for (let index = 0; index <= 1000; index += 1) {
        instances[0].emit(eventWithId(`ev-${index}`));
      }
    });
    expect(result.current.events.at(-1)?.event_id).toBe('ev-1000');

    act(() => {
      instances[0].emit(eventWithId('ev-0'));
      instances[0].emit(eventWithId('ev-1000'));
    });
    expect(result.current.events.filter((event) => event.event_id === 'ev-0')).toHaveLength(1);
    expect(result.current.events.filter((event) => event.event_id === 'ev-1000')).toHaveLength(1);
    unmount();
  });

  it('closes the socket on unmount', async () => {
    const instances: MockEventSocket[] = [];
    const { result, unmount } = renderHook(() => useEvents(makeFactory(instances, false)));
    await waitFor(() => expect(result.current.connected).toBe(true));
    unmount();
    expect(instances[0].closed).toBe(true);
  });
});
