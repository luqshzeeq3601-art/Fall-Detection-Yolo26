import {
  Check,
  Cpu,
  Gauge,
  HardDrive,
  Zap,
} from 'lucide-react';
import type { JSX } from 'react';
import { BENCHMARK } from '../../api/benchmarkData.ts';

/**
 * KPI card matching reference: Icon, Label, Big Value, Description,
 * and a smooth SVG Sparkline with trend percentage indicator on the right.
 */
export function KpiCard({
  tone,
  icon,
  label,
  value,
  description,
  trend,
  trendDir,
  comparisonLabel = 'vs V6.2',
  accessibleLabel,
}: {
  tone: 'blue' | 'green' | 'violet';
  icon: JSX.Element;
  label: string;
  value: string;
  description: string;
  trend: string;
  trendDir: 'up' | 'down';
  comparisonLabel?: string;
  accessibleLabel: string;
}): JSX.Element {
  return (
    <article className={`bm-ref-kpi bm-ref-kpi-${tone}`} role="region" aria-label={label}>
      <div className="bm-ref-kpi-main">
        <div className="bm-ref-kpi-header">
          <span className="bm-ref-kpi-icon" aria-hidden="true">
            {icon}
          </span>
          <span className="bm-ref-kpi-label">{label}</span>
        </div>
        <strong className="bm-ref-kpi-value">{value}</strong>
        <span className="bm-ref-kpi-desc">{description}</span>
      </div>

      <div className="bm-ref-kpi-spark-wrap" role="img" aria-label={accessibleLabel}>
        {tone === 'blue' && (
          <svg viewBox="0 0 110 38" className="bm-ref-sparkline" aria-hidden="true">
            <defs>
              <linearGradient id="bmBlueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <path
              d="M 0 28 Q 22 34 44 22 T 84 10 T 110 6 L 110 38 L 0 38 Z"
              fill="url(#bmBlueGrad)"
            />
            <path
              d="M 0 28 Q 22 34 44 22 T 84 10 T 110 6"
              fill="none"
              stroke="#3B82F6"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        )}

        {tone === 'green' && (
          <svg viewBox="0 0 110 38" className="bm-ref-sparkline" aria-hidden="true">
            <defs>
              <linearGradient id="bmGreenGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10B981" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <path
              d="M 0 32 Q 28 30 56 18 T 92 12 T 110 4 L 110 38 L 0 38 Z"
              fill="url(#bmGreenGrad)"
            />
            <path
              d="M 0 32 Q 28 30 56 18 T 92 12 T 110 4"
              fill="none"
              stroke="#10B981"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        )}

        {tone === 'violet' && (
          <svg viewBox="0 0 110 38" className="bm-ref-sparkline" aria-hidden="true">
            <defs>
              <linearGradient id="bmVioletGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <path
              d="M 0 26 Q 20 16 42 26 T 78 20 T 96 6 T 110 10 L 110 38 L 0 38 Z"
              fill="url(#bmVioletGrad)"
            />
            <path
              d="M 0 26 Q 20 16 42 26 T 78 20 T 96 6 T 110 10"
              fill="none"
              stroke="#8B5CF6"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        )}

        <div className="bm-ref-trend">
          <span className={`bm-ref-trend-delta bm-ref-trend-${trendDir}`}>
            {trendDir === 'up' ? '▲' : '▼'} {trend}
          </span>
          <span className="bm-ref-trend-vs">{comparisonLabel}</span>
        </div>
      </div>
    </article>
  );
}

/** 2x2 Confusion Matrix matching image reference exactly */
export function ConfusionMatrix(): JSX.Element {
  return (
    <div className="bm-cm-wrapper" aria-label="Confusion matrix of test recordings">
      <div className="bm-cm-col-title">Predicted</div>
      <div className="bm-cm-table-layout">
        <div className="bm-cm-row-title">
          <span>Actual</span>
        </div>
        <div className="bm-cm-grid-area">
          <div className="bm-cm-headers">
            <span>Fall</span>
            <span>No Fall</span>
          </div>
          <div className="bm-cm-row">
            <span className="bm-cm-row-label">Fall</span>
            <div className="bm-cm-cell bm-cm-cell-active">
              <strong className="bm-cm-pct">98.3%</strong>
              <small className="bm-cm-tag">(TP)</small>
            </div>
            <div className="bm-cm-cell bm-cm-cell-light">
              <strong className="bm-cm-pct">1.7%</strong>
              <small className="bm-cm-tag">(FN)</small>
            </div>
          </div>
          <div className="bm-cm-row">
            <span className="bm-cm-row-label">No Fall</span>
            <div className="bm-cm-cell bm-cm-cell-light">
              <strong className="bm-cm-pct">3.3%</strong>
              <small className="bm-cm-tag">(FP)</small>
            </div>
            <div className="bm-cm-cell bm-cm-cell-active">
              <strong className="bm-cm-pct">96.7%</strong>
              <small className="bm-cm-tag">(TN)</small>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Precision-Recall Curve chart matching image reference */
export function PrecisionRecallCurve(): JSX.Element {
  // Chart dimensions: W: 380, H: 210, Plot: x: 38..360, y: 15..175
  return (
    <div className="bm-pr-chart-wrap" aria-label="Precision-Recall Curve">
      <svg viewBox="0 0 380 200" className="bm-pr-svg" role="img">
        <defs>
          <linearGradient id="prAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563EB" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#2563EB" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Y Axis label */}
        <text x="12" y="105" className="bm-pr-axis-label" transform="rotate(-90 12 105)" textAnchor="middle">
          Precision
        </text>

        {/* Y Ticks & Gridlines */}
        {[
          { label: '1.0', y: 20 },
          { label: '0.8', y: 52 },
          { label: '0.6', y: 84 },
          { label: '0.4', y: 116 },
          { label: '0.2', y: 148 },
          { label: '0.0', y: 180 },
        ].map((t) => (
          <g key={t.label}>
            <text x="32" y={t.y + 4} textAnchor="end" className="bm-pr-tick">
              {t.label}
            </text>
            <line x1="38" x2="365" y1={t.y} y2={t.y} className="bm-pr-gridline" />
          </g>
        ))}

        {/* X Ticks */}
        {[
          { label: '0.0', x: 38 },
          { label: '0.2', x: 103 },
          { label: '0.4', x: 168 },
          { label: '0.6', x: 233 },
          { label: '0.8', x: 299 },
          { label: '1.0', x: 364 },
        ].map((t) => (
          <text key={t.label} x={t.x} y="194" textAnchor="middle" className="bm-pr-tick">
            {t.label}
          </text>
        ))}

        {/* X Axis label */}
        <text x="201" y="206" className="bm-pr-axis-label" textAnchor="middle">
          Recall
        </text>

        {/* PR Curve Area */}
        <path
          d="M 38 20
             L 90 21
             Q 150 22 210 24
             T 300 27
             T 345 32
             T 358 35
             L 364 85
             L 364 180
             L 38 180 Z"
          fill="url(#prAreaGrad)"
        />

        {/* PR Curve Line */}
        <path
          d="M 38 20
             L 90 21
             Q 150 22 210 24
             T 300 27
             T 345 32
             T 358 35
             L 364 85"
          fill="none"
          stroke="#2563EB"
          strokeWidth="2.5"
          strokeLinecap="round"
        />

        {/* Curve Points */}
        {[
          { cx: 38, cy: 20 },
          { cx: 90, cy: 21 },
          { cx: 150, cy: 22 },
          { cx: 210, cy: 24 },
          { cx: 270, cy: 26 },
          { cx: 320, cy: 29 },
          { cx: 345, cy: 32 },
          { cx: 358, cy: 35 },
          { cx: 364, cy: 85 },
        ].map((pt, i) => (
          <circle key={i} cx={pt.cx} cy={pt.cy} r="3" fill="#2563EB" />
        ))}

        {/* Tooltip marker & callout */}
        <g className="bm-pr-tooltip-callout">
          <circle cx="358" cy="35" r="4.5" fill="#2563EB" stroke="#ffffff" strokeWidth="2" />
          <line x1="358" y1="35" x2="350" y2="28" stroke="#93C5FD" strokeWidth="1" />
          <rect
            x="248"
            y="6"
            width="100"
            height="32"
            rx="6"
            fill="#ffffff"
            stroke="#BFDBFE"
            strokeWidth="1"
            className="bm-pr-tooltip-box"
          />
          <text x="256" y="19" className="bm-pr-tt-line">
            Recall: 98.3%
          </text>
          <text x="256" y="31" className="bm-pr-tt-line">
            Precision: 96.7%
          </text>
        </g>
      </svg>

      <div className="bm-pr-legend">
        <span className="bm-legend-item">
          <i className="bm-dot-blue" aria-hidden="true" />
          V6.3 (UP-Fall Test-B)
        </span>
        <span className="bm-legend-item">
          <i className="bm-dot-gray" aria-hidden="true" />
          V6.2 (Previous)
        </span>
      </div>
    </div>
  );
}

/** Model Version Comparison bars matching reference */
export function VersionComparisonBars(): JSX.Element {
  const rows = [
    {
      label: 'Recall',
      v63Width: 98.3,
      v63Val: '98.3%',
      v62Width: 97.5,
      v62Val: '97.5%',
    },
    {
      label: 'Precision',
      v63Width: 96.7,
      v63Val: '96.7%',
      v62Width: 95.6,
      v62Val: '95.6%',
    },
    {
      label: 'p95 Time-to-Alert (s)',
      v63Width: 42,
      v63Val: '1.58',
      v62Width: 52,
      v62Val: '1.90',
    },
    {
      label: 'False alerts / hour',
      v63Width: 32,
      v63Val: '0.6',
      v62Width: 44,
      v62Val: '0.8',
    },
  ];

  return (
    <div className="bm-comp-bars-wrap" aria-label="Model Version Comparison">
      <div className="bm-comp-legend">
        <span className="bm-legend-item">
          <i className="bm-dot-blue" aria-hidden="true" />
          V6.3 (UP-Fall Test-B)
        </span>
        <span className="bm-legend-item">
          <i className="bm-dot-gray" aria-hidden="true" />
          V6.2
        </span>
      </div>

      <div className="bm-comp-list">
        {rows.map((r) => (
          <div className="bm-comp-row" key={r.label}>
            <div className="bm-comp-label">{r.label}</div>
            <div className="bm-comp-data">
              <div className="bm-comp-bar-pair">
                {/* V6.3 Bar */}
                <div className="bm-comp-bar-line">
                  <div className="bm-comp-track">
                    <span
                      className="bm-comp-fill bm-comp-fill-blue"
                      style={{ width: `${r.v63Width}%` }}
                    />
                  </div>
                  <strong className="bm-comp-num bm-comp-num-blue">{r.v63Val}</strong>
                </div>

                {/* V6.2 Bar */}
                <div className="bm-comp-bar-line">
                  <div className="bm-comp-track">
                    <span
                      className="bm-comp-fill bm-comp-fill-gray"
                      style={{ width: `${r.v62Width}%` }}
                    />
                  </div>
                  <span className="bm-comp-num bm-comp-num-gray">{r.v62Val}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 5 Additional Metrics stat tiles */
export function AdditionalMetricsTiles(): JSX.Element {
  const metrics = [
    {
      label: 'False alerts / hour',
      value: '0.6',
      icon: <Gauge className="w-5 h-5 text-red-500" />,
      tone: 'red',
    },
    {
      label: 'Inference latency',
      value: '32 ms',
      icon: <Zap className="w-5 h-5 text-sky-500" />,
      tone: 'cyan',
    },
    {
      label: 'FPS',
      value: '28',
      icon: <Gauge className="w-5 h-5 text-blue-600" />,
      tone: 'blue',
    },
    {
      label: 'GPU utilization',
      value: '62 %',
      icon: <Cpu className="w-5 h-5 text-blue-600" />,
      tone: 'blue',
    },
    {
      label: 'CPU / RAM usage',
      value: '28% / 5.1 GB',
      icon: <HardDrive className="w-5 h-5 text-blue-600" />,
      tone: 'blue',
    },
  ];

  return (
    <div className="bm-add-metrics-grid" aria-label="Additional Metrics">
      {metrics.map((m) => (
        <div key={m.label} className="bm-add-metric-tile">
          <div className={`bm-add-icon-circle bm-add-icon-${m.tone}`} aria-hidden="true">
            {m.icon}
          </div>
          <span className="bm-add-metric-label">{m.label}</span>
          <strong className="bm-add-metric-value">{m.value}</strong>
        </div>
      ))}
    </div>
  );
}

/** 4-row Test Dataset card table */
export function TestDatasetTable(): JSX.Element {
  const rows = [
    { label: 'Dataset', value: 'UP-Fall Test-B' },
    { label: 'Model version', value: 'V6.3 (Frozen)' },
    { label: 'Test split', value: 'Sealed' },
    { label: 'Evaluation date', value: 'Oct 1, 2026 – Oct 7, 2026' },
  ];

  return (
    <dl className="bm-dataset-dl" aria-label="Test Dataset Information">
      {rows.map((r) => (
        <div key={r.label} className="bm-dataset-row">
          <dt>{r.label}</dt>
          <dd>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * GateRange component retained for accessibility checks & confidence interval visualizer
 */
export function GateRange({
  min,
  max,
  value,
  interval,
  gate,
  unit,
  higherIsBetter = true,
  label,
}: {
  min: number;
  max: number;
  value: number;
  interval?: readonly [number, number];
  gate: number;
  unit: string;
  higherIsBetter?: boolean;
  label: string;
}): JSX.Element {
  const pos = (v: number): number => ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * 100;
  const passed = higherIsBetter ? value >= gate : value <= gate;
  return (
    <div className="gate-range" role="img" aria-label={label}>
      <div className="gate-range-track">
        <span
          className={`gate-range-zone${higherIsBetter ? ' is-right' : ''}`}
          style={higherIsBetter ? { left: `${pos(gate)}%`, right: 0 } : { left: 0, width: `${pos(gate)}%` }}
        />
        {interval ? (
          <span
            className="gate-range-ci"
            style={{ left: `${pos(interval[0])}%`, width: `${pos(interval[1]) - pos(interval[0])}%` }}
          />
        ) : null}
        <span className="gate-range-gate" style={{ left: `${pos(gate)}%` }} />
        <span className="gate-range-value" style={{ left: `${pos(value)}%` }} />
      </div>
      <div className="gate-range-scale">
        <span>
          {min}
          {unit}
        </span>
        <span className={`gate-pill${passed ? ' is-pass' : ''}`}>
          {passed ? <Check aria-hidden="true" /> : null}Gate {higherIsBetter ? '≥' : '≤'} {gate}
          {unit}
        </span>
        <span>
          {max}
          {unit}
        </span>
      </div>
    </div>
  );
}

const W = 480;
const H = 220;
const PAD = 20;
const AXIS_Y = 176;
const MAX_S = 4;
const R = 5.5;

/**
 * Every detected fall plotted at its time from fall onset to alert (59 dots)
 * Styled as an interactive clinical response-time beeswarm histogram.
 */
export function AlertTimeline(): JSX.Element {
  const values = [...BENCHMARK.timeToAlert].sort((a, b) => a - b);
  const x = (s: number): number => PAD + (s / MAX_S) * (W - 2 * PAD);
  const stacks = new Map<number, number>();
  const dots = values.map((s) => {
    const bin = Math.round(s / 0.1);
    const level = stacks.get(bin) ?? 0;
    stacks.set(bin, level + 1);
    return { s, cx: x(bin * 0.1), cy: AXIS_Y - 12 - level * (R * 2 + 1.5) };
  });
  const slowest = values[values.length - 1];

  return (
    <figure className="alert-timeline">
      {/* Top summary chips */}
      <div className="bm-timeline-stat-chips" aria-hidden="true">
        <span className="bm-stat-chip chip-median">
          <small>Median</small>
          <strong>{BENCHMARK.medianSeconds.toFixed(2)} s</strong>
        </span>
        <span className="bm-stat-chip chip-p90">
          <small>p90</small>
          <strong>{BENCHMARK.p90Seconds.toFixed(2)} s</strong>
        </span>
        <span className="bm-stat-chip chip-p95">
          <small>p95 Alert</small>
          <strong>{BENCHMARK.p95Seconds.toFixed(2)} s</strong>
          <em>Gate ≤ 3.0s Passed</em>
        </span>
        <span className="bm-stat-chip chip-outlier">
          <small>Slowest</small>
          <strong>{slowest.toFixed(2)} s</strong>
          <em>1 Outlier</em>
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${values.length} detected falls by time to alert. Median ${BENCHMARK.medianSeconds} seconds, 95th percentile ${BENCHMARK.p95Seconds} seconds, slowest ${slowest.toFixed(2)} seconds.`}
      >
        <defs>
          <linearGradient id="gateZoneGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#EF4444" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#EF4444" stopOpacity="0.02" />
          </linearGradient>
          <filter id="dotShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1" stdDeviation="1" floodColor="#0F172A" floodOpacity="0.18" />
          </filter>
        </defs>

        {/* Clinical Over-Gate Warning Zone (> 3.0s) */}
        <rect
          x={x(BENCHMARK.gates.maxP95Seconds)}
          y={10}
          width={x(MAX_S) - x(BENCHMARK.gates.maxP95Seconds)}
          height={AXIS_Y - 10}
          fill="url(#gateZoneGrad)"
          className="tl-over-gate"
        />

        {/* Soft horizontal grid lines */}
        {[0, 40, 80, 120, 160].map((y) => (
          <line key={y} x1={PAD} x2={W - PAD} y1={y} y2={y} stroke="#F1F5F9" strokeWidth="1" />
        ))}

        {/* Reference Threshold Lines */}
        {/* Median line (0.85s) */}
        <line x1={x(BENCHMARK.medianSeconds)} x2={x(BENCHMARK.medianSeconds)} y1={28} y2={AXIS_Y} className="tl-median" stroke="#0F172A" strokeWidth="1.5" />
        <rect x={x(BENCHMARK.medianSeconds) - 40} y={10} width="80" height="18" rx="4" fill="#0F172A" />
        <text x={x(BENCHMARK.medianSeconds)} y={23} textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="700" className="tl-label tl-median">
          median 0.85 s
        </text>

        {/* p95 line (1.58s) */}
        <line x1={x(BENCHMARK.p95Seconds)} x2={x(BENCHMARK.p95Seconds)} y1={30} y2={AXIS_Y} className="tl-p95" stroke="#4338CA" strokeWidth="1.5" strokeDasharray="4 3" />
        <rect x={x(BENCHMARK.p95Seconds) - 34} y={12} width="68" height="18" rx="4" fill="#4338CA" />
        <text x={x(BENCHMARK.p95Seconds)} y={25} textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="700" className="tl-label tl-p95">
          p95 1.58 s
        </text>

        {/* Gate line (3.0s) */}
        <line x1={x(BENCHMARK.gates.maxP95Seconds)} x2={x(BENCHMARK.gates.maxP95Seconds)} y1={30} y2={AXIS_Y} className="tl-gate" stroke="#DC2626" strokeWidth="2" strokeDasharray="5 3" />
        <rect x={x(BENCHMARK.gates.maxP95Seconds) - 30} y={12} width="60" height="18" rx="4" fill="#DC2626" />
        <text x={x(BENCHMARK.gates.maxP95Seconds)} y={25} textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="700" className="tl-label tl-gate">
          gate 3 s
        </text>

        {/* Detected Fall Data Points (59 dots) */}
        {dots.map((d, i) => {
          const isSlow = d.s > BENCHMARK.gates.maxP95Seconds;
          return (
            <circle
              key={i}
              cx={d.cx}
              cy={d.cy}
              r={R}
              filter="url(#dotShadow)"
              className={isSlow ? 'tl-dot tl-dot-slow' : 'tl-dot'}
              fill={isSlow ? '#EA580C' : '#2563EB'}
              stroke="#FFFFFF"
              strokeWidth="1.5"
            >
              <title>{`Fall alert: ${d.s.toFixed(2)} seconds`}</title>
            </circle>
          );
        })}

        {/* X Axis & Ticks */}
        <line x1={PAD} x2={W - PAD} y1={AXIS_Y} y2={AXIS_Y} className="tl-axis" stroke="#94A3B8" strokeWidth="1.5" />
        {[0, 1, 2, 3, 4].map((s) => (
          <g key={s}>
            <line x1={x(s)} x2={x(s)} y1={AXIS_Y} y2={AXIS_Y + 5} stroke="#94A3B8" strokeWidth="1.5" />
            <text key={s} x={x(s)} y={AXIS_Y + 20} textAnchor="middle" className="tl-tick" fill="#64748B" fontSize="11" fontWeight="600">
              {s} s
            </text>
          </g>
        ))}
      </svg>
      <figcaption>
        Each dot is one detected fall ({values.length} of {BENCHMARK.fallClips} test clips). 95% of alerts landed within 1.58 s, easily beating the 3.0 s gate. One slow recovery at 3.70 s is the single outlier.
      </figcaption>
    </figure>
  );
}

/** One cell per test clip, grouped by activity with sleek clinical progress segments */
export function ActivityGrid(): JSX.Element {
  return (
    <div className="activity-grid">
      {(['fall', 'adl'] as const).map((group) => {
        const isFall = group === 'fall';
        const items = BENCHMARK.activities.filter((a) => a.fall === isFall);
        const totalCorrect = items.reduce((sum, a) => sum + a.correct, 0);
        const totalClips = items.reduce((sum, a) => sum + a.total, 0);
        const pct = ((totalCorrect / totalClips) * 100).toFixed(1);

        return (
          <div key={group} className={`activity-group activity-group-${group}`}>
            <div className="activity-group-header">
              <div>
                <span className="activity-group-title">
                  {isFall ? 'Falls · Alert Expected' : 'Everyday Activities (ADL) · Silence Expected'}
                </span>
                <span className="activity-group-subtitle">
                  {isFall ? 'Target ≥ 90% recall' : 'Target ≤ 0.05/h false alarms'}
                </span>
              </div>
              <span className={`activity-group-badge ${isFall ? 'badge-blue' : 'badge-teal'}`}>
                {totalCorrect}/{totalClips} ({pct}%)
              </span>
            </div>

            <ul className="activity-list">
              {items.map((a) => {
                const hasMiss = a.correct < a.total;
                return (
                  <li
                    key={a.name}
                    aria-label={`${a.name}: ${a.correct} of ${a.total} correct`}
                    className={`activity-item${hasMiss ? ' has-miss-item' : ''}`}
                  >
                    <span className="activity-name">{a.name}</span>
                    <div className="activity-cells" aria-hidden="true">
                      {Array.from({ length: a.total }, (_, i) => {
                        const ok = i < a.correct;
                        return (
                          <span
                            key={i}
                            className={`activity-segment ${
                              ok ? (isFall ? 'ok-fall' : 'ok-adl') : (isFall ? 'miss-fall' : 'miss-adl')
                            }`}
                            title={ok ? 'Pass' : 'Error'}
                          />
                        );
                      })}
                    </div>
                    <span className={`activity-score${hasMiss ? ' has-miss' : ' is-perfect'}`}>
                      {!hasMiss && <Check className="score-check-icon" aria-hidden="true" />}
                      {a.correct}/{a.total}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
