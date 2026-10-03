import { Bell, Camera, ImageOff, Maximize2 } from 'lucide-react';
import { useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { getApiClient } from '../api/index.ts';
import type { Camera as CameraRow, Incident } from '../api/types.ts';
import type { LiveSessionStatus } from '../api/platform.ts';
import { StreamViewer } from '../features/live/StreamViewer.tsx';
import { sourceTitle } from '../features/live/sourceLabels.ts';
import { useIncidentDetail } from '../hooks/useIncidentDetail.ts';
import { cameraStatusMeta } from '../utils/status.ts';
import { parseApiTime } from '../utils/format.ts';

/** Only stored incident evidence is a thumbnail; decorative art is never evidence. */
export function IncidentThumbnail({ id }: { id: string }): JSX.Element {
  const detail = useIncidentDetail(id);
  const [failed, setFailed] = useState(false);
  const frame = detail.data?.evidence.find((item) => item.mime_type.startsWith('image/'));
  return (
    <span className="overview-incident-thumbnail" aria-hidden="true">
      {frame && !failed
        ? <img src={getApiClient().evidenceUrl(id, frame.id)} alt="" loading="lazy" onError={() => setFailed(true)} />
        : <ImageOff />}
    </span>
  );
}

/** Reuses configured cameras and existing streams without starting additional sources. */
export function CameraPreviews({ cameras, sessions }: { cameras: readonly CameraRow[]; sessions: readonly LiveSessionStatus[] }): JSX.Element {
  const names = new Map(cameras.map((camera) => [camera.id, camera.name]));
  const entries = [
    ...sessions.map((session) => ({ id: session.camera_id, name: names.get(session.camera_id) ?? sourceTitle(session.source_type, session.source), session, status: 'active' })),
    ...cameras.filter((camera) => !sessions.some((session) => session.camera_id === camera.id)).map((camera) => ({ id: camera.id, name: camera.name, session: undefined, status: cameraStatusMeta(camera.status).label })),
  ].slice(0, 4);
  if (!entries.length) return (
    <div className="overview-feed-empty">
      <span className="overview-feed-empty-icon"><Camera aria-hidden="true" /></span>
      <strong>Your live view starts here</strong>
      <span>Choose a camera to begin monitoring.</span>
      <span className="overview-feed-label">No live feed</span>
    </div>
  );
  return (
    <div className={`overview-camera-grid${entries.length === 1 ? ' overview-camera-grid-single' : ''}`}>
      {entries.map((entry) => (
        <div className="overview-camera-tile" key={entry.id}>
          <div className="overview-camera-heading">
            <div><strong>{entry.name}</strong><small>{entry.session ? 'Monitoring' : entry.status}</small></div>
            <Link to="/app/surveillance" aria-label={`Open Live monitor for ${entry.name}`}><Maximize2 aria-hidden="true" /></Link>
          </div>
          {entry.session ? <StreamViewer compact session={entry.session} placeholder={<span>Live feed unavailable</span>} /> : (
            <div className="overview-camera-idle"><Camera aria-hidden="true" /><span>No live feed</span></div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Real counts by local hour; an empty chart contains no invented trend. */
export function TodayActivity({ incidents, now = new Date() }: { incidents: readonly Incident[]; now?: Date }): JSX.Element {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const today = incidents.filter((incident) => { const at = parseApiTime(incident.confirmed_at); return at >= start && at < end; });
  const counts = Array.from({ length: 24 }, (_, hour) => today.filter((incident) => parseApiTime(incident.confirmed_at).getHours() === hour).length);
  const max = Math.max(4, Math.ceil(Math.max(...counts) / 4) * 4);
  const ticks = Array.from({ length: 5 }, (_, index) => max * index / 4);
  return (
    <div className="overview-today-activity">
      <svg className="overview-hourly-chart" viewBox="0 0 400 180" role="img" aria-label={`Today's alerts by local hour: ${today.length} alert${today.length === 1 ? '' : 's'}`}>
        {ticks.map((tick, index) => <text key={index} x="18" y={145 - index * 30} textAnchor="end">{tick}</text>)}
        {[0, 6, 12, 18, 24].map((hour) => (
          <g key={hour}><line className="overview-chart-gridline" x1={28 + hour * 14.5} x2={28 + hour * 14.5} y1="20" y2="141" /><text x={28 + hour * 14.5} y="165" textAnchor={hour === 0 ? 'start' : hour === 24 ? 'end' : 'middle'}>{String(hour).padStart(2, '0')}:00</text></g>
        ))}
        <line className="overview-chart-baseline" x1="28" x2="376" y1="141" y2="141" />
        {counts.map((count, hour) => count ? <rect className="overview-chart-bar" key={hour} x={30 + hour * 14.5} y={141 - count / max * 120} width="10" height={count / max * 120} rx="3"><title>{String(hour).padStart(2, '0')}:00: {count} alert{count === 1 ? '' : 's'}</title></rect> : null)}
      </svg>
      {today.length === 0 ? (
        <div className="overview-today-empty"><span className="overview-bell-disc"><Bell aria-hidden="true" /></span><h3>No alerts yet today.</h3><p>You're all caught up! We'll show any alerts here as they happen.</p></div>
      ) : <p className="overview-chart-caption">Alerts recorded today, grouped by hour.</p>}
    </div>
  );
}
