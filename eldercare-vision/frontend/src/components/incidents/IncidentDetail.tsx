import type { JSX } from 'react';
import { useIncidentDetail } from '../../hooks/useIncidentDetail.ts';
import { formatFallScore, formatTimestamp } from '../../utils/format.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';
import { EvidenceView } from './EvidenceView.tsx';

/**
 * P6-004 incident detail/evidence over GET /incidents/{id}. AC-042.
 * Read-only detector output; review submission arrives in P6-005.
 */
export function IncidentDetailView({ incidentId }: { incidentId: string }): JSX.Element {
  const { data, loading, error, reload } = useIncidentDetail(incidentId);

  if (loading) return <LoadingState label="Loading incident detail…" />;
  if (error || !data)
    return <ErrorState message={error ?? 'Incident unavailable'} onRetry={reload} />;

  const features = Object.entries(data.evidence_features);
  return (
    <article aria-label={`Incident ${data.id}`}>
      <dl className="kv">
        <dt>Incident</dt>
        <dd>{data.id}</dd>
        <dt>Camera</dt>
        <dd>{data.camera_id}</dd>
        <dt>Track</dt>
        <dd>{data.track_id}</dd>
        <dt>Detector state</dt>
        <dd>{data.detector_state}</dd>
        <dt>Fall score</dt>
        <dd>{formatFallScore(data.fall_score)}</dd>
        <dt>Model</dt>
        <dd>
          {data.model_name} ({data.model_version})
        </dd>
        <dt>Config</dt>
        <dd>{data.config_version}</dd>
        <dt>Started</dt>
        <dd>{formatTimestamp(data.started_at)}</dd>
        <dt>Confirmed</dt>
        <dd>{formatTimestamp(data.confirmed_at)}</dd>
        <dt>Ended</dt>
        <dd>{formatTimestamp(data.ended_at)}</dd>
      </dl>

      <h3>Temporal evidence features</h3>
      {features.length === 0 ? (
        <p style={{ color: '#5b6575' }}>No evidence features recorded.</p>
      ) : (
        <dl className="kv">
          {features.map(([key, value]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{key}</dt>
              <dd>{JSON.stringify(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <h3>Evidence</h3>
      <EvidenceView items={data.evidence} />

      <h3>Human reviews</h3>
      {data.reviews.length === 0 ? (
        <p style={{ color: '#5b6575' }}>No reviews yet. Review submission loads in P6-005.</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {data.reviews.map((review) => (
            <li key={review.id} className="incident-row">
              <div>
                <strong>{review.label}</strong>
                <div style={{ color: '#5b6575', fontSize: 13 }}>
                  {review.reviewer ?? 'Anonymous'} · {formatTimestamp(review.created_at)}
                </div>
                {review.notes ? <div>{review.notes}</div> : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      {data.enrichments.length > 0 ? (
        <div>
          <h3>
            Enrichment<span className="generated-label">Generated context</span>
          </h3>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {data.enrichments.map((enrichment) => (
              <li key={enrichment.id} className="incident-row">
                <div>
                  <strong>
                    {enrichment.status}
                    <span className="generated-label">Generated context</span>
                  </strong>
                  <div style={{ color: '#5b6575', fontSize: 13 }}>
                    {enrichment.provider ?? 'unknown provider'} · {enrichment.model ?? 'unknown model'} ·{' '}
                    {enrichment.prompt_version}
                  </div>
                  {enrichment.output ? <div>{JSON.stringify(enrichment.output)}</div> : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

export function IncidentDetailPanel({ selectedId }: { selectedId: string | null }): JSX.Element {
  if (!selectedId) {
    return (
      <EmptyState
        title="No incident selected"
        detail="Select an incident from the queue to review its detail."
      />
    );
  }
  return <IncidentDetailView key={selectedId} incidentId={selectedId} />;
}
