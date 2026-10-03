import { ChevronLeft, ChevronRight, FileText, Sparkles } from 'lucide-react';
import { useEffect, useRef, type JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import type { AgentEnrichment, IncidentDetail } from '../../api/types.ts';
import { useAuth } from '../../features/auth/useAuth.ts';
import { useDashboardContext } from '../../hooks/useDashboardContext.ts';
import { useIncidentDetail } from '../../hooks/useIncidentDetail.ts';
import { formatFallScore, formatTimestamp, parseApiTime } from '../../utils/format.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';
import { DecisionBar } from './DecisionBar.tsx';
import { KeyframeStrip } from './KeyframeStrip.tsx';
import { ResponsePanel } from './ResponsePanel.tsx';
import { ReviewTag } from './ReviewTag.tsx';

const LIVE_UPDATES = new Set(['incident.response', 'incident.escalated', 'incident.reviewed']);
const DECISION_TEXT: Record<string, string> = { confirmed_fall: 'Real fall', non_fall: 'False alarm', uncertain: 'Unsure' };
const VERDICT_TEXT: Record<string, string> = { fall: 'Looks like a fall', no_fall: 'Does not look like a fall', unclear: 'Cannot tell' };
const DETAIL_TIME = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });

function latestLabel(detail: IncidentDetail): string | null {
  const latest = [...detail.reviews].sort((a, b) => a.created_at.localeCompare(b.created_at)).at(-1);
  return latest?.label ?? null;
}

function SecondOpinion({ enrichment, technical }: { enrichment: AgentEnrichment; technical: boolean }): JSX.Element {
  const output = enrichment.output ?? {};
  const verdict = typeof output.fall_assessment === 'string' ? output.fall_assessment : null;
  const summary = typeof output.scene_summary === 'string' ? output.scene_summary : null;
  const posture = typeof output.posture_description === 'string' ? output.posture_description : null;
  if (enrichment.status !== 'completed') {
    return <p className="helper">AI second opinion: {enrichment.status === 'failed' ? (technical ? `failed (${enrichment.error_code ?? 'error'})` : 'not available') : 'in progress…'}</p>;
  }
  return (
    <div className="second-opinion">
      <p className="section-label"><Sparkles aria-hidden="true" /> AI second opinion{technical ? ` · ${enrichment.model ?? enrichment.provider ?? 'VLM'}` : ''}</p>
      {verdict ? <strong>{VERDICT_TEXT[verdict] ?? verdict}</strong> : null}
      {summary ? <p>{summary}</p> : null}
      {posture ? <p className="helper">Posture: {posture}</p> : null}
      <p className="helper">Generated text; it never overrides your decision.</p>
    </div>
  );
}

/** One incident: what the camera saw, the decision to record, and the facts behind it. */
function IncidentDetailView({
  incidentId,
  cameraName,
  onReviewSaved,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
  alertThreshold = 0.55,
}: {
  incidentId: string;
  cameraName?: string;
  alertThreshold?: number;
  onReviewSaved?: (incidentId: string) => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}): JSX.Element {
  const { data, loading, error, reload } = useIncidentDetail(incidentId);
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  // Refresh when another dashboard responds to, or the server escalates, this incident.
  const { events } = useDashboardContext();
  const lastEvent = useRef<string | null>(null);
  useEffect(() => {
    const latest = [...events.events].reverse().find((event) => event.incident_id === incidentId && LIVE_UPDATES.has(event.event_type));
    if (!latest || latest.event_id === lastEvent.current) return;
    const first = lastEvent.current === null;
    lastEvent.current = latest.event_id;
    if (!first) reload();
  }, [events.events, incidentId, reload]);
  // Keep showing the incident while it refreshes after a decision.
  if (loading && !data) return <LoadingState label="Loading incident…" />;
  if (error || !data) return <ErrorState message={error ?? 'Incident unavailable'} onRetry={reload} />;
  if (data.id !== incidentId) return <LoadingState label="Loading incident…" />;

  const label = latestLabel(data);
  const reviews = [...data.reviews].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const completed = data.enrichments.filter((e) => e.status === 'completed').at(-1) ?? data.enrichments.at(-1);
  const primaryEvidence = data.evidence.find((e) => e.mime_type.startsWith('image/'));
  const posterUrl = primaryEvidence ? getApiClient().evidenceUrl(data.id, primaryEvidence.id) : null;

  return (
    <article className="incident-detail-view" aria-label={`Incident from ${cameraName ?? data.camera_id}`}>
      {(onPrev || onNext) ? (
        <div className="incident-detail-nav-bar">
          <div className="incident-detail-nav">
            <button type="button" aria-label="Previous incident" disabled={!hasPrev} onClick={onPrev}>
              <ChevronLeft aria-hidden="true" /> Previous
            </button>
            <button type="button" aria-label="Next incident" disabled={!hasNext} onClick={onNext}>
              Next <ChevronRight aria-hidden="true" />
            </button>
          </div>
        </div>
      ) : null}

      {/* Media section: Left large video, Right keyframes */}
      <div className="incident-media-layout">
        <div className="incident-video-preview">
          {posterUrl ? <img src={posterUrl} alt="Camera view at the alert" /> : <p className="helper">No keyframe saved.</p>}
        </div>
        <div className="incident-keyframes-column">
          <KeyframeStrip items={data.evidence} />
        </div>
      </div>

      {/* Header Info: Camera title, timestamp, status badge + Confidence */}
      <div className="incident-detail-info-row">
        <div className="incident-detail-meta-left">
          <div className="incident-detail-title-line">
            <h3>{cameraName ?? data.camera_id}</h3>
            <ReviewTag label={label} />
          </div>
          <span className="incident-detail-sub">
            {DETAIL_TIME.format(parseApiTime(data.confirmed_at))} · tracked person {data.track_id}
          </span>
        </div>
        <div className="incident-detail-confidence-box">
          <span className="confidence-title">Detector score</span>
          <div className="confidence-val-row">
            <strong>{data.fall_score.toFixed(2)}</strong>
            <div className="confidence-bar-detail" aria-hidden="true">
              <span
                style={{
                  width: `${Math.round(data.fall_score * 100)}%`,
                  backgroundColor: data.fall_score >= alertThreshold ? 'var(--red)' : 'var(--text-muted)',
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Incident Summary Box: only the detector's recorded reason, never placeholder text */}
      {typeof data.evidence_features.reason === 'string' && data.evidence_features.reason ? (
        <div className="incident-summary-box">
          <FileText className="incident-summary-icon" aria-hidden="true" />
          <div className="incident-summary-content">
            <strong>Why the detector raised it</strong>
            <p>{data.evidence_features.reason}</p>
          </div>
        </div>
      ) : null}

      {data.camera_id !== 'video-analysis' ? (
        <ResponsePanel
          incidentId={data.id}
          status={data.response_status ?? 'open'}
          responder={data.responder}
          entries={data.responses ?? []}
          onSaved={() => { reload(); onReviewSaved?.(data.id); }}
        />
      ) : null}

      {/* Decision Bar */}
      <DecisionBar incidentId={data.id} current={label} onSaved={() => { reload(); onReviewSaved?.(data.id); }} />

      {/* AI Second Opinion */}
      {completed ? <SecondOpinion enrichment={completed} technical={isAdmin} /> : null}

      {/* Bottom Collapsible / Secondary Details */}
      <div className="incident-detail-subgrid">
        {isAdmin ? <details className="incident-facts">
          <summary>Detector details</summary>
          <dl className="kv">
            <dt>Person (track)</dt><dd>{data.track_id}</dd>
            <dt>Detector score</dt><dd>{formatFallScore(data.fall_score)}</dd>
            <dt>Reason</dt><dd>{typeof data.evidence_features.reason === 'string' ? data.evidence_features.reason : '—'}</dd>
            <dt>Descent started</dt><dd>{formatTimestamp(data.started_at)}</dd>
            <dt>Fall confirmed</dt><dd>{formatTimestamp(data.confirmed_at)}</dd>
            <dt>Model</dt><dd>{data.model_name} {data.model_version} · {data.config_version}</dd>
            <dt>Incident ID</dt><dd>{data.id}</dd>
          </dl>
        </details> : null}

        {reviews.length > 0 ? (
          <section className="incident-history-section" aria-label="Decision history">
            <p className="section-label">Decision history</p>
            <ul className="review-history-list">
              {reviews.map((review) => (
                <li key={review.id}>
                  <strong>{DECISION_TEXT[review.label] ?? review.label}</strong>
                  <span>{review.reviewer ?? 'Unknown reviewer'} · {formatTimestamp(review.created_at)}</span>
                  {review.notes ? <p>{review.notes}</p> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </article>
  );
}

export function IncidentDetailPanel({
  selectedId,
  cameraName,
  onReviewSaved,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
  alertThreshold,
}: {
  selectedId: string | null;
  cameraName?: string;
  alertThreshold?: number;
  onReviewSaved?: (incidentId: string) => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}): JSX.Element {
  if (!selectedId) return <EmptyState title="Select an incident" detail="Pick one from the list to see its keyframes and record whether it was a real fall." />;
  return (
    <IncidentDetailView
      key={selectedId}
      incidentId={selectedId}
      cameraName={cameraName}
      onReviewSaved={onReviewSaved}
      onPrev={onPrev}
      onNext={onNext}
      hasPrev={hasPrev}
      hasNext={hasNext}
      alertThreshold={alertThreshold}
    />
  );
}

