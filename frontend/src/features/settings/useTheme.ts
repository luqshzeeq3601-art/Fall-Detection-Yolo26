import { useCallback, useEffect, useState } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';
const KEY = 'eldercare.theme';

function readPreference(): ThemePreference {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === 'dark' || value === 'system' ? value : 'light';
  } catch {
    return 'light';
  }
}

function systemDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/**
 * Per-device appearance for the signed-in app. Light is the default; the choice is kept
 * in this browser only, and the attribute is removed when the app shell unmounts so the
 * public pages always render light.
 */
export function useTheme(): { preference: ThemePreference; setPreference: (value: ThemePreference) => void } {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [prefersDark, setPrefersDark] = useState(systemDark);

  useEffect(() => {
    if (preference !== 'system' || typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent): void => setPrefersDark(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  const dark = preference === 'dark' || (preference === 'system' && prefersDark);
  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.dataset.theme = 'dark';
    else delete root.dataset.theme;
    return () => { delete root.dataset.theme; };
  }, [dark]);

  const setPreference = useCallback((value: ThemePreference): void => {
    setPreferenceState(value);
    if (value === 'system') setPrefersDark(systemDark());
    try { window.localStorage.setItem(KEY, value); } catch { /* per-visit only */ }
  }, []);

  return { preference, setPreference };
}
