import { useCallback, useEffect, useState } from 'react';
import { liveApi, type LiveSessionStatus, type StreamMetrics } from '../../api/platform.ts';

export interface LiveStatusState {
  sessions: Record<string, LiveSessionStatus>;
  metrics: StreamMetrics | null;
  error: string | null;
  refresh: () => void;
}

/** Polls `/live/status` (1 s while visible) for per-camera stream state. */
export function useLiveStatus(intervalMs = 1000): LiveStatusState {
  const [sessions, setSessions] = useState<Record<string, LiveSessionStatus>>({});
  const [metrics, setMetrics] = useState<StreamMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    const load = (): void => {
      if (document.visibilityState === 'hidden') return;
      liveApi
        .status()
        .then((value) => {
          if (cancelled) return;
          setSessions(Object.fromEntries(value.sessions.map((session) => [session.camera_id, session])));
          setMetrics(value.metrics);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (!cancelled) setError(reason instanceof Error ? reason.message : 'Live status unavailable.');
        });
    };
    load();
    const timer = window.setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [intervalMs, tick]);

  return { sessions, metrics, error, refresh };
}
