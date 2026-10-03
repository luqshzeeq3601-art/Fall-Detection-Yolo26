import { AlertTriangle, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import type { WsEvent } from '../../api/types.ts';
import { useWorkspaceSettings } from '../../features/settings/useWorkspaceSettings.ts';
import { useDashboardContext } from '../../hooks/useDashboardContext.ts';
import './FallAlerts.css';

function playAlertTone(): void {
  try {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const gain = ctx.createGain();
    gain.gain.value = 0.15;
    gain.connect(ctx.destination);
    [0, 0.28, 0.56].forEach((offset) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = 880;
      osc.connect(gain);
      osc.start(ctx.currentTime + offset);
      osc.stop(ctx.currentTime + offset + 0.18);
    });
    window.setTimeout(() => void ctx.close(), 1200);
  } catch {
    // Audio is best-effort; the on-screen alert always shows.
  }
}

/**
 * Raises an on-screen alert for every new `fall.confirmed` event, plus a sound and a
 * browser notification when enabled in Settings.
 */
export function FallAlerts(): JSX.Element | null {
  const { events, cameras } = useDashboardContext();
  const cameraName = useCallback(
    (id: string | null | undefined): string => cameras.data?.find((camera) => camera.id === id)?.name ?? id ?? 'Unknown camera',
    [cameras.data],
  );
  const { data } = useWorkspaceSettings();
  const seen = useRef<Set<string> | null>(null);
  const [alerts, setAlerts] = useState<WsEvent[]>([]);
  const settings = data?.settings;

  useEffect(() => {
    const falls = events.events.filter((event) => event.event_type === 'fall.confirmed');
    if (seen.current === null) {
      seen.current = new Set(falls.map((event) => event.event_id));
      return;
    }
    const known = seen.current;
    const fresh = falls.filter((event) => !known.has(event.event_id));
    if (fresh.length === 0) return;
    fresh.forEach((event) => known.add(event.event_id));
    setAlerts((previous) => [...fresh, ...previous].slice(0, 3));
    if (settings?.alert_sound ?? true) playAlertTone();
    if ((settings?.browser_alerts ?? true) && 'Notification' in window && Notification.permission === 'granted') {
      for (const event of fresh) {
        new Notification('Fall detected', {
          body: `${cameraName(event.camera_id)} · open ElderCare Vision to review.`,
          tag: event.event_id,
        });
      }
    }
  }, [events.events, settings, cameraName]);

  if (alerts.length === 0) return null;
  return (
    <div className="fall-alerts" role="alert" aria-live="assertive">
      {alerts.map((alert) => (
        <div className="fall-alert" key={alert.event_id}>
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>Fall detected · {cameraName(alert.camera_id)}</strong>
            <span>
              {new Date(alert.occurred_at).toLocaleTimeString()}
              {typeof alert.payload.fall_score === 'number' ? ` · score ${alert.payload.fall_score.toFixed(2)}` : ''}
            </span>
            {alert.incident_id ? (
              <Link to={`/app/incidents?selected=${encodeURIComponent(alert.incident_id)}`} onClick={() => setAlerts((list) => list.filter((item) => item !== alert))}>
                Review incident →
              </Link>
            ) : <span>Incident could not be saved; check server logs.</span>}
          </div>
          <button type="button" className="icon-button" aria-label="Dismiss fall alert" onClick={() => setAlerts((list) => list.filter((item) => item !== alert))}>
            <X aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
