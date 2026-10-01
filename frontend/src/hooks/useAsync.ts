import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

function toMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Request failed';
}

/**
 * Generic loading/error/data boundary. No global mutable state;
 * each hook instance owns its lifecycle with unmount cleanup.
 * Loading starts true; reload() re-arms loading before refetch.
 */
export function useAsync<T>(loader: () => Promise<T>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loaderRef
      .current()
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
  }, [nonce]);

  const reload = useCallback(() => {
    setError(null);
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);

  return { data, loading, error, reload };
}
