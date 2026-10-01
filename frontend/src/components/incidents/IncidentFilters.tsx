import type { JSX } from 'react';
import { useCameras } from '../../hooks/useDashboard.ts';
import type { IncidentQuery } from '../../hooks/useIncidents.ts';

const STATUS_OPTIONS = ['', 'FALL_CONFIRMED'];
const REVIEW_OPTIONS = ['', 'confirmed_fall', 'non_fall', 'uncertain'];

/**
 * Filter bar mapping 1:1 to GET /incidents query params.
 * Camera options come from GET /cameras; selects are labelled.
 */
export function IncidentFilters({
  query,
  onChange,
}: {
  query: IncidentQuery;
  onChange: (next: IncidentQuery) => void;
}): JSX.Element {
  const cameras = useCameras();
  return (
    <div className="filters" role="search" aria-label="Incident filters">
      <div>
        <label htmlFor="filter-camera">Camera</label>
        <select
          id="filter-camera"
          value={query.camera_id ?? ''}
          disabled={cameras.loading || Boolean(cameras.error)}
          onChange={(event) => {
            onChange({ ...query, offset: 0, camera_id: event.target.value || undefined });
          }}
        >
          <option value="">All cameras</option>
          {(cameras.data ?? []).map((camera) => (
            <option key={camera.id} value={camera.id}>
              {camera.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="filter-status">Detector state</label>
        <select
          id="filter-status"
          value={query.status ?? ''}
          onChange={(event) => {
            onChange({ ...query, offset: 0, status: event.target.value || undefined });
          }}
        >
          <option value="">All states</option>
          {STATUS_OPTIONS.filter(Boolean).map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="filter-review">Review</label>
        <select
          id="filter-review"
          value={query.review_label ?? ''}
          onChange={(event) => {
            onChange({ ...query, offset: 0, review_label: event.target.value || undefined });
          }}
        >
          <option value="">All reviews</option>
          {REVIEW_OPTIONS.filter(Boolean).map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
