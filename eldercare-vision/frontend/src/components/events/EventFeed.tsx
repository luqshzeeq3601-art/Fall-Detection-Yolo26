import type { JSX } from 'react';
import { formatTimestamp } from '../../utils/format.ts';
import type { ConnectionState } from '../../hooks/useEvents.ts';
import { isKnownEventType } from '../../hooks/useEvents.ts';
import type { WsEvent } from '../../api/types.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';

/**
 * P6-006 live event feed over WS /ws/events. Connection state is explicit;
 * unknown additive event types render generically (consumers ignore unknowns).
 */
export function EventFeed({
  connection,
  events,
  onReconnect,
}: {
  connection: ConnectionState;
  events: WsEvent[];
  onReconnect: () => void;
}): JSX.Element {
  if (connection === 'connecting' && events.length === 0) {
    return <LoadingState label="Connecting to event stream…" />;
  }
  return (
    <div>
      <p role="status">
        Event stream: {connection}
        {connection === 'disconnected' ? ' — auto-reconnect paused' : ''}
      </p>
      {connection === 'disconnected' ? (
        <ErrorState message="Event stream disconnected." onRetry={onReconnect} />
      ) : null}
      {events.length === 0 ? (
        <EmptyState title="No events yet" detail="Events appear here as the system emits them." />
      ) : (
        <ul aria-label="Live events" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {[...events].reverse().map((event) => (
            <li key={event.event_id} className="incident-row">
              <div>
                <strong>{event.event_type}</strong>
                {!isKnownEventType(event.event_type) ? (
                  <span className="generated-label">unknown type</span>
                ) : null}
                <div style={{ color: '#5b6575', fontSize: 13 }}>
                  {event.camera_id ?? 'system'} · {formatTimestamp(event.occurred_at)}
                  {event.incident_id ? ` · Incident ${event.incident_id.slice(0, 8)}…` : ''}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
