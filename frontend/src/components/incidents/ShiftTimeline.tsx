import type { JSX } from 'react';
import { Link } from 'react-router-dom';
import type { Incident } from '../../api/types.ts';
import { parseApiTime } from '../../utils/format.ts';

const TIME = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const STATE: Record<string, { key: string; text: string }> = {
  confirmed_fall: { key: 'fall', text: 'Real fall' },
  non_fall: { key: 'safe', text: 'False alarm' },
  uncertain: { key: 'unsure', text: 'Unsure' },
};
const NOT_REVIEWED = { key: 'review', text: 'Not reviewed' };
const TICKS = [0, 6, 12, 18, 24];

function dayFraction(date: Date, start: Date): number {
  return Math.min(1, Math.max(0, (date.getTime() - start.getTime()) / 86_400_000));
}

/**
 * Today's alerts on a midnight-to-midnight track, marked by their review decision.
 * Each marker opens the incident, so the day's unfinished work is visible at a glance.
 */
export function ShiftTimeline({ incidents, cameraName, now = new Date() }: { incidents: readonly Incident[]; cameraName: (id: string) => string; now?: Date }): JSX.Element {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const today = incidents.filter((incident) => parseApiTime(incident.confirmed_at) >= start);
  const nowPct = dayFraction(now, start) * 100;
  return (
    <div className="shift-timeline">
      <div className="shift-track" role="list" aria-label="Alerts today, by time">
        <span className="shift-elapsed" style={{ width: `${nowPct}%` }} aria-hidden="true" />
        <span className="shift-now" style={{ left: `${nowPct}%` }} aria-hidden="true"><span>Now</span></span>
        {today.map((incident) => {
          const at = parseApiTime(incident.confirmed_at);
          const state = (incident.review_label && STATE[incident.review_label]) || NOT_REVIEWED;
          const label = `${cameraName(incident.camera_id)}, ${TIME.format(at)}, ${state.text}`;
          return (
            <span role="listitem" key={incident.id} className="shift-marker-wrap" style={{ left: `${dayFraction(at, start) * 100}%` }}>
              <Link className={`shift-marker shift-${state.key}`} to={`/app/incidents?selected=${encodeURIComponent(incident.id)}`} aria-label={label} title={label} />
            </span>
          );
        })}
      </div>
      <div className="shift-scale" aria-hidden="true">
        {TICKS.map((hour) => <span key={hour} style={{ left: `${(hour / 24) * 100}%` }}>{String(hour % 24).padStart(2, '0')}:00</span>)}
      </div>
      {today.length === 0 ? <p className="helper">No alerts yet today.</p> : (
        <ul className="shift-legend" aria-label="Marker key">
          {[NOT_REVIEWED, STATE.confirmed_fall, STATE.non_fall, STATE.uncertain].map((state) => (
            <li key={state.key}><span className={`shift-marker shift-${state.key}`} aria-hidden="true" />{state.text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
