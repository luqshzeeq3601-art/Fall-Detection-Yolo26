import { Activity, AlertTriangle, Camera, ChevronRight, ClipboardCheck, Database, HeartPulse, Play, ShieldCheck, Upload } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi, type IncidentStats } from '../api/platform.ts';
import glassRibbonUrl from '../assets/glass-ribbon.png';
import { AreaChart } from '../components/charts/Charts.tsx';
import { Card, MetricCard, PageHeader, StatusPill } from '../components/common/Ui.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { ReviewTag } from '../components/incidents/ReviewTag.tsx';
import { sourceTitle } from '../features/live/sourceLabels.ts';
import { StreamViewer } from '../features/live/StreamViewer.tsx';
import { useLiveStatus } from '../features/live/useLiveStatus.ts';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { useIncidents } from '../hooks/useIncidents.ts';
import { formatFallScore, parseApiTime } from '../utils/format.ts';
import './DashboardPage.css';

const REFRESH_EVENTS = new Set(['fall.confirmed', 'incident.persisted', 'incident.reviewed']);
const WEEKDAY = new Intl.DateTimeFormat(undefined, { weekday: 'short' });
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
function StartChoices(): JSX.Element {
  const choices = [
    { to: '/app/surveillance?source=camera', icon: <Camera aria-hidden="true" />, title: 'Watch a camera', detail: 'Live detection from a webcam on this computer' },
    { to: '/app/surveillance?source=video', icon: <Database aria-hidden="true" />, title: 'Test with a dataset clip', detail: 'Labelled URFD recordings with a known answer' },
    { to: '/app/surveillance?source=upload', icon: <Upload aria-hidden="true" />, title: 'Analyse your own video', detail: 'Upload MP4, AVI, MOV, MKV or WebM' },
  ];
  return (
    <div className="start-choices">
      <p className="start-choices-lead"><strong>Nothing is being monitored.</strong> Pick a source to start fall detection.</p>
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
  const stats = useIncidentStats();
  const live = useLiveStatus(2000);
  const recent = useIncidents({ limit: 6, offset: 0 });
  const reloadRecent = recent.reload;
  const reloadStats = stats.reload;
  const lastEvent = useRef<string | null>(null);

  useEffect(() => {
    const latest = [...events.events].reverse().find((event) => REFRESH_EVENTS.has(event.event_type));
    if (!latest || latest.event_id === lastEvent.current) return;
    lastEvent.current = latest.event_id;
    reloadRecent();
    reloadStats();
  }, [events.events, reloadRecent, reloadStats]);

  const active = Object.values(live.sessions).filter((session) => session.active);
  const featured = active[0];
  const cameraNames = new Map((cameras.data ?? []).map((camera) => [camera.id, camera.name]));
  const week = stats.data?.last_7_days ?? [];
  const weekTotal = week.reduce((sum, day) => sum + day.count, 0);
  const needsReview = stats.data?.unreviewed ?? null;
  const systemOk = ready.data?.status === 'ready';

  return (
    <div className="overview-page">
      <div className="overview-ambient" aria-hidden="true"><img src={glassRibbonUrl} alt="" /></div>
      <PageHeader title="Overview" subtitle="What needs your attention now: unreviewed falls, what is being monitored, and this week's activity.">
        <Link className="btn btn-primary" to="/app/surveillance"><Play aria-hidden="true" />Start monitoring</Link>
      </PageHeader>

      <section className="overview-kpis" aria-label="Summary">
        <MetricCard label="Needs review" value={needsReview ?? '—'} tone={needsReview ? 'amber' : 'green'} icon={<ClipboardCheck />}
          detail={stats.error ? 'Count unavailable' : needsReview ? <Link to="/app/review">Review them now →</Link> : 'All incidents reviewed'} />
        <MetricCard label="Falls today" value={stats.data?.today ?? '—'} tone="red" icon={<AlertTriangle />}
          detail={stats.data ? `${weekTotal} this week · ${stats.data.total} recorded in total` : 'Since local midnight'} />
        <MetricCard label="Monitoring" value={active.length ? `${active.length} running` : 'Idle'} tone="blue" icon={<Camera />}
          detail={active.length ? active.map((session) => sourceTitle(session.source_type, session.source)).join(', ') : <Link to="/app/surveillance">Start a camera or video →</Link>} />
        <MetricCard label="System" value={ready.loading ? '…' : systemOk ? 'Ready' : 'Check'} tone={systemOk ? 'green' : 'amber'} icon={<HeartPulse />}
          detail={ready.error ? <Link to="/app/telemetry">Status unavailable · open System health</Link> : `Database ${ready.data?.database ?? '—'} · detector ${ready.data?.vision_service ?? '—'}`} />
      </section>

      <section className="overview-main-grid" aria-label="Live view and latest incidents">
        <Card className="overview-media-card" title={featured ? `Live · ${sourceTitle(featured.source_type, featured.source)}` : 'Live view'} icon={<Camera />}
          action={featured ? <Link className="card-link" to="/app/surveillance">Open Live monitor <span aria-hidden="true">→</span></Link> : undefined}>
          {featured ? <StreamViewer compact session={featured} placeholder={null} /> : <StartChoices />}
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
                    <span className="recent-incident-main"><strong>{cameraNames.get(incident.camera_id) ?? incident.camera_id}</strong><small>{when(incident.confirmed_at)} · person {incident.track_id} · score {formatFallScore(incident.fall_score)}</small></span>
                    <ReviewTag label={incident.review_label} />
                    <ChevronRight aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>
      </section>

      <Card className="weekly-card" title="Falls per day" icon={<Activity />} action={<StatusPill tone="blue">{weekTotal} in the last 7 days</StatusPill>}>
        {stats.error ? <ErrorState message={stats.error} onRetry={stats.reload} /> : week.length ? (
          <AreaChart values={week.map((day) => day.count)} labels={week.map((day) => WEEKDAY.format(new Date(`${day.date}T12:00:00`)))} color="var(--blue)" />
        ) : <LoadingState label="Loading the last 7 days…" />}
      </Card>
    </div>
  );
}
