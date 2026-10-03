import { Activity, Bell, Camera, ChevronRight, ClipboardCheck, Database, HeartPulse, Play, ShieldCheck, Upload } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi, type IncidentStats } from '../api/platform.ts';
import { Card, MetricCard, PageHeader, StatusPill } from '../components/common/Ui.tsx';
import { ShiftTimeline } from '../components/incidents/ShiftTimeline.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { ResponseTag } from '../components/incidents/ResponsePanel.tsx';
import { ReviewTag } from '../components/incidents/ReviewTag.tsx';
import { sourceTitle } from '../features/live/sourceLabels.ts';
import { useLiveStatus } from '../features/live/useLiveStatus.ts';
import { useAuth } from '../features/auth/useAuth.ts';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { useIncidents } from '../hooks/useIncidents.ts';
import { formatFallScore, parseApiTime } from '../utils/format.ts';
import { CameraPreviews, IncidentThumbnail, TodayActivity } from './OverviewWorkspace.tsx';
import './DashboardPage.css';
import './OverviewReference.css';

const REFRESH_EVENTS = new Set(['fall.confirmed', 'incident.persisted', 'incident.reviewed', 'incident.response', 'incident.escalated']);
const TIME = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const DAY = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });

function useIncidentStats(): { data: IncidentStats | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<IncidentStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    incidentApi.stats()
      .then((value) => { if (!cancelled) { setData(value); setError(null); } })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Statistics unavailable.'); });
    return () => { cancelled = true; };
  }, [tick]);
  return { data, error, reload };
}

function when(iso: string): string {
  const date = parseApiTime(iso);
  const today = new Date();
  return date.toDateString() === today.toDateString() ? TIME.format(date) : `${DAY.format(date)}, ${TIME.format(date)}`;
}

/** Shown in the live card when nothing runs: the three ways to start detection. */
function StartChoices({ allowFiles }: { allowFiles: boolean }): JSX.Element {
  const all = [
    { to: '/app/surveillance?source=camera', icon: <Camera aria-hidden="true" />, title: 'Watch a camera', detail: 'Live detection from a webcam on this computer' },
    { to: '/app/surveillance?source=video', icon: <Database aria-hidden="true" />, title: 'Test with a dataset clip', detail: 'Labelled URFD recordings with a known answer' },
    { to: '/app/surveillance?source=upload', icon: <Upload aria-hidden="true" />, title: 'Analyse your own video', detail: 'Upload MP4, AVI, MOV, MKV or WebM' },
  ];
  const choices = allowFiles ? all : all.filter((choice) => choice.to === '/app/surveillance?source=camera');
  return (
    <div className="start-choices">
      <ul>
        {choices.map((choice) => (
          <li key={choice.to}><Link to={choice.to} className="start-choice"><span className="choice-icon">{choice.icon}</span><span><strong>{choice.title}</strong><small>{choice.detail}</small></span><ChevronRight aria-hidden="true" /></Link></li>
        ))}
      </ul>
    </div>
  );
}

export function DashboardPage(): JSX.Element {
  const { cameras, ready, events } = useDashboardContext();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const stats = useIncidentStats();
  const live = useLiveStatus(2000);
  const recent = useIncidents({ limit: 5, offset: 0 });
  const [dayStart] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString(); });
  const todays = useIncidents({ limit: 100, offset: 0, from: dayStart });
  const reloadRecent = recent.reload;
  const reloadToday = todays.reload;
  const reloadStats = stats.reload;
  const lastEvent = useRef<string | null>(null);

  useEffect(() => {
    const latest = [...events.events].reverse().find((event) => REFRESH_EVENTS.has(event.event_type));
    if (!latest || latest.event_id === lastEvent.current) return;
    lastEvent.current = latest.event_id;
    reloadRecent();
    reloadToday();
    reloadStats();
  }, [events.events, reloadRecent, reloadToday, reloadStats]);

  const active = Object.values(live.sessions).filter((session) => session.active);
  const featured = active[0];
  const cameraNames = new Map((cameras.data ?? []).map((camera) => [camera.id, camera.name]));
  const week = stats.data?.last_7_days ?? [];
  const weekTotal = week.reduce((sum, day) => sum + day.count, 0);
  const needsReview = stats.data?.unreviewed ?? null;
  const systemOk = ready.data?.status === 'ready';

  // A quiet decorative motif matching the reference; these bars encode no values.
  const texture = <span className="overview-summary-texture" aria-hidden="true">{[16, 23, 19, 29, 36, 46, 32].map((height, index) => <i key={index} style={{ height }} />)}</span>;

  return (
    <div className="overview-page">
      <PageHeader
        eyebrow="MONITOR"
        title="Overview"
        subtitle="What needs your attention now: unreviewed alerts, what is being monitored, and today's alerts by time."
      >
        {needsReview ? (
          <>
            <Link className="btn btn-secondary" to="/app/surveillance"><Play aria-hidden="true" /><span><strong>Start monitoring</strong><small>Open live view</small></span></Link>
            <Link className="btn btn-primary" to="/app/review"><ClipboardCheck aria-hidden="true" /><span><strong>Review {needsReview} alert{needsReview === 1 ? '' : 's'}</strong><small>Check unreviewed</small></span></Link>
          </>
        ) : <Link className="btn btn-primary" to="/app/surveillance"><Play aria-hidden="true" /><span><strong>Start monitoring</strong><small>Open live view</small></span></Link>}
      </PageHeader>

      <section className="overview-kpis" aria-label="Summary">
        <MetricCard label="Not reviewed" value={needsReview ?? '—'} tone={needsReview ? 'amber' : 'green'} icon={<ClipboardCheck />}
          detail={stats.error ? 'Count unavailable' : needsReview ? <Link to="/app/review">Review them now</Link> : needsReview === 0 ? 'All incidents reviewed' : 'Loading review count'}>{texture}</MetricCard>
        <MetricCard label="Alerts today" value={stats.data?.today ?? '—'} tone={stats.data?.today ? 'red' : 'blue'} icon={<Bell />}
          detail={stats.data ? `${weekTotal} this week · ${stats.data.total} recorded in total` : 'Since local midnight'}>{texture}</MetricCard>
        <MetricCard label="Monitoring" value={live.error ? 'Check' : active.length ? `${active.length} running` : 'Idle'} tone="blue" icon={<Camera />}
          detail={live.error ? 'Live status unavailable' : active.length ? active.map((session) => sourceTitle(session.source_type, session.source)).join(', ') : <Link to="/app/surveillance">Start a camera or video</Link>}>{texture}</MetricCard>
        <MetricCard label="System" value={ready.loading ? '…' : systemOk ? 'Ready' : 'Check'} tone={systemOk ? 'green' : 'amber'} icon={<HeartPulse />}
          detail={isAdmin
            ? (ready.error ? <Link to="/app/telemetry">Status unavailable · open System health</Link> : `Database ${ready.data?.database ?? '—'} · detector ${ready.data?.vision_service ?? '—'}`)
            : ready.loading ? 'Checking system status' : ready.error || (ready.data && !systemOk) ? 'Something is not working · tell your admin' : 'Fall detection is available'}>{texture}</MetricCard>
      </section>

      <section className="overview-main-grid" aria-label="Live view and latest incidents">
        <Card className="overview-media-card" title="Live monitoring workspace" icon={<Camera />}>
          <p className="overview-workspace-intro">{live.error ? 'Monitoring status could not be checked.' : featured ? `Live · ${sourceTitle(featured.source_type, featured.source)}` : 'Nothing is being monitored. Pick a source to start fall detection.'}</p>
          {live.error ? <ErrorState message={live.error} onRetry={live.refresh} /> : null}
          <div className="overview-live-workspace">
            <div className="overview-workspace-toolbar"><h3><Camera aria-hidden="true" />Live view</h3><Link className="overview-manage-link" to={isAdmin ? '/app/settings?tab=cameras' : '/app/surveillance'}><Camera aria-hidden="true" />{isAdmin ? 'Manage cameras' : 'Open Live monitor'}</Link></div>
            {cameras.error ? <ErrorState message={cameras.error} onRetry={cameras.reload} /> : cameras.loading && !cameras.data ? <LoadingState label="Loading cameras…" /> : <CameraPreviews cameras={cameras.data ?? []} sessions={active} />}
          </div>
          {!featured ? <StartChoices allowFiles={isAdmin} /> : null}
          {featured && active.length > 1 ? <p className="helper">{active.length - 1} more source{active.length > 2 ? 's' : ''} running · switch in Live monitor.</p> : null}
        </Card>

        <Card className="recent-incidents-card" title="Latest incidents" icon={<ShieldCheck />} action={<Link className="card-link" to="/app/incidents">All incidents <span aria-hidden="true">→</span></Link>}>
          {recent.loading && !recent.data ? <LoadingState label="Loading incidents…" /> : null}
          {recent.error ? <ErrorState message={recent.error} onRetry={recent.reload} /> : null}
          {!recent.error && recent.data?.items.length === 0 ? <EmptyState title="No falls recorded yet" detail="When the detector confirms a fall, it appears here for review." /> : null}
          {recent.data && recent.data.items.length > 0 ? (
            <ul className="recent-incidents-list">
              {recent.data.items.map((incident) => (
                <li key={incident.id}>
                  <Link className="recent-incident-link" to={`/app/incidents?selected=${encodeURIComponent(incident.id)}`}>
                    <IncidentThumbnail id={incident.id} />
                    <span className="recent-incident-main"><strong>{cameraNames.get(incident.camera_id) ?? incident.camera_id}</strong><small>{when(incident.confirmed_at)} · person {incident.track_id}</small><small>score {formatFallScore(incident.fall_score)}</small></span>
                    <span className="recent-incident-tags"><ResponseTag status={incident.response_status} responder={incident.responder} /><ReviewTag label={incident.review_label} /></span>
                    <ChevronRight aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>
      <Card className="shift-card" title="Today" icon={<Activity />} action={<StatusPill tone={(todays.data?.items ?? []).filter((item) => !item.review_label).length ? 'amber' : 'neutral'}>{todays.data ? `${todays.data.total} alert${todays.data.total === 1 ? '' : 's'} · ${(todays.data?.items ?? []).filter((item) => !item.review_label).length} not reviewed` : '…'}</StatusPill>}>
        {todays.error ? <ErrorState message={todays.error} onRetry={todays.reload} /> : todays.data ? (
          <>
            <TodayActivity incidents={todays.data.items} />
            {todays.data.items.length ? <ShiftTimeline incidents={todays.data.items} cameraName={(id) => cameraNames.get(id) ?? id} /> : null}
            {todays.data.total > todays.data.items.length ? <p className="helper">Showing the latest {todays.data.items.length} of {todays.data.total} alerts. <Link to="/app/incidents">View all incidents</Link></p> : null}
          </>
        ) : <LoadingState label="Loading today's alerts…" />}
      </Card>
      </section>
    </div>
  );
}
