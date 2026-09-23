import { useCameras, useSystemStatus } from '../hooks/useDashboard.ts';
import type { JSX } from 'react';
import { formatLatency, formatTimestamp } from '../utils/format.ts';
import { cameraStatusMeta } from '../utils/status.ts';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';

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

function CameraSection(): JSX.Element {
  const { data, loading, error, reload } = useCameras();
  if (loading) return <LoadingState label="Loading cameras…" />;
  if (error || !data) return <ErrorState message={error ?? 'Cameras unavailable'} onRetry={reload} />;
  if (data.length === 0) return <EmptyState title="No cameras registered" />;
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {data.map((camera) => {
        const meta = cameraStatusMeta(camera.status);
        return (
          <li key={camera.id} className="camera-row">
            <div>
              <strong>{camera.name}</strong>
              <div style={{ color: '#5b6575', fontSize: 13 }}>
                {camera.id} · Last frame {formatTimestamp(camera.last_frame_at)} · Reconnects{' '}
                {camera.reconnect_count}
              </div>
            </div>
            <span className={`status status-${meta.tone}`} title={meta.description}>
              <span aria-hidden="true">{meta.symbol}</span> {meta.label}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * P6-001 foundation page: establishes the dashboard tree.
 * Incident queue, detail, review, live events, and telemetry arrive
 * in P6-003…P6-007 and mount in the sections below.
 */
export function DashboardPage(): JSX.Element {
  return (
    <main>
      <div className="grid-two">
        <section aria-labelledby="sys-heading" className="panel">
          <h2 id="sys-heading">System</h2>
          <SystemSection />
        </section>
        <section aria-labelledby="cam-heading" className="panel">
          <h2 id="cam-heading">Cameras</h2>
          <CameraSection />
        </section>
      </div>
      <section aria-labelledby="inc-heading" className="panel">
        <h2 id="inc-heading">Incidents</h2>
        <EmptyState
          title="Incident queue loads in P6-003"
          detail="Data boundary and mock server are ready; list, detail, and review views mount here."
        />
      </section>
    </main>
  );
}
