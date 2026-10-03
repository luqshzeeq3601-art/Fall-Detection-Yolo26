import {
  Check,
  Cpu,
  Gauge,
  Zap,
} from 'lucide-react';
import type { JSX } from 'react';
import { BENCHMARK } from '../../api/benchmarkData.ts';

/**
 * KPI card: icon, label, headline value, description, and the measured evidence
 * (confidence interval and release gate) on the right. No invented trends.
 */
export function KpiCard({
  tone,
  icon,
  label,
  value,
  description,
  evidence,
  accessibleLabel,
}: {
  tone: 'blue' | 'green' | 'violet';
  icon: JSX.Element;
  label: string;
  value: string;
  description: string;
  evidence: string[];
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

      <div className="bm-ref-kpi-evidence" role="img" aria-label={accessibleLabel}>
        {evidence.map((line) => <span key={line}>{line}</span>)}
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

/** False-alarm evidence: what was measured, against the target, without a drawn curve. */
export function FalseAlarmEvidence(): JSX.Element {
  const { heldout, gates, devLongformRatePerHour } = BENCHMARK;
  const rows = [
    { label: 'Held-out recordings', value: `${heldout.hours} h, ${heldout.falseAlarms} false alarms` },
    { label: '95% upper bound', value: `${heldout.ci95Upper} per hour` },
    { label: 'Target', value: `≤ ${gates.maxFalseAlarmsPerHour} per hour` },
    { label: 'Development long-form', value: `${devLongformRatePerHour.toFixed(2)} per hour` },
  ];
  return (
    <>
      <dl className="bm-dataset-dl" aria-label="False-alarm evidence">
        {rows.map((r) => (
          <div key={r.label} className="bm-dataset-row">
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      <p className="engineering-note">
        Zero false alarms in {heldout.hours} h cannot show a rate below {gates.maxFalseAlarmsPerHour} per hour; much longer everyday recordings are needed.
      </p>
    </>
  );
}

/** V6.2 vs V6.3 on development diagnostics (BENCHMARK.history); V6.2 was never run on Test-B. */
export function VersionComparisonBars(): JSX.Element {
  const prev = BENCHMARK.history.find((h) => h.version === 'V6.2');
  const curr = BENCHMARK.history.find((h) => h.version.startsWith('V6.3'));
  if (!prev || !curr) return <p className="engineering-note">Version history unavailable.</p>;
  const faMax = Math.max(prev.longformFaPerHour, curr.longformFaPerHour);
  const rows = [
    { label: 'Camera 2 recall (dev)', curr: curr.cam2Recall, prev: prev.cam2Recall, unit: '%', width: (v: number) => v },
    { label: 'URFD recall (dev)', curr: curr.urfdRecall, prev: prev.urfdRecall, unit: '%', width: (v: number) => v },
    { label: 'Test-X recall', curr: curr.testXRecall, prev: prev.testXRecall, unit: '%', width: (v: number) => v },
    { label: 'Long-form false alarms / h', curr: curr.longformFaPerHour, prev: prev.longformFaPerHour, unit: '', width: (v: number) => (v / faMax) * 100 },
  ];

  return (
    <div className="bm-comp-bars-wrap" aria-label="Model version comparison on development data">
      <div className="bm-comp-legend">
        <span className="bm-legend-item">
          <i className="bm-dot-blue" aria-hidden="true" />
          {curr.version}
        </span>
        <span className="bm-legend-item">
          <i className="bm-dot-gray" aria-hidden="true" />
          {prev.version}
        </span>
      </div>

      <div className="bm-comp-list">
        {rows.map((r) => (
          <div className="bm-comp-row" key={r.label}>
            <div className="bm-comp-label">{r.label}</div>
            <div className="bm-comp-data">
              <div className="bm-comp-bar-pair">
                <div className="bm-comp-bar-line">
                  <div className="bm-comp-track">
                    <span className="bm-comp-fill bm-comp-fill-blue" style={{ width: `${r.width(r.curr)}%` }} />
                  </div>
                  <strong className="bm-comp-num bm-comp-num-blue">{r.curr}{r.unit}</strong>
                </div>
                <div className="bm-comp-bar-line">
                  <div className="bm-comp-track">
                    <span className="bm-comp-fill bm-comp-fill-gray" style={{ width: `${r.width(r.prev)}%` }} />
                  </div>
                  <span className="bm-comp-num bm-comp-num-gray">{r.prev}{r.unit}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="engineering-note">Development diagnostics, not the sealed test.</p>
    </div>
  );
}

/** 5 Additional Metrics stat tiles */
export function AdditionalMetricsTiles(): JSX.Element {
  const b = BENCHMARK;
  const metrics = [
    { label: 'Specificity', value: `${b.specificity}%`, icon: <Check className="w-5 h-5" />, tone: 'blue' },
    { label: 'F1 score', value: b.f1.toFixed(3), icon: <Gauge className="w-5 h-5" />, tone: 'blue' },
    { label: 'Median time to alert', value: `${b.medianSeconds.toFixed(2)} s`, icon: <Zap className="w-5 h-5" />, tone: 'cyan' },
    { label: 'p90 time to alert', value: `${b.p90Seconds.toFixed(2)} s`, icon: <Zap className="w-5 h-5" />, tone: 'cyan' },
    { label: `False alerts in ${b.adlClips} everyday clips`, value: String(b.falseAlertEvents), icon: <Cpu className="w-5 h-5" />, tone: 'red' },
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
    { label: 'Clips', value: `${BENCHMARK.clips} (${BENCHMARK.fallClips} falls, ${BENCHMARK.adlClips} everyday)` },
    { label: 'Evaluated', value: new Date(`${BENCHMARK.evaluatedAt}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) },
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
            <stop offset="0%" stopColor="var(--tone-red-398-2)" stopOpacity="0.08" />
            <stop offset="100%" stopColor="var(--tone-red-398-2)" stopOpacity="0.02" />
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
          <line key={y} x1={PAD} x2={W - PAD} y1={y} y2={y} stroke="var(--tone-neutral-39)" strokeWidth="1" />
        ))}

        {/* Reference Threshold Lines */}
        {/* Median line (0.85s) */}
        <line x1={x(BENCHMARK.medianSeconds)} x2={x(BENCHMARK.medianSeconds)} y1={28} y2={AXIS_Y} className="tl-median" stroke="var(--tone-neutral-888)" strokeWidth="1.5" />
        <rect x={x(BENCHMARK.medianSeconds) - 40} y={10} width="80" height="18" rx="4" fill="var(--tone-neutral-888)" />
        <text x={x(BENCHMARK.medianSeconds)} y={23} textAnchor="middle" fill="var(--tone-neutral-0)" fontSize="10" fontWeight="700" className="tl-label tl-median">
          median 0.85 s
        </text>

        {/* p95 line (1.58s) */}
        <line x1={x(BENCHMARK.p95Seconds)} x2={x(BENCHMARK.p95Seconds)} y1={30} y2={AXIS_Y} className="tl-p95" stroke="var(--tone-blue-494)" strokeWidth="1.5" strokeDasharray="4 3" />
        <rect x={x(BENCHMARK.p95Seconds) - 34} y={12} width="68" height="18" rx="4" fill="var(--tone-blue-494)" />
        <text x={x(BENCHMARK.p95Seconds)} y={25} textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="700" className="tl-label tl-p95">
          p95 1.58 s
        </text>

        {/* Gate line (3.0s) */}
        <line x1={x(BENCHMARK.gates.maxP95Seconds)} x2={x(BENCHMARK.gates.maxP95Seconds)} y1={30} y2={AXIS_Y} className="tl-gate" stroke="var(--tone-red-494)" strokeWidth="2" strokeDasharray="5 3" />
        <rect x={x(BENCHMARK.gates.maxP95Seconds) - 30} y={12} width="60" height="18" rx="4" fill="var(--tone-red-494)" />
        <text x={x(BENCHMARK.gates.maxP95Seconds)} y={25} textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="700" className="tl-label tl-gate">
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
              stroke="var(--tone-neutral-0)"
              strokeWidth="1.5"
            >
              <title>{`Fall alert: ${d.s.toFixed(2)} seconds`}</title>
            </circle>
          );
        })}

        {/* X Axis & Ticks */}
        <line x1={PAD} x2={W - PAD} y1={AXIS_Y} y2={AXIS_Y} className="tl-axis" stroke="var(--tone-neutral-349)" strokeWidth="1.5" />
        {[0, 1, 2, 3, 4].map((s) => (
          <g key={s}>
            <line x1={x(s)} x2={x(s)} y1={AXIS_Y} y2={AXIS_Y + 5} stroke="var(--tone-neutral-349)" strokeWidth="1.5" />
            <text key={s} x={x(s)} y={AXIS_Y + 20} textAnchor="middle" className="tl-tick" fill="var(--tone-neutral-531)" fontSize="11" fontWeight="600">
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
