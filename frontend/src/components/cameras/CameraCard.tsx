import type { JSX } from 'react';
import type { Camera } from '../../api/types.ts';
import { formatTimestamp } from '../../utils/format.ts';
import { cameraStatusMeta } from '../../utils/status.ts';

export function CameraCard({ camera }: { camera: Camera }): JSX.Element {
  const meta = cameraStatusMeta(camera.status);
  return (
    <li className="camera-row">
      <div>
        <strong>{camera.name}</strong>
        <div style={{ color: '#5b6575', fontSize: 13 }}>
          {camera.id} · Last frame {formatTimestamp(camera.last_frame_at)} · Last heartbeat{' '}
          {formatTimestamp(camera.last_heartbeat_at)} · Reconnects {camera.reconnect_count}
        </div>
      </div>
      <span
        className={`status status-${meta.tone}`}
        title={meta.description}
        aria-label={`Camera ${camera.name} status: ${meta.label}. ${meta.description}`}
      >
        <span aria-hidden="true">{meta.symbol}</span> {meta.label}
      </span>
    </li>
  );
}
