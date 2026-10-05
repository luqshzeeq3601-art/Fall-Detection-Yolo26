import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Camera,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  ClipboardCheck,
  Home,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Search,
  Settings,
  Sliders,
  Sun,
  User as UserIcon,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent, type JSX, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useDashboardContext } from '../../hooks/useDashboardContext.ts';
import { ConnectionBadge } from '../common/ConnectionBadge.tsx';
import { FallAlerts } from '../events/FallAlerts.tsx';
import { roleLabel } from '../../features/auth/roles.ts';
import { useAuth } from '../../features/auth/useAuth.ts';
import { useTheme, type ThemePreference } from '../../features/settings/useTheme.ts';
import { Brand } from './Brand.tsx';
import './Shell.css';


const SEEN_KEY = 'eldercare.alerts.seen';
const SIDEBAR_COLLAPSED_KEY = 'eldercare.sidebar.collapsed';

function readSeen(): string | null {
  try { return window.localStorage.getItem(SEEN_KEY); } catch { return null; }
}

function readSidebarCollapsed(): boolean {
  try { return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'; } catch { return false; }
}

export function AppShell({ children }: { children?: ReactNode }): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const isOverview = location.pathname === '/app' || location.pathname === '/app/';
  const { events, cameras } = useDashboardContext();
  const falls = events.events.filter((event) => event.event_type === 'fall.confirmed');
  const [seenAt, setSeenAt] = useState<string | null>(readSeen);
  const unseen = falls.filter((event) => !seenAt || event.occurred_at > seenAt).length;
  const cameraName = (id: string | null | undefined): string => cameras.data?.find((camera) => camera.id === id)?.name ?? id ?? 'Unknown camera';
  const markSeen = (): void => {
    const now = new Date().toISOString();
    setSeenAt(now);
    try { window.localStorage.setItem(SEEN_KEY, now); } catch { /* per-visit only */ }
  };
  const { user, signOut } = useAuth();
  const theme = useTheme();
  const isAdmin = user?.role === 'admin';
  const navGroups = isAdmin
    ? [
        { label: 'Monitor', items: [
          { label: 'Overview', to: '/app', icon: Home },
          { label: 'Live monitor', to: '/app/surveillance', icon: Camera },
        ] },
        { label: 'Respond', items: [
          { label: 'Incidents', to: '/app/incidents', icon: AlertTriangle },
          { label: 'Review queue', to: '/app/review', icon: ClipboardCheck },
        ] },
        { label: 'System', items: [
          { label: 'System health', to: '/app/telemetry', icon: Activity },
          { label: 'Model results', to: '/app/benchmarks', icon: BarChart3 },
          { label: 'Settings', to: '/app/settings', icon: Settings },
        ] },
      ]
    : [
        { label: 'Monitor', items: [
          { label: 'Overview', to: '/app', icon: Home },
          { label: 'Live monitor', to: '/app/surveillance', icon: Camera },
        ] },
        { label: 'Respond', items: [
          { label: 'Incidents', to: '/app/incidents', icon: AlertTriangle },
          { label: 'Review queue', to: '/app/review', icon: ClipboardCheck },
        ] },
        { label: 'Account', items: [
          { label: 'Settings', to: '/app/settings?tab=account', icon: Settings },
        ] },
      ];
  const displayName = user?.full_name ?? 'Signed in';
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(readSidebarCollapsed);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [search, setSearch] = useState('');
  const sidebarCloseRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const notificationButtonRef = useRef<HTMLButtonElement>(null);
  const userMenuButtonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverRestoreFocusRef = useRef<HTMLElement | null>(null);

  const toggleSidebarCollapsed = (): void => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try { window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next)); } catch { /* ignore */ }
      return next;
    });
  };

  useEffect(() => {
    const handleHotkeys = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'b') {
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable) return;
        event.preventDefault();
        toggleSidebarCollapsed();
      }
    };
    window.addEventListener('keydown', handleHotkeys);
    return () => window.removeEventListener('keydown', handleHotkeys);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    restoreFocusRef.current = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : mobileMenuRef.current;
    sidebarCloseRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setSidebarOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const sidebar = document.getElementById('app-sidebar');
      if (!sidebar) return;
      const focusable = Array.from(sidebar.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [sidebarOpen]);
  useEffect(() => {
    const popoverOpen = notificationsOpen || userMenuOpen;
    if (!popoverOpen) {
      const restore = popoverRestoreFocusRef.current;
      popoverRestoreFocusRef.current = null;
      restore?.focus();
      return undefined;
    }
    popoverRestoreFocusRef.current = notificationsOpen
      ? notificationButtonRef.current
      : userMenuButtonRef.current;
    const popover = popoverRef.current;
    if (!popover) return undefined;
    const focusable = (): HTMLElement[] => Array.from(popover.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'));
    focusable()[0]?.focus();
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setNotificationsOpen(false);
        setUserMenuOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const handlePointerDown = (event: MouseEvent | TouchEvent): void => {
      const target = event.target as Node | null;
      if (!target) return;
      if (popover.contains(target)) return;
      if (notificationButtonRef.current?.contains(target)) return;
      if (userMenuButtonRef.current?.contains(target)) return;
      setNotificationsOpen(false);
      setUserMenuOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [notificationsOpen, userMenuOpen]);
  useEffect(() => {
    if (sidebarOpen || !restoreFocusRef.current) return;
    const restore = restoreFocusRef.current;
    restoreFocusRef.current = null;
    restore.focus();
  }, [sidebarOpen]);
  const submitSearch = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const value = search.trim();
    setNotificationsOpen(false);
    setUserMenuOpen(false);
    navigate(value ? `/app/incidents?search=${encodeURIComponent(value)}` : '/app/incidents');
  };

  return (
    <div className={`app-frame${isOverview ? ' app-frame-overview' : ''}${sidebarCollapsed ? ' is-collapsed' : ''}`}>
      <button
        className={`sidebar-scrim${sidebarOpen ? ' is-visible' : ''}`}
        type="button"
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />
      <aside id="app-sidebar" className={`app-sidebar${sidebarOpen ? ' is-open' : ''}${sidebarCollapsed ? ' is-collapsed' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand-row">
          <Link to="/app" aria-label="ElderCare Vision home" onClick={() => setSidebarOpen(false)}>
            <Brand compact={sidebarCollapsed} />
          </Link>
          <button
            ref={sidebarCloseRef}
            className="sidebar-close icon-button"
            type="button"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          >
            <X aria-hidden="true" />
          </button>
        </div>
        <nav className="sidebar-nav" aria-label="Dashboard pages">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-group-label">{group.label}</p>
              {group.items.map(({ label, to, icon: Icon }) => (
                <NavLink
                  key={label}
                  to={to}
                  end={to === '/app'}
                  aria-label={label}
                  title={sidebarCollapsed ? `${label}${to === '/app/incidents' && unseen > 0 ? ` (${unseen} new)` : ''}` : undefined}
                  className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
                  onClick={() => {
                    setSidebarOpen(false);
                    setNotificationsOpen(false);
                    setUserMenuOpen(false);
                  }}
                >
                  <Icon aria-hidden="true" />
                  <span>{label}</span>
                  {to === '/app/incidents' && unseen > 0 ? (
                    <span className="nav-badge" aria-label={`${unseen} new incidents`}>
                      {unseen}
                    </span>
                  ) : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="sidebar-collapse-btn"
            type="button"
            aria-label={sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
            title={sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
            aria-expanded={!sidebarCollapsed}
            onClick={toggleSidebarCollapsed}
          >
            {sidebarCollapsed ? (
              <ChevronsRight aria-hidden="true" />
            ) : (
              <ChevronsLeft aria-hidden="true" />
            )}
          </button>
          <p className="sidebar-poc-note">Research POC · not a medical device</p>
        </div>
      </aside>

      <div className="app-main-shell">
        <header className="app-topbar">
          <button
            ref={mobileMenuRef}
            className="mobile-menu icon-button"
            type="button"
            aria-label="Open navigation"
            aria-expanded={sidebarOpen}
            aria-controls="app-sidebar"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu aria-hidden="true" />
          </button>
          <form className="global-search" role="search" onSubmit={submitSearch}>
            <Search aria-hidden="true" />
            <label className="sr-only" htmlFor="global-search-input">Search incidents</label>
            <input
              id="global-search-input"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search incidents by camera or ID…"
            />
          </form>
          <div className="topbar-actions">
            <ConnectionBadge connected={events.connected} />
            <span className="topbar-divider" aria-hidden="true" />
            <div className="topbar-popover-wrap">
              <button
                ref={notificationButtonRef}
                className="icon-button topbar-icon-button"
                type="button"
                aria-label={unseen ? `Fall alerts, ${unseen} new` : 'Fall alerts'}
                aria-haspopup="dialog"
                aria-expanded={notificationsOpen}
                onClick={() => {
                  setNotificationsOpen((open) => !open);
                  setUserMenuOpen(false);
                }}
              >
                <Bell aria-hidden="true" />
                {unseen > 0 ? <span className="notification-count" aria-hidden="true">{unseen > 9 ? '9+' : unseen}</span> : null}
              </button>
              {notificationsOpen ? (
                <div ref={popoverRef} className="popover notification-panel" role="dialog" aria-label="Fall alerts">
                  <div className="popover-heading">
                    <div>
                      <strong>Fall alerts</strong>
                      <span>{falls.length ? `${falls.length} since you opened the dashboard` : 'Since you opened the dashboard'}</span>
                    </div>
                    {unseen > 0 ? <button className="text-button" type="button" onClick={markSeen}>Mark as seen</button> : null}
                  </div>
                  {falls.length === 0 ? (
                    <p className="popover-empty">No falls detected. New alerts also appear on screen as they happen.</p>
                  ) : (
                    <ul className="notification-list">
                      {[...falls].reverse().slice(0, 6).map((event) => (
                        <li key={event.event_id}>
                          <span className="notification-icon" aria-hidden="true"><AlertTriangle /></span>
                          <div>
                            <strong>{cameraName(event.camera_id)}</strong>
                            <span>{new Date(event.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{typeof event.payload.fall_score === 'number' ? ` · score ${event.payload.fall_score.toFixed(2)}` : ''}</span>
                            {event.incident_id ? <Link to={`/app/incidents?selected=${encodeURIComponent(event.incident_id)}`} onClick={() => { markSeen(); setNotificationsOpen(false); }}>Review incident</Link> : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <Link className="popover-footer-link" to="/app/incidents?status=unreviewed" onClick={() => setNotificationsOpen(false)}>All incidents not reviewed yet →</Link>
                </div>
              ) : null}
            </div>
            <div className="topbar-popover-wrap">
              <button
                ref={userMenuButtonRef}
                className="user-menu-button"
                type="button"
                aria-label={`Account menu for ${displayName}`}
                aria-haspopup="dialog"
                aria-expanded={userMenuOpen}
                onClick={() => {
                  setUserMenuOpen((open) => !open);
                  setNotificationsOpen(false);
                }}
              >
                <span className="avatar" aria-hidden="true">{displayName.trim().charAt(0).toUpperCase() || 'O'}</span>
                <span className="user-meta"><strong>{displayName}</strong><small>{user?.organization ?? roleLabel(user?.role)}</small></span>
                <ChevronDown aria-hidden="true" />
              </button>
              {userMenuOpen ? (
                <div ref={popoverRef} className="popover user-panel" role="dialog" aria-label="Account menu">
                  <div className="user-panel-identity">
                    <div className="user-identity-head">
                      <span className="avatar avatar-sm" aria-hidden="true">
                        {displayName.trim().charAt(0).toUpperCase() || 'O'}
                      </span>
                      <div className="user-identity-names">
                        <strong>{displayName}</strong>
                        <span>{user?.email ?? 'Signed in'}</span>
                      </div>
                    </div>
                    <span className="tag tag-blue user-role-tag">{roleLabel(user?.role)}</span>
                  </div>

                  <nav className="user-panel-nav" aria-label="User navigation">
                    <Link className="user-menu-item" to="/app/settings?tab=account" onClick={() => setUserMenuOpen(false)}>
                      <UserIcon aria-hidden="true" />
                      <span>Account &amp; password</span>
                    </Link>
                    {isAdmin ? (
                      <Link className="user-menu-item" to="/app/settings" onClick={() => setUserMenuOpen(false)}>
                        <Sliders aria-hidden="true" />
                        <span>Workspace settings</span>
                      </Link>
                    ) : null}
                  </nav>

                  <div className="user-panel-section">
                    <span className="user-panel-section-title">Appearance</span>
                    <div className="segmented-theme-toggle" role="radiogroup" aria-label="Appearance on this device">
                      {(['light', 'dark', 'system'] as ThemePreference[]).map((value) => (
                        <label key={value} className={`segmented-theme-item${theme.preference === value ? ' is-active' : ''}`}>
                          <input
                            type="radio"
                            name="appearance"
                            value={value}
                            checked={theme.preference === value}
                            onChange={() => theme.setPreference(value)}
                          />
                          <span className="segmented-theme-label">
                            {value === 'light' ? <Sun aria-hidden="true" /> : value === 'dark' ? <Moon aria-hidden="true" /> : <Monitor aria-hidden="true" />}
                            <span>{value === 'light' ? 'Light' : value === 'dark' ? 'Dark' : 'System'}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="user-panel-footer">
                    <button
                      className="user-signout-btn"
                      type="button"
                      onClick={() => {
                        setUserMenuOpen(false);
                        void signOut().then(() => navigate('/signin', { replace: true }));
                      }}
                    >
                      <LogOut aria-hidden="true" />
                      <span>Sign out</span>
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        <FallAlerts />
        <main className="app-content">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
