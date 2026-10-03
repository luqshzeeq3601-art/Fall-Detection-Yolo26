import { Activity, Camera, Cpu, Database, Gauge, HeartPulse, RefreshCw, Server, Sparkles, Wifi, Zap } from 'lucide-react';
import { useEffect, useState, type JSX } from 'react';
import { Link } from 'react-router-dom';
import { telemetryApi, type TelemetrySample } from '../api/platform.ts';
import { RingGauge, Sparkline } from '../components/charts/Charts.tsx';
import { Card, PageHeader, StatusPill } from '../components/common/Ui.tsx';
import { EmptyState, ErrorState, LoadingState } from '../components/common/States.tsx';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { cameraStatusMeta } from '../utils/status.ts';
import './EngineeringPages.css';

function useTelemetry(): { current: TelemetrySample | null; history: TelemetrySample[]; error: string | null; retry: () => void } {
  const [state, setState] = useState<{ current: TelemetrySample | null; history: TelemetrySample[]; error: string | null }>({ current: null, history: [], error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = (): void => {
      if (document.visibilityState === 'hidden') return;
      telemetryApi.metrics()
        .then((value) => { if (!cancelled) setState({ current: value.current, history: value.history, error: null }); })
        .catch((reason: unknown) => { if (!cancelled) setState((previous) => ({ ...previous, error: reason instanceof Error ? reason.message : 'Telemetry unavailable.' })); });
    };
    load();
    const timer = window.setInterval(load, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

const SERIES = [
  { key: 'latency_avg_ms', label: 'Average', color: 'var(--tone-blue-467)' },
  { key: 'latency_p95_ms', label: 'Slowest 5%', color: 'var(--tone-violet-422)' },
] as const;

function LatencyChart({ history }: { history: TelemetrySample[] }): JSX.Element {
  const points = history.slice(-60);
  const max = Math.max(50, ...points.flatMap((sample) => SERIES.map((series) => sample[series.key])));
  const ceiling = Math.ceil(max / 50) * 50;
  const x = (i: number): number => 36 + (i * 554) / Math.max(1, points.length - 1);
  const y = (value: number): number => 150 - (value / ceiling) * 140;
  return (
    <div className="latency-lines">
      <div className="latency-legend">{SERIES.map((series) => <span key={series.key}><i style={{ background: series.color }} />{series.label}</span>)}</div>
      <svg viewBox="0 0 600 170" role="img" aria-label="Time per analysed frame over the last two minutes"><title>Milliseconds per analysed frame</title>
        {[0, ceiling / 2, ceiling].map((value) => <g key={value}><line x1="36" x2="590" y1={y(value)} y2={y(value)} className="chart-grid" /><text x="0" y={y(value) + 4}>{Math.round(value)}</text></g>)}
        {SERIES.map((series) => <polyline key={series.key} points={points.map((sample, i) => `${x(i)},${y(sample[series.key])}`).join(' ')} fill="none" stroke={series.color} strokeWidth="2.5" />)}
      </svg>
      <p className="engineering-note">Milliseconds per analysed frame, sampled every 2 s. Flat at zero while nothing runs.</p>
    </div>
  );
}

function Tile({ icon, name, state, detail }: { icon: JSX.Element; name: string; state: string; detail?: string }): JSX.Element {
  const tone = state === 'ready' || state === 'connected' ? 'green' : state === 'disabled' ? 'neutral' : 'amber';
  return <div className="service-tile">{icon}<div><strong>{name}</strong><StatusPill tone={tone}>{state}</StatusPill>{detail ? <small>{detail}</small> : null}</div></div>;
}

export function TelemetryPage(): JSX.Element {
  const { cameras, system, ready, events } = useDashboardContext();
  const telemetry = useTelemetry();
  const now = telemetry.current;
  const series = (key: keyof TelemetrySample): number[] => telemetry.history.map((sample) => Number(sample[key] ?? 0));
  const device = system.data?.gpu_summary;

  return (
    <div className="engineering-page telemetry-page">
      <PageHeader
        eyebrow="SYSTEM"
        title="System health"
        subtitle="Is everything working? Detector speed, computer load, connected services and cameras, measured live on this server."
      >
        <button type="button" className="btn btn-secondary" onClick={() => { system.reload(); ready.reload(); cameras.reload(); }}><RefreshCw aria-hidden="true" />Refresh status</button>
      </PageHeader>

      <Card title="Detector and computer" icon={<Cpu />} action={<StatusPill tone={now?.active_streams ? 'green' : 'neutral'}>{now?.active_streams ? `${now.active_streams} source${now.active_streams === 1 ? '' : 's'} running` : 'Idle'}</StatusPill>}>
        {telemetry.error && !now ? <ErrorState message={telemetry.error} onRetry={telemetry.retry} /> : !now ? <LoadingState label="Measuring…" /> : (
          <div className="telemetry-gauges">
            <div><h3>Frames analysed / s</h3><RingGauge value={Number(now.fps.toFixed(1))} max={30} label={now.active_streams ? 'frames per second' : 'nothing running'} color="var(--blue)" /><Sparkline values={series('fps')} color="var(--blue)" /></div>
            <div><h3>Time per frame</h3><RingGauge value={Math.round(now.latency_avg_ms)} max={Math.max(100, Math.ceil(now.latency_p95_ms / 50) * 50)} label={`slowest 5%: ${now.latency_p95_ms.toFixed(0)} ms`} unit=" ms" color="var(--mint)" /><Sparkline values={series('latency_avg_ms')} color="var(--mint)" /></div>
            <div><h3>Graphics card</h3>{now.gpu_percent !== null ? <><RingGauge value={Math.round(now.gpu_percent)} label={now.gpu_memory_total_mb ? `${((now.gpu_memory_used_mb ?? 0) / 1024).toFixed(1)} / ${(now.gpu_memory_total_mb / 1024).toFixed(1)} GB` : 'NVIDIA'} unit="%" color="var(--violet)" /><Sparkline values={series('gpu_percent')} color="var(--violet)" /></> : <div className="metric-unavailable">No NVIDIA GPU<small>Detection runs on the processor</small></div>}</div>
            <div><h3>Processor</h3><RingGauge value={Math.round(now.cpu_percent)} label="all cores" unit="%" color="var(--blue)" /><Sparkline values={series('cpu_percent')} color="var(--blue)" /></div>
            <div><h3>Memory</h3><RingGauge value={Number(now.memory_used_gb.toFixed(1))} max={now.memory_total_gb} label={`of ${now.memory_total_gb.toFixed(1)} GB`} unit=" GB" color="var(--mint)" /><Sparkline values={series('memory_used_gb')} color="var(--mint)" /></div>
          </div>
        )}
        {device && device.device === 'cpu' && now?.gpu_percent !== null ? <p className="engineering-note">A GPU is present but the installed PyTorch build is CPU-only, so detection runs on the processor. Installing the CUDA build of PyTorch would speed it up.</p> : null}
      </Card>

      <div className="engineering-two">
        <Card title="Services" icon={<Server />}>
          {ready.loading && !ready.data ? <LoadingState label="Checking services…" /> : ready.error ? <ErrorState message={ready.error} onRetry={ready.reload} /> : (
            <div className="service-tiles">
              <Tile icon={<Database size={21} />} name="Database" state={ready.data?.database ?? 'unknown'} detail="Incidents, reviews, accounts" />
              <Tile icon={<HeartPulse size={21} />} name="Fall detector" state={ready.data?.vision_service ?? 'unknown'} detail={system.data ? `${system.data.model_name}` : undefined} />
              <Tile icon={<Activity size={21} />} name="Live updates" state={events.connected ? 'connected' : events.connection} detail="Pushes alerts to open dashboards" />
              <Tile icon={<Sparkles size={21} />} name="AI second opinion" state={ready.data?.vlm ?? 'unknown'} detail={ready.data?.vlm === 'ready' ? 'Describes each incident' : 'Set VLM_PROVIDER on the server to enable'} />
              <Tile icon={<Wifi size={21} />} name="MQTT" state={ready.data?.mqtt ?? 'unknown'} detail="Optional message bus" />
            </div>
          )}
        </Card>
        <Card title="Time per frame" icon={<Zap />}>
          {telemetry.history.length > 1 ? <LatencyChart history={telemetry.history} /> : <EmptyState title="Collecting samples" detail="The chart fills in every 2 seconds." />}
        </Card>
      </div>

      <div className="engineering-two">
        <Card title="Cameras" icon={<Camera />} action={<Link className="card-link" to="/app/settings?tab=cameras">Manage →</Link>}>
          {cameras.loading && !cameras.data ? <LoadingState label="Loading cameras…" /> : cameras.error ? <ErrorState message={cameras.error} onRetry={cameras.reload} /> : cameras.data?.length ? (
            <div className="telemetry-cameras">{cameras.data.map((camera) => { const status = cameraStatusMeta(camera.status); return <div key={camera.id}><Camera size={21} /><strong>{camera.name}</strong><StatusPill tone={status.tone === 'ok' ? 'green' : status.tone === 'bad' ? 'red' : status.tone === 'warn' ? 'amber' : 'neutral'}>{status.label}</StatusPill><small>{camera.reconnect_count} reconnects</small></div>; })}</div>
          ) : <EmptyState title="No cameras yet" detail="They appear after the first start in Live monitor." />}
        </Card>
        <Card title="Software" icon={<Gauge />}>
          {system.loading && !system.data ? <LoadingState label="Loading…" /> : system.error ? <ErrorState message={system.error} onRetry={system.reload} /> : system.data ? (
            <dl className="kv">
              <dt>Models</dt><dd>{system.data.model_name}</dd>
              <dt>Model version</dt><dd>{system.data.model_version} · {system.data.config_version}</dd>
              <dt>Runs on</dt><dd>{system.data.gpu_summary.name} ({system.data.gpu_summary.device})</dd>
              <dt>API version</dt><dd>{system.data.version}</dd>
            </dl>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
