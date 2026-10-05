import {
  AlertCircle,
  AlertTriangle,
  ArrowUpDown,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  FileText,
  Filter,
  RefreshCw,
  Search,
  Shield,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type JSX } from 'react';
import { useSearchParams } from 'react-router-dom';
import { incidentApi, type IncidentStats } from '../api/platform.ts';
import { Card, MetricCard, PageHeader } from '../components/common/Ui.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { SelectDropdown } from '../components/common/SelectDropdown.tsx';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';
import { IncidentQueuePreview } from '../components/incidents/IncidentQueuePreview.tsx';
import { ResponseTag } from '../components/incidents/ResponsePanel.tsx';
import { ReviewTag } from '../components/incidents/ReviewTag.tsx';
import { useAuth } from '../features/auth/useAuth.ts';
import { useWorkspaceSettings } from '../features/settings/useWorkspaceSettings.ts';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { useIncidents, type IncidentQuery } from '../hooks/useIncidents.ts';
import { formatFallScore, parseApiTime } from '../utils/format.ts';
import './OperationsPages.css';
import './IncidentsReference.css';

const PAGE_SIZE = 10;
const LIST_EVENTS = new Set(['fall.confirmed', 'incident.persisted', 'incident.response', 'incident.escalated']);
const TABS = [
  { id: '', label: 'All' },
  { id: 'unreviewed', label: 'Not reviewed' },
  { id: 'confirmed_fall', label: 'Real falls' },
  { id: 'non_fall', label: 'False alarms' },
  { id: 'uncertain', label: 'Unsure' },
] as const;
const WHEN = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/** Local calendar date (yyyy-mm-dd) → ISO bound in UTC. */
function dayBound(value: string, end = false): string | undefined {
  if (!value) return undefined;
  const parts = value.split('-').map(Number);
  if (parts.length !== 3 || parts.some((p) => isNaN(p) || p <= 0)) return undefined;
  const [y, m, d] = parts;
  const date = end ? new Date(y, m - 1, d, 23, 59, 59, 999) : new Date(y, m - 1, d, 0, 0, 0, 0);
  if (isNaN(date.getTime())) return undefined;
  return date.toISOString();
}

function BarSparkline({ values, color }: { values: readonly number[]; color: string }): JSX.Element {
  const max = Math.max(1, ...values);
  return (
    <svg className="bar-sparkline" viewBox="0 0 68 26" aria-hidden="true" style={{ width: 68, height: 26, overflow: 'visible' }}>
      {values.map((v, i) => {
        const height = Math.round((v / max) * 22);
        const y = 24 - height;
        const x = i * 7 + 2;
        return <rect key={i} x={x} y={y} width="4" height={height} rx="2" fill={color} opacity={0.35 + (v / max) * 0.65} />;
      })}
    </svg>
  );
}

function useIncidentStats(): { data: IncidentStats | null; reload: () => void } {
  const [data, setData] = useState<IncidentStats | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    incidentApi.stats()
      .then((value) => { if (!cancelled) setData(value); })
      .catch(() => { /* fallback gracefully */ });
    return () => { cancelled = true; };
  }, [tick]);
  return { data, reload };
}

export function IncidentsPage(): JSX.Element {
  const { cameras, events } = useDashboardContext();
  const [url, setUrl] = useSearchParams();
  const status = url.get('status') ?? '';
  const camera = url.get('camera') ?? '';
  const search = url.get('search') ?? '';
  const from = url.get('from') ?? '';
  const to = url.get('to') ?? '';
  const offset = Math.max(0, Number(url.get('offset') ?? 0) || 0);
  const rawSelected = url.get('selected');
  const update = useCallback((changes: Record<string, string | null>): void => {
    const next = new URLSearchParams(url);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!('offset' in changes)) next.delete('offset');
    setUrl(next);
  }, [url, setUrl]);
  const [sortOrder, setSortOrder] = useState<'newest' | 'score_desc' | 'score_asc'>('newest');

  const [searchDraft, setSearchDraft] = useState(search);
  const [syncedSearch, setSyncedSearch] = useState(search);
  if (search !== syncedSearch) {
    setSyncedSearch(search);
    setSearchDraft(search);
  }
  const [exportMessage, setExportMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const stats = useIncidentStats();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const workspace = useWorkspaceSettings();
  const alertThreshold = workspace.data?.settings.fall_threshold ?? workspace.data?.frozen_defaults.fall_threshold ?? 0.55;

  const query = useMemo<IncidentQuery>(() => ({
    limit: PAGE_SIZE,
    offset,
    camera_id: camera || undefined,
    q: search.trim() || undefined,
    reviewed: status === 'unreviewed' ? false : undefined,
    review_label: status === 'confirmed_fall' || status === 'non_fall' || status === 'uncertain' ? status : undefined,
    from: dayBound(from),
    to: dayBound(to, true),
  }), [camera, from, offset, search, status, to]);
  const incidents = useIncidents(query);
  const setIncidentQuery = incidents.setQuery;
  useEffect(() => { setIncidentQuery(query); }, [query, setIncidentQuery]);

  // New falls, responses and escalations from any dashboard refresh the list.
  const reloadIncidents = incidents.reload;
  const lastEvent = useRef<string | null>(null);
  useEffect(() => {
    const latest = [...events.events].reverse().find((event) => LIST_EVENTS.has(event.event_type));
    if (!latest || latest.event_id === lastEvent.current) return;
    const first = lastEvent.current === null;
    lastEvent.current = latest.event_id;
    if (!first) reloadIncidents();
  }, [events.events, reloadIncidents]);

  // Debounce typing into the URL so each keystroke does not hit the server.
  useEffect(() => {
    if (searchDraft === search) return undefined;
    const timer = window.setTimeout(() => update({ search: searchDraft.trim() || null }), 300);
    return () => window.clearTimeout(timer);
  }, [searchDraft, search, update]);

  const cameraNames = useMemo(() => new Map((cameras.data ?? []).map((item) => [item.id, item.name])), [cameras.data]);
  const items = useMemo(() => {
    const list = [...(incidents.data?.items ?? [])];
    if (sortOrder === 'score_desc') return list.sort((a, b) => b.fall_score - a.fall_score);
    if (sortOrder === 'score_asc') return list.sort((a, b) => a.fall_score - b.fall_score);
    return list;
  }, [incidents.data?.items, sortOrder]);

  const total = incidents.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const filtered = Boolean(camera || search || from || to);

  // Paging from the detail view stores "@first"/"@last" until the new page has loaded.
  const pageLoaded = incidents.data?.offset === offset;
  const selectedId = rawSelected === '@first' ? (pageLoaded ? items[0]?.id ?? null : null)
    : rawSelected === '@last' ? (pageLoaded ? items.at(-1)?.id ?? null : null)
    : rawSelected;
  const selectedIndex = items.findIndex((item) => item.id === selectedId);
  const hasPrev = selectedIndex > 0 || (selectedIndex === 0 && offset > 0);
  const hasNext = selectedIndex >= 0 && (selectedIndex < items.length - 1 || offset + items.length < total);

  function handleNavigate(direction: 'prev' | 'next'): void {
    if (direction === 'prev' && hasPrev) {
      if (selectedIndex > 0) update({ selected: items[selectedIndex - 1].id, offset: String(offset) });
      else update({ selected: '@last', offset: String(Math.max(0, offset - PAGE_SIZE)) });
    } else if (direction === 'next' && hasNext) {
      if (selectedIndex < items.length - 1) update({ selected: items[selectedIndex + 1].id, offset: String(offset) });
      else update({ selected: '@first', offset: String(offset + PAGE_SIZE) });
    }
  }

  async function exportReviewed(): Promise<void> {
    setExportMessage(null);
    try {
      const count = await incidentApi.exportDataset();
      setExportMessage({ ok: true, text: count ? `Downloaded ${count} reviewed incident${count === 1 ? '' : 's'} (JSONL).` : 'No reviewed incidents to export yet.' });
    } catch (error) {
      setExportMessage({ ok: false, text: error instanceof Error ? error.message : 'Export failed.' });
    }
  }

  const week = stats.data?.last_7_days ?? [];
  const weekTotal = week.reduce((sum, day) => sum + day.count, 0);

  const submitFilters = useCallback((event?: FormEvent): void => {
    if (event) event.preventDefault();
    const nextSearch = searchDraft.trim();
    update({ search: nextSearch || null, selected: null });
    incidents.reload();
    stats.reload();
  }, [searchDraft, update, incidents, stats]);

  return (
    <div className="operations-page incidents-page">
      <PageHeader
        eyebrow="RESPOND"
        title="Incidents"
        subtitle="Every fall the detector confirmed. Open one to see what the camera saw and record whether it was a real fall."
      >
        {isAdmin ? (
          <button type="button" className="btn btn-secondary" onClick={() => void exportReviewed()}>
            <Download aria-hidden="true" />Export reviewed
          </button>
        ) : null}
      </PageHeader>
      {exportMessage ? <div className={`inline-alert ${exportMessage.ok ? 'inline-alert-success' : 'inline-alert-error'} page-message`} role="status">{exportMessage.text}</div> : null}

      <section className="incidents-kpis" aria-label="Incident metrics summary">
        <MetricCard
          label="Total incidents"
          value={stats.data?.total ?? '—'}
          tone="blue"
          icon={<FileText aria-hidden="true" />}
          detail={stats.data ? `${weekTotal} in the last 7 days` : 'Count unavailable'}
        >
          {week.length ? <BarSparkline values={week.map((day) => day.count)} color="var(--blue)" /> : null}
        </MetricCard>

        <MetricCard
          label="Not reviewed"
          value={stats.data?.unreviewed ?? '—'}
          tone="amber"
          icon={<AlertCircle aria-hidden="true" />}
          detail="No decision recorded yet"
        />

        <MetricCard
          label="Real falls"
          value={stats.data?.confirmed_falls ?? '—'}
          tone="green"
          icon={<CheckCircle2 aria-hidden="true" />}
          detail="Confirmed by a reviewer"
        />

        <MetricCard
          label="False alarms"
          value={stats.data?.false_alarms ?? '—'}
          tone="violet"
          icon={<Shield aria-hidden="true" />}
          detail="Ruled out by a reviewer"
        />
      </section>

      <form className="incident-toolbar" aria-label="Incident filters" onSubmit={submitFilters}>
        <div className="incident-tabs-bar">
          <div className="segmented incident-tabs" role="tablist" aria-label="Filter by decision">
            {TABS.map((tab) => (
              <button
                key={tab.id || 'all'}
                type="button"
                role="tab"
                aria-selected={status === tab.id}
                onClick={() => update({ status: tab.id || null, selected: null })}
                onKeyDown={(event) => {
                  const index = TABS.findIndex((item) => item.id === tab.id);
                  const next = event.key === 'ArrowRight' ? (index + 1) % TABS.length
                    : event.key === 'ArrowLeft' ? (index + TABS.length - 1) % TABS.length
                    : event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : null;
                  if (next === null) return;
                  event.preventDefault();
                  update({ status: TABS[next].id || null, selected: null });
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus();
                }}
                tabIndex={status === tab.id ? 0 : -1}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {filtered ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm clear-filters-btn"
              onClick={() => {
                setSearchDraft('');
                update({ camera: null, search: null, from: null, to: null, status: null });
              }}
            >
              <X aria-hidden="true" />Clear filters
            </button>
          ) : null}
        </div>

        <div className="incident-filters">
          <div className="input-with-icon incident-search-input">
            <Search aria-hidden="true" />
            <label className="sr-only" htmlFor="incident-search">Search incidents</label>
            <input
              id="incident-search"
              type="search"
              placeholder="Search camera or incident ID…"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
            />
          </div>

          <div className="incident-camera-filter">
            <label className="sr-only" htmlFor="incident-camera">Camera</label>
            <SelectDropdown
              id="incident-camera"
              ariaLabel="Camera"
              icon={<Camera aria-hidden="true" />}
              value={camera}
              options={[
                { value: '', label: 'All cameras' },
                ...(cameras.data ?? []).map((item) => ({ value: item.id, label: item.name })),
              ]}
              onChange={(val) => update({ camera: val || null })}
            />
          </div>

          <div className="incident-date-range">
            <label className="date-field">
              <Calendar aria-hidden="true" className="filter-field-icon" />
              <span>From</span>
              <input type="date" value={from} max={to || undefined} onChange={(event) => update({ from: event.target.value || null })} />
            </label>
            <label className="date-field">
              <span>To</span>
              <input type="date" value={to} min={from || undefined} onChange={(event) => update({ to: event.target.value || null })} />
            </label>
          </div>

          <button
            type="submit"
            className="btn btn-primary incident-filter-submit"
            aria-label="Filter"
            disabled={incidents.loading}
          >
            {incidents.loading ? <RefreshCw aria-hidden="true" className="spin" /> : <Filter aria-hidden="true" />}
            <span>Filter</span>
          </button>
        </div>
      </form>

      <div className="incidents-layout">
        <Card
          className="incident-table-card"
          title={`Incident queue (${total})`}
          icon={<AlertTriangle aria-hidden="true" />}
          action={
            <SelectDropdown<'newest' | 'score_desc' | 'score_asc'>
              ariaLabel="Sort this page"
              icon={<ArrowUpDown aria-hidden="true" />}
              value={sortOrder}
              options={[
                { value: 'newest', label: 'Newest first' },
                { value: 'score_desc', label: 'Highest score on this page' },
                { value: 'score_asc', label: 'Lowest score on this page' },
              ]}
              onChange={(val) => setSortOrder(val)}
              size="sm"
              width={210}
            />
          }
        >
          {incidents.loading && !incidents.data ? <LoadingState label="Loading incidents…" /> : null}
          {incidents.error ? <ErrorState message={incidents.error} onRetry={incidents.reload} /> : null}
          {!incidents.error && incidents.data && items.length === 0 ? (
            <EmptyState
              title={status === 'unreviewed' && !filtered ? 'Every incident has been reviewed' : 'No incidents match'}
              detail={filtered ? 'Try clearing the filters.' : status ? 'Try the All tab.' : 'Falls confirmed by the detector appear here.'}
            />
          ) : null}
          {items.length > 0 ? (
            <>
              <ul className="incident-rows" aria-label="Incidents">
                {items.map((incident) => (
                  <li key={incident.id}>
                    <button
                      type="button"
                      className={`incident-row-button${selectedId === incident.id ? ' is-selected' : ''}`}
                      aria-pressed={selectedId === incident.id}
                      onClick={() => update({ selected: incident.id, offset: String(offset) })}
                    >
                      <IncidentQueuePreview incidentId={incident.id} />
                      <span className="incident-row-main">
                        <strong className="incident-row-cam-title">{cameraNames.get(incident.camera_id) ?? incident.camera_id}</strong>
                        <small className="incident-row-sub">{WHEN.format(parseApiTime(incident.confirmed_at))} · person {incident.track_id}</small>
                      </span>
                      <div className="incident-row-tag-wrap">
                        <ResponseTag status={incident.response_status} responder={incident.responder} />
                        <ReviewTag label={incident.review_label} />
                      </div>
                      <div className="incident-row-score-col" aria-label={`Detector score ${formatFallScore(incident.fall_score)}`}>
                        <strong className="incident-row-score-num">{incident.fall_score.toFixed(2)}</strong>
                        <span className="confidence-bar" aria-hidden="true">
                          <i style={{ width: `${Math.round(incident.fall_score * 100)}%`, backgroundColor: incident.fall_score >= alertThreshold ? 'var(--red)' : 'var(--text-muted)' }} />
                        </span>
                      </div>
                      <span className="incident-row-chevron" aria-hidden="true">
                        <ChevronRight style={{ width: 16, height: 16 }} />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="incident-pagination">
                <span>{offset + 1}–{Math.min(offset + items.length, total)} of {total}</span>
                <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => update({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}>
                  <ChevronLeft />
                </button>
                <strong>{page} / {pageCount}</strong>
                <button type="button" aria-label="Next page" disabled={page >= pageCount} onClick={() => update({ offset: String(offset + PAGE_SIZE) })}>
                  <ChevronRight />
                </button>
              </div>
            </>
          ) : null}
        </Card>

        <Card className={`incident-detail-card${selectedId ? '' : ' is-empty'}`} title="Review details" icon={<FileText aria-hidden="true" />}>
          {!selectedId ? <div className="incident-empty-art" aria-hidden="true"><ClipboardList /></div> : null}
          <IncidentDetailPanel
            selectedId={selectedId}
            cameraName={selectedId ? cameraNames.get(items.find((item) => item.id === selectedId)?.camera_id ?? '') : undefined}
            alertThreshold={alertThreshold}
            onReviewSaved={() => { incidents.reload(); stats.reload(); }}
            onPrev={() => handleNavigate('prev')}
            onNext={() => handleNavigate('next')}
            hasPrev={hasPrev}
            hasNext={hasNext}
          />
        </Card>
      </div>
    </div>
  );
}
