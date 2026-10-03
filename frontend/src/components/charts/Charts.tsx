import type { JSX } from 'react';
import './Charts.css';

function coords(values: readonly number[], width: number, height: number, pad = 8): string {
  const low = Math.min(0, ...values);
  const high = Math.max(1, ...values);
  return values
    .map(
      (value, i) =>
        `${pad + (i / Math.max(1, values.length - 1)) * (width - pad * 2)},${
          height - pad - ((value - low) / (high - low)) * (height - pad * 2)
        }`,
    )
    .join(' ');
}

export function Sparkline({
  values,
  color = 'var(--primary)',
}: {
  values: readonly number[];
  color?: string;
}): JSX.Element {
  return (
    <svg className="sparkline" viewBox="0 0 110 40" aria-hidden="true">
      <polyline
        points={coords(values, 110, 40)}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function RingGauge({
  value,
  max = 100,
  label,
  unit = '',
  color = 'var(--primary)',
}: {
  value: number;
  max?: number;
  label: string;
  unit?: string;
  color?: string;
}): JSX.Element {
  const ratio = Math.max(0, Math.min(1, value / max));
  const circumference = 2 * Math.PI * 48;
  return (
    <div className="ring-gauge">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="48" fill="none" stroke="var(--border)" strokeWidth="11" />
        <circle
          cx="60"
          cy="60"
          r="48"
          fill="none"
          stroke={color}
          strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray={`${circumference * ratio} ${circumference}`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="gauge-value">
        <strong>
          {value}
          {unit}
        </strong>
        <small>{label}</small>
      </div>
    </div>
  );
}
