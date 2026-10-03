import { AlertTriangle, Siren, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi } from '../../api/platform.ts';
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

const ALERT_EVENTS = new Set(['fall.confirmed', 'incident.escalated']);

/**
 * Raises an on-screen alert for every confirmed fall and every escalation (a fall nobody
 * has responded to), plus a sound and a browser notification when enabled in Settings.
 * Anyone can claim an alert with "I'm responding"; every open dashboard then shows who.
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
  const [claiming, setClaiming] = useState<string | null>(null);
  const [claimError, setClaimError] = useState<{ id: string; text: string } | null>(null);
  const settings = data?.settings;

  // Latest response per incident, as broadcast to every dashboard.
  const handledBy = useMemo(() => {
    const map = new Map<string, { action: string; responder: string | null }>();
    for (const event of events.events) {
      if (event.event_type === 'incident.response' && event.incident_id) {
        map.set(event.incident_id, { action: String(event.payload.action ?? ''), responder: typeof event.payload.responder === 'string' ? event.payload.responder : null });
      }
    }
    return map;
  }, [events.events]);

  useEffect(() => {
    const incoming = events.events.filter((event) => ALERT_EVENTS.has(event.event_type));
    if (seen.current === null) {
      seen.current = new Set(incoming.map((event) => event.event_id));
      return;
    }
    const known = seen.current;
    const fresh = incoming.filter((event) => !known.has(event.event_id));
    if (fresh.length === 0) return;
    fresh.forEach((event) => known.add(event.event_id));
    // An escalation replaces the original alert for the same incident.
    setAlerts((previous) => [...fresh, ...previous.filter((item) => !fresh.some((f) => f.incident_id && f.incident_id === item.incident_id))].slice(0, 3));
    if (settings?.alert_sound ?? true) playAlertTone();
    if ((settings?.browser_alerts ?? true) && 'Notification' in window && Notification.permission === 'granted') {
      for (const event of fresh) {
        const escalated = event.event_type === 'incident.escalated';
        new Notification(escalated ? 'No one has responded to a fall' : 'Fall detected', {
          body: `${cameraName(event.camera_id)} · open ElderCare Vision to respond.`,
          tag: event.incident_id ?? event.event_id,
          requireInteraction: escalated,
        });
      }
    }
  }, [events.events, settings, cameraName]);

  async function claim(incidentId: string): Promise<void> {
    setClaiming(incidentId);
    setClaimError(null);
    try { await incidentApi.respond(incidentId, { action: 'responding' }); } catch (reason) { setClaimError({ id: incidentId, text: reason instanceof Error ? reason.message : 'Not saved. Try again.' }); } finally { setClaiming(null); }
  }
  const dismiss = (alert: WsEvent): void => setAlerts((list) => list.filter((item) => item !== alert));

  if (alerts.length === 0) return null;
  return (
    <div className="fall-alerts" role="alert" aria-live="assertive">
      {alerts.map((alert) => {
        const escalated = alert.event_type === 'incident.escalated';
        const handled = alert.incident_id ? handledBy.get(alert.incident_id) : undefined;
        return (
          <div className={`fall-alert${escalated ? ' is-escalated' : ''}`} key={alert.event_id}>
            {escalated ? <Siren aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
            <div>
              <strong>{escalated ? 'No one has responded' : 'Fall detected'} · {cameraName(alert.camera_id)}</strong>
              <span>
                {new Date(alert.occurred_at).toLocaleTimeString()}
                {typeof alert.payload.fall_score === 'number' ? ` · score ${alert.payload.fall_score.toFixed(2)}` : ''}
              </span>
              {handled ? (
                <span className="fall-alert-handled">{handled.action === 'resolved' ? `Resolved by ${handled.responder ?? 'a colleague'}` : `${handled.responder ?? 'A colleague'} is responding`}</span>
              ) : alert.incident_id ? (
                <button type="button" className="btn btn-primary btn-sm" disabled={claiming === alert.incident_id} onClick={() => void claim(alert.incident_id as string)}>
                  {claiming === alert.incident_id ? 'Saving…' : "I'm responding"}
                </button>
              ) : null}
              {claimError && claimError.id === alert.incident_id ? <span className="fall-alert-error">{claimError.text}</span> : null}
              {alert.incident_id ? (
                <Link to={`/app/incidents?selected=${encodeURIComponent(alert.incident_id)}`} onClick={() => dismiss(alert)}>
                  Open incident →
                </Link>
              ) : <span>Incident could not be saved; check server logs.</span>}
            </div>
            <button type="button" className="icon-button" aria-label="Dismiss fall alert" onClick={() => dismiss(alert)}>
              <X aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
