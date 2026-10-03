import type { JSX } from 'react';
import type { FallDetection } from '../../api/platform.ts';

const W = 640;
const H = 150;
const PAD_L = 34;
const PAD_R = 8;
const PAD_T = 10;
const PAD_B = 22;

/**
 * Fall-likelihood trace for the current run: the detector's estimate over the last
 * minute of video, the trigger threshold, and a marker where each fall was confirmed.
 */
export function LikelihoodTrace({ trace, detections, threshold }: { trace: [number, number][]; detections: FallDetection[]; threshold: number }): JSX.Element {
  if (trace.length < 2) {
    return <p className="helper">The trace appears once the detector has processed a few frames.</p>;
  }
  const t0 = trace[0][0];
  const t1 = Math.max(trace[trace.length - 1][0], t0 + 1);
  const x = (t: number): number => PAD_L + ((t - t0) / (t1 - t0)) * (W - PAD_L - PAD_R);
  const y = (v: number): number => PAD_T + (1 - Math.max(0, Math.min(1, v))) * (H - PAD_T - PAD_B);
  const line = trace.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${x(t0).toFixed(1)},${y(0)} ${line} ${x(trace[trace.length - 1][0]).toFixed(1)},${y(0)}`;
  const visible = detections.filter((d) => d.video_time >= t0 && d.video_time <= t1);
  const peak = Math.max(...trace.map(([, v]) => v));
  const ticks = [t0, (t0 + t1) / 2, t1];
  return (
    <figure className="likelihood-trace">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Fall likelihood over ${(t1 - t0).toFixed(0)} seconds, peak ${Math.round(peak * 100)} percent, ${visible.length} confirmed fall${visible.length === 1 ? '' : 's'}`}>
        <defs>
          <linearGradient id="trace-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--tone-blue-467)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--tone-blue-467)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <rect x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={y(threshold) - PAD_T} className="trace-danger-zone" />
        {[0, 0.5, 1].map((v) => <g key={v}><line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} className="chart-grid" /><text x="2" y={y(v) + 4} className="trace-axis">{Math.round(v * 100)}%</text></g>)}
        <line x1={PAD_L} x2={W - PAD_R} y1={y(threshold)} y2={y(threshold)} className="trace-threshold" />
        <text x={W - PAD_R - 4} y={y(threshold) - 5} textAnchor="end" className="trace-threshold-label">trigger {threshold.toFixed(2)}</text>
        <polygon points={area} fill="url(#trace-fill)" />
        <polyline points={line} fill="none" className="trace-line" />
        {visible.map((d) => (
          <g key={`${d.video_time}-${d.track_id}`}>
            <line x1={x(d.video_time)} x2={x(d.video_time)} y1={PAD_T} y2={H - PAD_B} className="trace-fall-line" />
            <circle cx={x(d.video_time)} cy={PAD_T + 6} r="5" className="trace-fall-dot" />
          </g>
        ))}
        {ticks.map((t, i) => <text key={i} x={x(t)} y={H - 5} textAnchor={i === 0 ? 'start' : i === 2 ? 'end' : 'middle'} className="trace-axis">{t.toFixed(1)} s</text>)}
      </svg>
      <figcaption><span><i className="legend-line" />Fall likelihood</span><span><i className="legend-threshold" />Trigger threshold</span><span><i className="legend-fall" />Fall confirmed</span></figcaption>
    </figure>
  );
}
