import { useCallback, useEffect, useMemo, useState, type JSX, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { apiBaseUrl, isDemoMode } from '../../api/index.ts';
import { UNAUTHORIZED_EVENT } from '../../api/client.ts';
import { authApi, type User } from '../../api/platform.ts';
import { LoadingState } from '../../components/common/States.tsx';
import { AuthContext, type AuthStatus } from './authContext.ts';
import { useAuth } from './useAuth.ts';

const FIXTURE_USER: User = {
  id: 'fixture-operator',
  email: 'operator@example.test',
  full_name: 'Operator',
  role: 'admin',
  organization: 'Fixture workspace',
  care_setting: 'home',
  job_role: 'caregiver',
  created_at: '2026-01-01T00:00:00Z',
};

/** Session owner: resolves `/auth/me` once, and signs out on any 401 response. */
export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const demo = isDemoMode();
  const [user, setUserState] = useState<User | null>(demo ? FIXTURE_USER : null);
  const [status, setStatus] = useState<AuthStatus>(demo ? 'signed-in' : 'loading');

  const refresh = useCallback(async (): Promise<void> => {
    if (demo) return;
    try {
      setUserState(await authApi.me());
      setStatus('signed-in');
    } catch {
      setUserState(null);
      setStatus('signed-out');
    }
  }, [demo]);

  useEffect(() => {
    if (demo) return undefined;
    let cancelled = false;
    authApi.me()
      .then((me) => { if (!cancelled) { setUserState(me); setStatus('signed-in'); } })
      .catch(() => { if (!cancelled) { setUserState(null); setStatus('signed-out'); } });
    return () => { cancelled = true; };
  }, [demo]);

  useEffect(() => {
    if (demo) return undefined;
    // A 401 from any request may be stray (e.g. a redirect that lost the cookie);
    // sign out only when the session itself is confirmed gone.
    const onUnauthorized = (): void => {
      fetch(`${apiBaseUrl()}/auth/me`, { credentials: 'same-origin' })
        .then((response) => {
          if (response.status === 401) {
            setUserState(null);
            setStatus('signed-out');
          }
        })
        .catch(() => undefined);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [demo]);

  const signIn = useCallback(async (email: string, password: string, remember: boolean): Promise<User> => {
    const signedIn = await authApi.login(email, password, remember);
    setUserState(signedIn);
    setStatus('signed-in');
    return signedIn;
  }, []);

  const signOut = useCallback(async (): Promise<void> => {
    if (!demo) {
      try { await authApi.logout(); } catch { /* the cookie is cleared server-side when reachable */ }
    }
    setUserState(null);
    setStatus('signed-out');
  }, [demo]);

  const setUser = useCallback((next: User): void => {
    setUserState(next);
    setStatus('signed-in');
  }, []);

  const value = useMemo(() => ({ status, user, signIn, signOut, setUser, refresh }), [status, user, signIn, signOut, setUser, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Route guard for the dashboard: sends signed-out visitors to /signin. */
export function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <main className="auth-gate"><LoadingState label="Checking your session…" /></main>;
  if (status === 'signed-out') {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/signin?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}
