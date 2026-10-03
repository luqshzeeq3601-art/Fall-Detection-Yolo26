import { useCallback, useEffect, useState } from 'react';
import { settingsApi, type SettingsResponse, type WorkspaceSettings } from '../../api/platform.ts';

const SETTINGS_UPDATED_EVENT = 'eldercare:settings-updated';

/** Server-persisted workspace settings, refreshed whenever another view saves them. */
export function useWorkspaceSettings(): {
  data: SettingsResponse | null;
  error: string | null;
  loading: boolean;
  save: (value: WorkspaceSettings) => Promise<WorkspaceSettings>;
  reload: () => void;
} {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback((): void => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    settingsApi
      .get()
      .then((value) => { if (!cancelled) { setData(value); setError(null); } })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Settings unavailable.'); });
    return () => { cancelled = true; };
  }, [tick]);

  useEffect(() => {
    window.addEventListener(SETTINGS_UPDATED_EVENT, reload);
    return () => window.removeEventListener(SETTINGS_UPDATED_EVENT, reload);
  }, [reload]);

  const save = useCallback(async (value: WorkspaceSettings): Promise<WorkspaceSettings> => {
    const saved = await settingsApi.put(value);
    window.dispatchEvent(new Event(SETTINGS_UPDATED_EVENT));
    return saved;
  }, []);

  return { data, error, loading: data === null && error === null, save, reload };
}
