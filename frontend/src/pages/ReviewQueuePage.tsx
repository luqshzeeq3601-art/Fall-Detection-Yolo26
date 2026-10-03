import { Check, ClipboardCheck, Download, HelpCircle, ListOrdered, SkipForward, X } from 'lucide-react';
import { useEffect, useMemo, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { getApiClient } from '../api/index.ts';
import { incidentApi } from '../api/platform.ts';
import type { Incident, ReviewLabel } from '../api/types.ts';
import { Card, PageHeader, StatusPill } from '../components/common/Ui.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { KeyframeStrip } from '../components/incidents/KeyframeStrip.tsx';
import { ReviewTag } from '../components/incidents/ReviewTag.tsx';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { useIncidentDetail } from '../hooks/useIncidentDetail.ts';
import { useIncidents, type IncidentQuery } from '../hooks/useIncidents.ts';
import { shortcutDecision, type QueueDecision } from '../features/review/reviewQueue.ts';
import { formatFallScore, formatTimestamp, parseApiTime } from '../utils/format.ts';
import './OperationsPages.css';

const BATCH = 20;
const QUERY: IncidentQuery = { limit: BATCH, offset: 0, reviewed: false };
const TIME = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const BUTTONS: { decision: QueueDecision; text: string; key: string; className: string; icon: JSX.Element }[] = [
  { decision: 'confirmed_fall', text: 'Real fall', key: 'F', className: 'decision-fall', icon: <Check aria-hidden="true" /> },
  { decision: 'non_fall', text: 'False alarm', key: 'N', className: 'decision-safe', icon: <X aria-hidden="true" /> },
  { decision: 'uncertain', text: 'Unsure', key: 'U', className: 'decision-unsure', icon: <HelpCircle aria-hidden="true" /> },
  { decision: 'skip', text: 'Skip for now', key: 'S', className: 'decision-skip', icon: <SkipForward aria-hidden="true" /> },
];

function CurrentCase({ incident, cameraName, pending, onDecide }: { incident: Incident; cameraName: string; pending: QueueDecision | null; onDecide: (decision: QueueDecision) => void }): JSX.Element {
  const detail = useIncidentDetail(incident.id);
  const ready = detail.data?.id === incident.id;

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const decision = shortcutDecision(event, { dialogOpen: Boolean(document.querySelector('dialog[open], [role="dialog"]')) });
      if (!decision || pending || !ready) return;
      event.preventDefault();
      onDecide(decision);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDecide, pending, ready]);

  return (
    <div className="review-case">
      <div className="review-case-head">
        <div><strong>{cameraName}</strong><span>{formatTimestamp(incident.confirmed_at)} · person {incident.track_id} · detector score {formatFallScore(incident.fall_score)}</span></div>
        <Link to={`/app/incidents?selected=${encodeURIComponent(incident.id)}`} className="card-link">Full details →</Link>
      </div>
      {detail.loading ? <LoadingState label="Loading keyframes…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.reload} /> : detail.data ? <KeyframeStrip items={detail.data.evidence} large /> : null}
      <p className="section-label">Was this a real fall?</p>
      <div className="decision-buttons decision-buttons-queue">
        {BUTTONS.map((button) => (
          <button key={button.decision} type="button" className={`decision ${button.className}`} disabled={Boolean(pending) || !ready} onClick={() => onDecide(button.decision)}>
            {button.icon}<span>{pending === button.decision ? 'Saving…' : button.text}</span><kbd>{button.key}</kbd>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ReviewQueuePage(): JSX.Element {
  const { cameras } = useDashboardContext();
  const queue = useIncidents(QUERY);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<{ id: string; label: ReviewLabel; camera: string }[]>([]);
  const [pending, setPending] = useState<QueueDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportNote, setExportNote] = useState('');

  const cameraNames = useMemo(() => new Map((cameras.data ?? []).map((item) => [item.id, item.name])), [cameras.data]);
  const handled = useMemo(() => new Set(done.map((item) => item.id)), [done]);
  const waiting = (queue.data?.items ?? []).filter((item) => !handled.has(item.id));
  const upNext = waiting.filter((item) => !skipped.has(item.id));
  const current = upNext[0];
  const remaining = Math.max(0, (queue.data?.total ?? 0) - done.filter((item) => (queue.data?.items ?? []).some((q) => q.id === item.id)).length);

  async function decide(decision: QueueDecision): Promise<void> {
    if (!current || pending) return;
    if (decision === 'skip') {
      setSkipped((previous) => new Set(previous).add(current.id));
      return;
    }
    setPending(decision);
    setError(null);
    try {
      await getApiClient().submitReview(current.id, { label: decision });
      setDone((previous) => [{ id: current.id, label: decision, camera: cameraNames.get(current.camera_id) ?? current.camera_id }, ...previous]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The decision was not saved. Try again.');
    } finally {
      setPending(null);
    }
  }

  // Refill the batch once it runs low so long queues keep flowing.
  const reloadQueue = queue.reload;
  useEffect(() => {
    if (queue.data && queue.data.total > queue.data.items.length && upNext.length === 0) reloadQueue();
  }, [queue.data, reloadQueue, upNext.length]);

  async function exportReviewed(): Promise<void> {
    try {
      const count = await incidentApi.exportDataset();
      setExportNote(`Downloaded ${count} reviewed incident${count === 1 ? '' : 's'}.`);
    } catch (caught) {
      setExportNote(caught instanceof Error ? caught.message : 'Export failed.');
    }
  }

  return (
    <div className="operations-page review-queue-page">
      <PageHeader title="Review queue" subtitle="Go through unreviewed falls one at a time and decide whether each was real. Keys: F real fall · N false alarm · U unsure · S skip.">
        <StatusPill tone={remaining ? 'amber' : 'green'}>{remaining ? `${remaining} waiting` : 'All reviewed'}</StatusPill>
      </PageHeader>
      <div className="review-layout">
        <Card className="review-workbench" title={current ? 'Current incident' : 'Queue'} icon={<ClipboardCheck />}>
          {queue.loading && !queue.data ? <LoadingState label="Loading the queue…" /> : null}
          {queue.error ? <ErrorState message={queue.error} onRetry={queue.reload} /> : null}
          {error ? <div className="inline-alert inline-alert-error" role="alert">{error}</div> : null}
          {current ? <CurrentCase key={current.id} incident={current} cameraName={cameraNames.get(current.camera_id) ?? current.camera_id} pending={pending} onDecide={(decision) => void decide(decision)} /> : null}
          {queue.data && !current ? (
            skipped.size > 0 && waiting.length > 0
              ? <EmptyState title="Only skipped incidents left" detail={`${waiting.length} skipped this session.`} action={<button type="button" className="btn btn-secondary" onClick={() => setSkipped(new Set())}>Go through skipped ones</button>} />
              : <EmptyState title="Nothing waiting for review" detail="New falls from the Live monitor will appear here." />
          ) : null}
        </Card>
        <aside className="review-side-column">
          <Card title="Up next" icon={<ListOrdered />}>
            {upNext.length <= 1 ? <p className="helper">{upNext.length === 1 ? 'This is the last one in the queue.' : 'Nothing queued.'}</p> : (
              <ol className="queue-list">
                {upNext.slice(1, 6).map((item) => <li key={item.id}><strong>{cameraNames.get(item.camera_id) ?? item.camera_id}</strong><span>{TIME.format(parseApiTime(item.confirmed_at))} · score {formatFallScore(item.fall_score)}</span></li>)}
              </ol>
            )}
            {upNext.length > 6 ? <p className="helper">and {upNext.length - 6} more…</p> : null}
          </Card>
          <Card title={`Reviewed this session · ${done.length}`} icon={<Check />} action={<button type="button" className="btn btn-ghost btn-sm" onClick={() => void exportReviewed()}><Download aria-hidden="true" />Export</button>}>
            {exportNote ? <p className="helper" role="status">{exportNote}</p> : null}
            {done.length === 0 ? <p className="helper">Decisions you make here are listed so you can revisit them.</p> : (
              <ul className="queue-list">
                {done.map((item) => <li key={item.id}><Link to={`/app/incidents?selected=${encodeURIComponent(item.id)}`}><strong>{item.camera}</strong></Link><ReviewTag label={item.label} /></li>)}
              </ul>
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}
