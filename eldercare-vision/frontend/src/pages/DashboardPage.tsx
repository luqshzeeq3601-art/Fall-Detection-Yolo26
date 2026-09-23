import { useSystemStatus } from '../hooks/useDashboard.ts';
import { useState, type JSX } from 'react';
import { formatLatency } from '../utils/format.ts';
import { ErrorState, LoadingState } from '../components/common/States.tsx';
import { CameraList } from '../components/cameras/CameraList.tsx';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';
import { IncidentList } from '../components/incidents/IncidentList.tsx';

function SystemSection(): JSX.Element {
  const { data, loading, error, reload } = useSystemStatus();
  if (loading) return <LoadingState label="Loading system status…" />;
  if (error || !data) return <ErrorState message={error ?? 'System status unavailable'} onRetry={reload} />;
  return (
    <dl className="kv">
      <dt>Model</dt>
      <dd>{data.model_name}</dd>
      <dt>Config</dt>
      <dd>{data.config_version}</dd>
      <dt>Vision</dt>
      <dd>{data.vision_fps.toFixed(1)} fps</dd>
      <dt>Inference latency</dt>
      <dd>{formatLatency(data.inference_latency_ms.avg, data.inference_latency_ms.p95)}</dd>
      <dt>Device</dt>
      <dd>{data.gpu_summary.name}</dd>
      <dt>Cameras</dt>
      <dd>{String(data.camera_count)}</dd>
    </dl>
  );
}

/**
 * Dashboard composition. Camera health is owned by P6-002 CameraList,
 * incident queue by P6-003 IncidentList. Detail/evidence (P6-004),
 * review (P6-005), live events (P6-006), and telemetry (P6-007) mount below.
 */
export function DashboardPage(): JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <main>
      <div className="grid-two">
        <section aria-labelledby="sys-heading" className="panel">
          <h2 id="sys-heading">System</h2>
          <SystemSection />
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
    </main>
  );
}
