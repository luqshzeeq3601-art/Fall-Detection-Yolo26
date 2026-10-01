import type { JSX } from 'react';
import { useSystemStatus } from '../../hooks/useDashboard.ts';
import { formatFps, formatLatency } from '../../utils/format.ts';
import { ErrorState, LoadingState } from '../common/States.tsx';

function memoryText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)} MB`;
}

/**
 * P6-007 telemetry panel over GET /system/status. Renders only
 * transported fields — no derived claims, no decorative charts.
 */
export function TelemetryPanel(): JSX.Element {
  const { data, loading, error, reload } = useSystemStatus();
  if (loading) return <LoadingState label="Loading telemetry…" />;
  if (error || !data)
    return <ErrorState message={error ?? 'Telemetry unavailable'} onRetry={reload} />;
  return (
    <dl className="kv">
      <dt>Service version</dt>
      <dd>{data.version}</dd>
      <dt>Model</dt>
      <dd>
        {data.model_name} ({data.model_version})
      </dd>
      <dt>Config</dt>
      <dd>{data.config_version}</dd>
      <dt>Cameras</dt>
      <dd>{String(data.camera_count)}</dd>
      <dt>Vision throughput</dt>
      <dd>{formatFps(data.vision_fps)}</dd>
      <dt>Inference latency</dt>
      <dd>{formatLatency(data.inference_latency_ms.avg, data.inference_latency_ms.p95)}</dd>
      <dt>Compute device</dt>
      <dd>
        {data.gpu_summary.name} ({data.gpu_summary.device})
      </dd>
      <dt>Memory used</dt>
      <dd>{memoryText(data.gpu_summary.memory_allocated_mb)}</dd>
      <dt>Memory total</dt>
      <dd>{memoryText(data.gpu_summary.memory_total_mb)}</dd>
      {Object.entries(data.integrations).map(([name, state]) => (
        <div key={name} style={{ display: 'contents' }}>
          <dt>{name}</dt>
          <dd>{state}</dd>
        </div>
      ))}
    </dl>
  );
}
