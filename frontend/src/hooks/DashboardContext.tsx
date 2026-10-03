import type { ReactNode } from 'react';
import { useEffect, useMemo, useRef } from 'react';
import { getApiClient } from '../api/index.ts';
import { useAsync } from './useAsync.ts';
import { DashboardContext } from './dashboardContext.ts';
import { useEvents, type ConnectionState } from './useEvents.ts';

const CAMERA_REFRESH_EVENTS = new Set(['camera.online', 'camera.degraded', 'camera.offline', 'camera.reconnected']);

interface DashboardProviderProps {
  children: ReactNode;
}

/** One shared source of camera health, readiness, system status and live events. */
export function DashboardProvider({ children }: DashboardProviderProps) {
  const cameras = useAsync(() => getApiClient().listCameras());
  const system = useAsync(() => getApiClient().getSystemStatus());
  const ready = useAsync(() => getApiClient().getReady());
  const events = useEvents();
  const reloadCameras = cameras.reload;
  const seenCameraEventIds = useRef<Set<string> | null>(null);
  const previousConnection = useRef<ConnectionState | null>(null);
  const hasConnectedOnce = useRef(false);

  useEffect(() => {
    const relevantEvents = events.events.filter((event) => CAMERA_REFRESH_EVENTS.has(event.event_type));
    if (seenCameraEventIds.current === null) {
      seenCameraEventIds.current = new Set(relevantEvents.map((event) => event.event_id));
      return;
    }
    const seen = seenCameraEventIds.current;
    const freshEvents = relevantEvents.filter((event) => !seen.has(event.event_id));
    if (freshEvents.length === 0) return;
    for (const event of freshEvents) seen.add(event.event_id);
    reloadCameras();
  }, [events.events, reloadCameras]);

  useEffect(() => {
    const previous = previousConnection.current;
    previousConnection.current = events.connection;
    if (previous === null) {
      if (events.connection === 'connected') hasConnectedOnce.current = true;
      return;
    }
    if (events.connection === 'connected' && previous !== 'connected') {
      if (hasConnectedOnce.current) reloadCameras();
      hasConnectedOnce.current = true;
    }
  }, [events.connection, reloadCameras]);

  const value = useMemo(() => ({ cameras, system, ready, events }), [cameras, system, ready, events]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}
