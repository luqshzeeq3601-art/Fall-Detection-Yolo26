import { ImageOff } from 'lucide-react';
import { useState, type JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import type { IncidentEvidence } from '../../api/types.ts';
import { formatTimestamp } from '../../utils/format.ts';

function SavedImage({ frame, alt }: { frame: IncidentEvidence; alt: string }): JSX.Element {
  const [failed, setFailed] = useState(false);
  return failed ? (
    <span className="review-image-unavailable"><ImageOff aria-hidden="true" /><span>This saved image is unavailable.</span></span>
  ) : <img src={getApiClient().evidenceUrl(frame.incident_id, frame.id)} alt={alt} onError={() => setFailed(true)} />;
}

/** Inspect actual saved snapshots. Never crop evidence or simulate a recording. */
export function ReviewEvidence({ items }: { items: IncidentEvidence[] }): JSX.Element {
  const frames = items.filter((item) => item.mime_type.startsWith('image/')).sort((a, b) => a.storage_path.localeCompare(b.storage_path));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = frames.find((frame) => frame.id === selectedId) ?? frames[0];
  if (!selected) return <p className="helper review-no-evidence">No keyframes were saved for this incident.</p>;

  return (
    <div className="review-evidence">
      <figure className="review-evidence-stage">
        <a href={getApiClient().evidenceUrl(selected.incident_id, selected.id)} target="_blank" rel="noreferrer" aria-label="Selected keyframe: open full size">
          <SavedImage key={selected.id} frame={selected} alt="Selected saved keyframe" />
        </a>
        <figcaption>Saved keyframe <span>{formatTimestamp(selected.captured_at)}</span></figcaption>
      </figure>
      <ol className="review-frame-strip" aria-label="Saved keyframes">
        {frames.map((frame, index) => (
          <li key={frame.id}>
            <button type="button" aria-pressed={frame.id === selected.id} aria-label={`Select keyframe ${index + 1}, ${formatTimestamp(frame.captured_at)}`} onClick={() => setSelectedId(frame.id)}>
              <SavedImage frame={frame} alt={`Saved keyframe ${index + 1}`} />
            </button>
            <span>{index === 0 ? 'At the alert' : `Keyframe ${index + 1}`}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
