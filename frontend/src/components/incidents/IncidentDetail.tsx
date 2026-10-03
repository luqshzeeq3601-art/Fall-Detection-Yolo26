import { Sparkles } from 'lucide-react';
import type { JSX } from 'react';
import type { AgentEnrichment, IncidentDetail } from '../../api/types.ts';
import { useIncidentDetail } from '../../hooks/useIncidentDetail.ts';
import { formatFallScore, formatTimestamp } from '../../utils/format.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';
import { DecisionBar } from './DecisionBar.tsx';
import { KeyframeStrip } from './KeyframeStrip.tsx';
import { ReviewTag } from './ReviewTag.tsx';

const DECISION_TEXT: Record<string, string> = { confirmed_fall: 'Real fall', non_fall: 'False alarm', uncertain: 'Unsure' };
const VERDICT_TEXT: Record<string, string> = { fall: 'Looks like a fall', no_fall: 'Does not look like a fall', unclear: 'Cannot tell' };

function latestLabel(detail: IncidentDetail): string | null {
  const latest = [...detail.reviews].sort((a, b) => a.created_at.localeCompare(b.created_at)).at(-1);
  return latest?.label ?? null;
}

function SecondOpinion({ enrichment }: { enrichment: AgentEnrichment }): JSX.Element {
  const output = enrichment.output ?? {};
  const verdict = typeof output.fall_assessment === 'string' ? output.fall_assessment : null;
  const summary = typeof output.scene_summary === 'string' ? output.scene_summary : null;
  const posture = typeof output.posture_description === 'string' ? output.posture_description : null;
  if (enrichment.status !== 'completed') {
    return <p className="helper">AI second opinion: {enrichment.status === 'failed' ? `failed (${enrichment.error_code ?? 'error'})` : 'in progress…'}</p>;
  }
  return (
    <div className="second-opinion">
      <p className="section-label"><Sparkles aria-hidden="true" /> AI second opinion · {enrichment.model ?? enrichment.provider ?? 'VLM'}</p>
      {verdict ? <strong>{VERDICT_TEXT[verdict] ?? verdict}</strong> : null}
      {summary ? <p>{summary}</p> : null}
      {posture ? <p className="helper">Posture: {posture}</p> : null}
      <p className="helper">Generated text; it never overrides your decision.</p>
    </div>
  );
}

/** One incident: what the camera saw, the decision to record, and the facts behind it. */
export function IncidentDetailView({ incidentId, cameraName, onReviewSaved }: { incidentId: string; cameraName?: string; onReviewSaved?: (incidentId: string) => void }): JSX.Element {
  const { data, loading, error, reload } = useIncidentDetail(incidentId);
  // Keep showing the incident while it refreshes after a decision.
  if (loading && !data) return <LoadingState label="Loading incident…" />;
  if (error || !data) return <ErrorState message={error ?? 'Incident unavailable'} onRetry={reload} />;
  if (data.id !== incidentId) return <LoadingState label="Loading incident…" />;

  const label = latestLabel(data);
  const reviews = [...data.reviews].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const completed = data.enrichments.filter((e) => e.status === 'completed').at(-1) ?? data.enrichments.at(-1);

  return (
    <article className="incident-detail-view" aria-label={`Incident from ${cameraName ?? data.camera_id}`}>
      <header className="incident-detail-head">
        <div><strong>{cameraName ?? data.camera_id}</strong><span>{formatTimestamp(data.confirmed_at)}</span></div>
        <ReviewTag label={label} />
      </header>

      <KeyframeStrip items={data.evidence} />
      <DecisionBar incidentId={data.id} current={label} onSaved={() => { reload(); onReviewSaved?.(data.id); }} />

      {completed ? <SecondOpinion enrichment={completed} /> : null}

      <details className="incident-facts">
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
      </details>

      <section aria-label="Decision history">
        <p className="section-label">Decision history</p>
        {reviews.length === 0 ? <p className="helper">No decision recorded yet.</p> : (
          <ul className="review-history-list">
            {reviews.map((review) => (
              <li key={review.id}>
                <strong>{DECISION_TEXT[review.label] ?? review.label}</strong>
                <span>{review.reviewer ?? 'Unknown reviewer'} · {formatTimestamp(review.created_at)}</span>
                {review.notes ? <p>{review.notes}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}

export function IncidentDetailPanel({ selectedId, cameraName, onReviewSaved }: { selectedId: string | null; cameraName?: string; onReviewSaved?: (incidentId: string) => void }): JSX.Element {
  if (!selectedId) return <EmptyState title="Select an incident" detail="Pick one from the list to see its keyframes and record whether it was a real fall." />;
  return <IncidentDetailView key={selectedId} incidentId={selectedId} cameraName={cameraName} onReviewSaved={onReviewSaved} />;
}
