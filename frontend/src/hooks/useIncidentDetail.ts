import { useEffect, useRef, useState } from 'react';
import { getApiClient } from '../api/index.ts';
import type { IncidentDetail } from '../api/types.ts';

function toMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Request failed';
}

/**
 * Detail fetch over GET /incidents/{id}. The parent mounts this hook
 * per incident (key={incidentId}) so id changes remount with fresh
 * loading state; the effect only resolves results.
 */
export function useIncidentDetail(incidentId: string): {
  data: IncidentDetail | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const [data, setData] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    // No selection: never request `/incidents/` (an empty ID is not a resource).
    if (!incidentId) return undefined;
    let cancelled = false;
    getApiClient()
      .getIncident(incidentId)
      .then((value) => {
        if (!cancelled && mounted.current) {
          setData(value);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled && mounted.current) {
          setError(toMessage(err));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId, nonce]);

  return {
    data,
    loading,
    error,
    reload: (): void => {
      setError(null);
      setLoading(true);
      setNonce((n) => n + 1);
    },
  };
}
