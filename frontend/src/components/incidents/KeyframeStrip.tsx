import type { JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import type { IncidentEvidence } from '../../api/types.ts';

// The detector stores keyframe_00 at the alert, then 1.5 s and 3 s before it.
const CAPTIONS = ['At the alert', '1.5 s before', '3 s before'];

/** The saved keyframes, newest first, each opening full size in a new tab. */
export function KeyframeStrip({ items, large = false }: { items: IncidentEvidence[]; large?: boolean }): JSX.Element {
  const frames = items
    .filter((item) => item.mime_type.startsWith('image/'))
    .sort((a, b) => a.storage_path.localeCompare(b.storage_path));
  if (frames.length === 0) return <p className="helper">No keyframes were saved for this incident.</p>;
  return (
    <ol className={`keyframe-strip${large ? ' keyframe-strip-large' : ''}`} aria-label="Saved keyframes">
      {frames.map((frame, index) => {
        const href = getApiClient().evidenceUrl(frame.incident_id, frame.id);
        const caption = CAPTIONS[index] ?? `Frame ${index + 1}`;
        return (
          <li key={frame.id}>
            <a href={href} target="_blank" rel="noreferrer" aria-label={`${caption}: open full size`}>
              <img src={href} alt={`Keyframe ${caption.toLowerCase()}`} loading="lazy" />
            </a>
            <span>{caption}</span>
          </li>
        );
      })}
    </ol>
  );
}
