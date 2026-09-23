import type { JSX } from 'react';
import { useIncidents } from '../../hooks/useIncidents.ts';
import { formatFallScore, formatTimestamp } from '../../utils/format.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';
import { IncidentFilters } from './IncidentFilters.tsx';

/**
 * P6-003 incident list/filter over GET /incidents. AC-041.
 * Selection is keyboard-accessible and lifts via onSelect (detail in P6-004).
 */
export function IncidentList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}): JSX.Element {
  const { data, loading, error, query, setQuery, reload } = useIncidents({
    limit: 50,
    offset: 0,
  });

  return (
    <div>
      <IncidentFilters query={query} onChange={setQuery} />
      {loading ? <LoadingState label="Loading incidents…" /> : null}
      {!loading && (error || !data) ? (
        <ErrorState message={error ?? 'Incidents unavailable'} onRetry={reload} />
      ) : null}
      {!loading && !error && data && data.items.length === 0 ? (
        <EmptyState
          title="No incidents match these filters"
          detail="Adjust or clear the filters to see more."
        />
      ) : null}
      {!loading && !error && data && data.items.length > 0 ? (
        <div>
          <p style={{ color: '#5b6575' }} role="status">
            Showing {data.items.length} of {data.total} incidents
          </p>
          <ul aria-label="Incidents" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {data.items.map((incident) => (
              <li key={incident.id} className="incident-row">
                <button
                  type="button"
                  onClick={() => onSelect(incident.id)}
                  aria-pressed={selectedId === incident.id}
                  aria-label={`Open incident ${incident.id} from ${incident.camera_id}`}
                  style={{ all: 'unset', cursor: 'pointer', flex: 1 }}
                >
                  <span style={{ display: 'block', fontWeight: 600 }}>
                    {incident.camera_id} · Track {incident.track_id} · Score{' '}
                    {formatFallScore(incident.fall_score)}
                  </span>
                  <span style={{ display: 'block', color: '#5b6575', fontSize: 13 }}>
                    {incident.detector_state} · Confirmed{' '}
                    {formatTimestamp(incident.confirmed_at)}
                  </span>
                </button>
                <span className="status status-neutral">{incident.detector_state}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
