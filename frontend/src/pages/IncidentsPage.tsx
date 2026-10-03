import { AlertTriangle, CalendarDays, ChevronLeft, ChevronRight, Download, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState, type JSX } from 'react';
import { useSearchParams } from 'react-router-dom';
import { incidentApi } from '../api/platform.ts';
import { Card, PageHeader } from '../components/common/Ui.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';
import { ReviewTag } from '../components/incidents/ReviewTag.tsx';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { useIncidents, type IncidentQuery } from '../hooks/useIncidents.ts';
import { formatFallScore, parseApiTime } from '../utils/format.ts';
import './OperationsPages.css';

const PAGE_SIZE = 10;
const TABS = [
  { id: '', label: 'All' },
  { id: 'unreviewed', label: 'Needs review' },
  { id: 'confirmed_fall', label: 'Real falls' },
  { id: 'non_fall', label: 'False alarms' },
] as const;
const WHEN = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/** Local calendar date (yyyy-mm-dd) → ISO bound in UTC. */
function dayBound(value: string, end = false): string | undefined {
  if (!value) return undefined;
  const [y, m, d] = value.split('-').map(Number);
  const date = end ? new Date(y, m - 1, d, 23, 59, 59, 999) : new Date(y, m - 1, d);
  return date.toISOString();
}

export function IncidentsPage(): JSX.Element {
  const { cameras } = useDashboardContext();
  const [url, setUrl] = useSearchParams();
  const status = url.get('status') ?? '';
  const camera = url.get('camera') ?? '';
  const search = url.get('search') ?? '';
  const from = url.get('from') ?? '';
  const to = url.get('to') ?? '';
  const offset = Math.max(0, Number(url.get('offset') ?? 0) || 0);
  const selectedId = url.get('selected');
  const [searchDraft, setSearchDraft] = useState(search);
  const [syncedSearch, setSyncedSearch] = useState(search);
  if (search !== syncedSearch) {
    // The URL changed elsewhere (e.g. the top-bar search): show it in the box.
    setSyncedSearch(search);
    setSearchDraft(search);
  }
  const [exportMessage, setExportMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const query = useMemo<IncidentQuery>(() => ({
    limit: PAGE_SIZE,
    offset,
    camera_id: camera || undefined,
    q: search.trim() || undefined,
    reviewed: status === 'unreviewed' ? false : undefined,
    review_label: status === 'confirmed_fall' || status === 'non_fall' ? status : undefined,
    from: dayBound(from),
    to: dayBound(to, true),
  }), [camera, from, offset, search, status, to]);
  const incidents = useIncidents(query);
  const setIncidentQuery = incidents.setQuery;
  useEffect(() => { setIncidentQuery(query); }, [query, setIncidentQuery]);

  // Debounce typing into the URL so each keystroke does not hit the server.
  useEffect(() => {
    if (searchDraft === search) return undefined;
    const timer = window.setTimeout(() => update({ search: searchDraft.trim() || null }), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- update reads the latest URL
  }, [searchDraft]);

  const cameraNames = useMemo(() => new Map((cameras.data ?? []).map((item) => [item.id, item.name])), [cameras.data]);
  const items = incidents.data?.items ?? [];
  const total = incidents.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const filtered = Boolean(camera || search || from || to);

  function update(changes: Record<string, string | null>): void {
    const next = new URLSearchParams(url);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!('offset' in changes)) next.delete('offset');
    setUrl(next);
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

  return (
    <div className="operations-page incidents-page">
      <PageHeader title="Incidents" subtitle="Every fall the detector confirmed. Open one to see what the camera saw and record whether it was a real fall.">
        <button type="button" className="btn btn-secondary" onClick={() => void exportReviewed()}><Download aria-hidden="true" />Export reviewed</button>
      </PageHeader>
      {exportMessage ? <div className={`inline-alert ${exportMessage.ok ? 'inline-alert-success' : 'inline-alert-error'} page-message`} role="status">{exportMessage.text}</div> : null}

      <div className="incident-toolbar">
        <div className="segmented incident-tabs" role="tablist" aria-label="Filter by decision">
          {TABS.map((tab) => <button key={tab.id || 'all'} type="button" role="tab" aria-selected={status === tab.id} onClick={() => update({ status: tab.id || null, selected: null })}>{tab.label}</button>)}
        </div>
        <div className="incident-filters">
          <div className="input-with-icon">
            <Search aria-hidden="true" />
            <label className="sr-only" htmlFor="incident-search">Search incidents</label>
            <input id="incident-search" type="search" placeholder="Camera, incident ID or person" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} />
          </div>
          <label className="sr-only" htmlFor="incident-camera">Camera</label>
          <select id="incident-camera" value={camera} onChange={(event) => update({ camera: event.target.value || null })}>
            <option value="">All cameras</option>
            {(cameras.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <label className="date-field"><span>From</span><input type="date" value={from} max={to || undefined} onChange={(event) => update({ from: event.target.value || null })} /></label>
          <label className="date-field"><span>To</span><input type="date" value={to} min={from || undefined} onChange={(event) => update({ to: event.target.value || null })} /></label>
          {filtered ? <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setSearchDraft(''); update({ camera: null, search: null, from: null, to: null }); }}><X aria-hidden="true" />Clear filters</button> : null}
        </div>
      </div>

      <div className="incidents-layout">
        <Card className="incident-table-card" title={`${total} incident${total === 1 ? '' : 's'}`} icon={<AlertTriangle />}>
          {incidents.loading && !incidents.data ? <LoadingState label="Loading incidents…" /> : null}
          {incidents.error ? <ErrorState message={incidents.error} onRetry={incidents.reload} /> : null}
          {!incidents.error && incidents.data && items.length === 0 ? (
            <EmptyState title={status === 'unreviewed' && !filtered ? 'Nothing waiting for review' : 'No incidents match'} detail={filtered ? 'Try clearing the filters.' : status ? 'Try the All tab.' : 'Falls confirmed by the detector appear here.'} />
          ) : null}
          {items.length > 0 ? (
            <>
              <ul className="incident-rows" aria-label="Incidents">
                {items.map((incident) => (
                  <li key={incident.id}>
                    <button type="button" className={`incident-row-button${selectedId === incident.id ? ' is-selected' : ''}`} aria-pressed={selectedId === incident.id} onClick={() => update({ selected: incident.id, offset: String(offset) })}>
                      <span className="incident-row-main"><strong>{cameraNames.get(incident.camera_id) ?? incident.camera_id}</strong><small>{WHEN.format(parseApiTime(incident.confirmed_at))} · person {incident.track_id}</small></span>
                      <span className="incident-row-score" aria-label={`Detector score ${formatFallScore(incident.fall_score)}`}><span className="confidence-bar" aria-hidden="true"><i style={{ width: `${Math.round(incident.fall_score * 100)}%` }} /></span>{formatFallScore(incident.fall_score)}</span>
                      <ReviewTag label={incident.review_label} />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="incident-pagination">
                <span>{offset + 1}–{Math.min(offset + items.length, total)} of {total}</span>
                <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => update({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}><ChevronLeft /></button>
                <strong>{page} / {pageCount}</strong>
                <button type="button" aria-label="Next page" disabled={page >= pageCount} onClick={() => update({ offset: String(offset + PAGE_SIZE) })}><ChevronRight /></button>
              </div>
            </>
          ) : null}
        </Card>
        <Card className="incident-detail-card" title={selectedId ? 'Incident' : 'Details'} icon={<CalendarDays />}>
          <IncidentDetailPanel
            selectedId={selectedId}
            cameraName={selectedId ? cameraNames.get(items.find((item) => item.id === selectedId)?.camera_id ?? '') : undefined}
            onReviewSaved={() => incidents.reload()}
          />
        </Card>
      </div>
    </div>
  );
}
