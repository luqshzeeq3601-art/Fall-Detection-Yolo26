import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiClient } from '../api/index.ts';
import type { IncidentFilterParams, PaginatedIncidents } from '../api/types.ts';

export interface IncidentQuery extends IncidentFilterParams {
  limit: number;
  offset: number;
}

function toMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Request failed';
}

/**
 * Incident search over GET /incidents. Filter updates happen in event
 * handlers (which re-arm loading); the effect only resolves results.
 */
export function useIncidents(initial: IncidentQuery): {
  data: PaginatedIncidents | null;
  loading: boolean;
  error: string | null;
  query: IncidentQuery;
  setQuery: (next: IncidentQuery) => void;
  reload: () => void;
} {
  const [params, setParams] = useState<IncidentQuery>(initial);
  const [data, setData] = useState<PaginatedIncidents | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getApiClient()
      .listIncidents(params)
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
  }, [params]);

  const setQuery = useCallback((next: IncidentQuery) => {
    setError(null);
    setLoading(true);
    setParams(next);
  }, []);

  const reload = useCallback(() => {
    setError(null);
    setLoading(true);
    setParams((prev) => ({ ...prev }));
  }, []);

  return { data, loading, error, query: params, setQuery, reload };
}
