import type { JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import type { IncidentEvidence } from '../../api/types.ts';
import { formatTimestamp } from '../../utils/format.ts';

/**
 * Evidence references via backend-approved routes only.
 * Links never embed filesystem paths; metadata renders as plain text.
 */
export function EvidenceView({ items }: { items: IncidentEvidence[] }): JSX.Element {
  if (items.length === 0) {
    return <p style={{ color: '#5b6575' }}>No evidence snapshots stored for this incident.</p>;
  }
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {items.map((item) => (
        <li key={item.id} className="incident-row">
          <div>
            <strong>{item.evidence_type}</strong>
            <div style={{ color: '#5b6575', fontSize: 13 }}>
              {item.mime_type} · Captured {formatTimestamp(item.captured_at)} · SHA-256{' '}
              {item.sha256.slice(0, 12)}…
            </div>
          </div>
          <a
            className="evidence-link"
            href={getApiClient().evidenceUrl(item.incident_id, item.id)}
          >
            Open evidence
          </a>
        </li>
      ))}
    </ul>
  );
}
