import type { JSX } from 'react';

export function Brand({ compact = false }: { compact?: boolean }): JSX.Element {
  return (
    <div className={`brand${compact ? ' brand-compact' : ''}`}>
      <svg
        className="brand-mark"
        viewBox="0 0 48 40"
        role="img"
        aria-label="ElderCare Vision mark"
      >
        <defs>
          <linearGradient id="brand-blue" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#60A5FA" />
            <stop offset="1" stopColor="#2563EB" />
          </linearGradient>
          <linearGradient id="brand-mint" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#6EE7D8" />
            <stop offset="1" stopColor="#14B8A6" />
          </linearGradient>
        </defs>
        <circle cx="16" cy="22" r="13" fill="url(#brand-blue)" opacity="0.9" />
        <circle cx="28" cy="14" r="13" fill="url(#brand-mint)" opacity="0.86" />
        <circle cx="33" cy="27" r="12" fill="#7DD3FC" opacity="0.72" />
        <path d="M15 11.5a13 13 0 0 1 10.6 2.7A13 13 0 0 0 17 35.1 13 13 0 0 1 15 11.5Z" fill="#fff" opacity="0.22" />
      </svg>
      {compact ? null : (
        <span className="brand-wordmark"><span>ElderCare</span> <strong>Vision</strong></span>
      )}
    </div>
  );
}
