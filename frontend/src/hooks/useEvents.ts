import { useEffect, useRef, useState } from 'react';
import { MOCK_WS_EVENTS } from '../api/mockData.ts';
import type { WsEvent } from '../api/types.ts';

export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

const KNOWN_EVENT_TYPES: readonly string[] = [
  'camera.online',
  'camera.degraded',
  'camera.offline',
  'camera.reconnected',
  'fall.candidate',
  'fall.confirmed',
  'fall.recovered',
  'incident.persisted',
  'incident.reviewed',
  'agent.enrichment_queued',
  'agent.enrichment_completed',
  'agent.enrichment_failed',
  'service.degraded',
  'service.recovered',
];

/** Minimal socket surface so tests can inject a deterministic mock. */
export interface EventSocket {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  close(): void;
}

export type SocketFactory = (url: string) => EventSocket;

export function eventsUrl(): string {
  const useMock = (import.meta.env.VITE_USE_MOCK as string | undefined) !== 'false';
  if (useMock) return 'mock://ws/events';
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
  const httpUrl = base || window.location.origin;
  return httpUrl.replace(/^http/, 'ws') + '/ws/events';
}

function parseEvent(raw: string): WsEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const record = parsed as Record<string, unknown>;
  if (
    typeof record.event_id !== 'string' ||
    typeof record.event_type !== 'string' ||
    typeof record.occurred_at !== 'string'
  ) {
    return null;
  }
  if (Number.isNaN(new Date(record.occurred_at).getTime())) return null;
  return {
    event_id: record.event_id,
    event_type: record.event_type,
    occurred_at: record.occurred_at,
    camera_id: typeof record.camera_id === 'string' ? record.camera_id : null,
    incident_id: typeof record.incident_id === 'string' ? record.incident_id : null,
    payload:
      typeof record.payload === 'object' && record.payload !== null
        ? (record.payload as Record<string, unknown>)
        : {},
  };
}

const BACKOFF_MS = [500, 1000, 2000];
const MAX_ATTEMPTS = 4;

export interface EventsBundle {
  connection: ConnectionState;
  connected: boolean;
  events: WsEvent[];
  latestByCamera: Record<string, WsEvent>;
  reconnect: () => void;
}

function defaultSocketFactory(url: string): EventSocket {
  if (url.startsWith('mock://')) return new MockEventSocket();
  return new WebSocket(url) as unknown as EventSocket;
}

/**
 * Single event-stream subscription. Dedupe by event_id; per-camera
 * latest advances only on newer occurred_at; bounded auto-reconnect
 * with manual retry; full cleanup on unmount.
 */
export function useEvents(factory: SocketFactory = defaultSocketFactory): EventsBundle {
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [latestByCamera, setLatestByCamera] = useState<Record<string, WsEvent>>({});
  const [generation, setGeneration] = useState(0);
  const seenRef = useRef<Set<string> | null>(null);
  if (seenRef.current === null) seenRef.current = new Set<string>();
  const factoryRef = useRef<SocketFactory>(factory);

  useEffect(() => {
    factoryRef.current = factory;
  });

  useEffect(() => {
    const seen = seenRef.current as Set<string>;
    let disposed = false;
    let timer: number | null = null;
    let attempts = 0;
    let socket: EventSocket | null = null;

    function openSocket(): void {
      if (disposed) return;
      socket = factoryRef.current(eventsUrl());
      socket.onopen = () => {
        if (disposed) return;
        attempts = 0;
        setConnection('connected');
      };
      socket.onmessage = (message) => {
        if (disposed) return;
        const event = parseEvent(message.data);
        if (!event) return;
        if (seen.has(event.event_id)) return;
        seen.add(event.event_id);
        setEvents((prev) => [...prev.slice(-99), event]);
        if (event.camera_id) {
          const cameraId = event.camera_id;
          setLatestByCamera((prev) => {
            const current = prev[cameraId];
            if (current && current.occurred_at >= event.occurred_at) return prev;
            return { ...prev, [cameraId]: event };
          });
        }
      };
      const handleClose = (): void => {
        if (disposed) return;
        const delay = BACKOFF_MS[Math.min(attempts, BACKOFF_MS.length - 1)];
        attempts += 1;
        if (attempts > MAX_ATTEMPTS) {
          setConnection('disconnected');
          return;
        }
        setConnection('connecting');
        timer = window.setTimeout(openSocket, delay);
      };
      socket.onclose = handleClose;
      socket.onerror = handleClose;
    }

    openSocket();
    return () => {
      disposed = true;
      if (timer !== null) window.clearTimeout(timer);
      socket?.close();
    };
  }, [generation]);

  function reconnect(): void {
    setConnection('connecting');
    setGeneration((g) => g + 1);
  }

  return {
    connection,
    connected: connection === 'connected',
    events,
    latestByCamera,
    reconnect,
  };
}

export function isKnownEventType(eventType: string): boolean {
  return KNOWN_EVENT_TYPES.includes(eventType);
}

/**
 * Deterministic mock socket: replays MockApiClient fixtures on open.
 * Tests drive extra frames via `emit`, duplicates, malformed payloads,
 * stale timestamps, and close/reconnect.
 */
export class MockEventSocket implements EventSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  opened = false;
  autoReplay: boolean;

  constructor(autoReplay = true) {
    this.autoReplay = autoReplay;
    queueMicrotask(() => this.open());
  }

  open(): void {
    if (this.opened || this.closed) return;
    this.opened = true;
    this.onopen?.();
    if (this.autoReplay) {
      for (const event of MOCK_WS_EVENTS) {
        this.emit(event);
      }
    }
  }

  emit(event: WsEvent): void {
    if (this.closed) return;
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  emitRaw(raw: string): void {
    if (this.closed) return;
    this.onmessage?.({ data: raw });
  }

  serverClose(): void {
    if (this.closed) return;
    this.onclose?.();
  }

  close(): void {
    this.closed = true;
  }
}
