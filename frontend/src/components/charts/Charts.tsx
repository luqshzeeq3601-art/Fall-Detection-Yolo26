import { useState, type JSX } from 'react';
import './Charts.css';

function coords(values: readonly number[], width: number, height: number, pad = 8): string {
  const low = Math.min(0, ...values); const high = Math.max(1, ...values);
  return values.map((value, i) => `${pad + i / Math.max(1, values.length - 1) * (width - pad * 2)},${height - pad - (value - low) / (high - low) * (height - pad * 2)}`).join(' ');
}
export function Sparkline({ values, color = 'var(--primary)' }: { values: readonly number[]; color?: string }): JSX.Element {
  return <svg className="sparkline" viewBox="0 0 110 40" aria-hidden="true"><polyline points={coords(values, 110, 40)} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
export function AreaChart({ values, labels = [], color = 'var(--primary)' }: { values: readonly number[]; labels?: readonly string[]; color?: string }): JSX.Element {
  const [active, setActive] = useState<number | null>(null); const width = 800; const height = 140; const pad = 16;
  const points = coords(values, width, height, pad); const high = Math.max(1, ...values); const entries = points.split(' ');
  if (values.length === 0) return <p className="muted">No history is available.</p>;
  return <div className="area-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Incidents by day"><title>{values.map((v, i) => `${labels[i] ?? i + 1}: ${v}`).join(', ')}</title>{[0, .5, 1].map((v) => <g key={v}><line x1={pad} x2={width - pad} y1={height - pad - v * (height - pad * 2)} y2={height - pad - v * (height - pad * 2)} className="chart-grid" /><text x="0" y={height - pad - v * (height - pad * 2)} className="chart-axis">{Math.round(high * v)}</text></g>)}<polygon points={`${pad},${height - pad} ${points} ${width - pad},${height - pad}`} fill={color} opacity=".09" /><polyline points={points} fill="none" stroke={color} strokeWidth="2.5" />{entries.map((point, i) => { const [x, y] = point.split(',').map(Number); return <circle key={i} cx={x} cy={y} r={active === i ? 6 : 4} fill={color} stroke="white" strokeWidth="2" tabIndex={0} aria-label={`${labels[i] ?? i + 1}: ${values[i]} incidents`} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} />; })}</svg><div className="chart-labels">{labels.map((label) => <span key={label}>{label}</span>)}</div><p className="chart-tooltip" role="status">{active !== null ? `${labels[active] ?? active + 1}: ${values[active]} incidents` : 'Focus or hover a point to inspect the count.'}</p></div>;
}
export function RingGauge({ value, max = 100, label, unit = '', color = 'var(--primary)' }: { value: number; max?: number; label: string; unit?: string; color?: string }): JSX.Element {
  const ratio = Math.max(0, Math.min(1, value / max)); const circumference = 2 * Math.PI * 48;
  return <div className="ring-gauge"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="48" fill="none" stroke="var(--border)" strokeWidth="11" /><circle cx="60" cy="60" r="48" fill="none" stroke={color} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${circumference * ratio} ${circumference}`} transform="rotate(-90 60 60)" /></svg><div className="gauge-value"><strong>{value}{unit}</strong><small>{label}</small></div></div>;
}
export function Donut({ values, labels }: { values: readonly number[]; labels: readonly string[] }): JSX.Element {
  const total = values.reduce((sum, value) => sum + value, 0); const colors = ['#10b981', '#f59e0b', '#2563eb']; const circumference = 2 * Math.PI * 45;
  return <div className="donut-chart"><svg viewBox="0 0 120 120" role="img" aria-label={labels.map((label, i) => `${label}: ${values[i] ?? 0}`).join(', ')}><circle cx="60" cy="60" r="45" fill="none" stroke="#e6eefb" strokeWidth="15" />{values.map((value, i) => <circle key={i} cx="60" cy="60" r="45" fill="none" stroke={colors[i % colors.length]} strokeWidth="15" strokeDasharray={`${total ? value / total * circumference : 0} ${circumference}`} strokeDashoffset={-values.slice(0, i).reduce((sum, n) => sum + n, 0) / Math.max(1, total) * circumference} transform="rotate(-90 60 60)" />)}</svg><strong>{total}<small>samples</small></strong><ul>{labels.map((label, i) => <li key={label}><span className={`donut-dot donut-dot-${i}`} />{label}<b>{values[i] ?? 0}</b></li>)}</ul></div>;
}
