import { useState, type JSX } from 'react';
import type { EventsBundle } from '../hooks/useEvents.ts';
import { CameraList } from '../components/cameras/CameraList.tsx';
import { EventFeed } from '../components/events/EventFeed.tsx';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';
import { IncidentList } from '../components/incidents/IncidentList.tsx';
import { TelemetryPanel } from '../components/system/TelemetryPanel.tsx';

/**
 * Dashboard composition: telemetry (P6-007), cameras (P6-002),
 * incident queue (P6-003), detail/evidence (P6-004), review (P6-005),
 * live events (P6-006). Browser/a11y hardening in P6-008.
 */
export function DashboardPage({ events }: { events: EventsBundle }): JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <main>
      <div className="grid-two">
        <section aria-labelledby="sys-heading" className="panel">
          <h2 id="sys-heading">System telemetry</h2>
          <TelemetryPanel />
        </section>
        <section aria-labelledby="cam-heading" className="panel">
          <h2 id="cam-heading">Cameras</h2>
          <CameraList />
        </section>
      </div>
      <section aria-labelledby="inc-heading" className="panel">
        <h2 id="inc-heading">Incidents</h2>
        <IncidentList selectedId={selectedId} onSelect={setSelectedId} />
      </section>
      <section aria-labelledby="detail-heading" className="panel">
        <h2 id="detail-heading">Incident detail</h2>
        <IncidentDetailPanel selectedId={selectedId} />
      </section>
      <section aria-labelledby="events-heading" className="panel">
        <h2 id="events-heading">Live events</h2>
        <EventFeed
          connection={events.connection}
          events={events.events}
          onReconnect={events.reconnect}
        />
      </section>
    </main>
  );
}
