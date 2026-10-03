import { ImageOff } from 'lucide-react';
import { useState, type JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import { useIncidentDetail } from '../../hooks/useIncidentDetail.ts';

/** At most one detail request per visible row (the queue is capped at ten). */
export function IncidentQueuePreview({ incidentId }: { incidentId: string }): JSX.Element {
  const { data, loading, error } = useIncidentDetail(incidentId);
  const [failed, setFailed] = useState(false);
  const evidence = data?.id === incidentId ? data.evidence.find((item) => item.mime_type.startsWith('image/')) : undefined;
  const label = loading ? 'Loading preview' : error || failed ? 'Preview unavailable' : 'No saved image';

  return (
    <span className="incident-queue-preview">
      {evidence && !failed ? (
        <img
          src={getApiClient().evidenceUrl(incidentId, evidence.id)}
          alt="Saved incident preview"
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="incident-preview-fallback" title={label}>
          <ImageOff aria-hidden="true" />
          <small>{label}</small>
        </span>
      )}
    </span>
  );
}
