import { describe, expect, it } from 'vitest';
import { formatFallScore, formatLatency, formatTimestamp } from './format.ts';
import { cameraStatusMeta, connectionMeta } from './status.ts';

describe('format utils', () => {
  it('formats timestamps consistently in UTC', () => {
    expect(formatTimestamp('2026-09-23T07:10:04Z')).toBe('2026-09-23 07:10:04 UTC');
    expect(formatTimestamp(null)).toBe('—');
    expect(formatTimestamp('bad-input')).toBe('bad-input');
    // SQLite returns UTC without an offset; it must not be read as local time.
    expect(formatTimestamp('2026-09-23T07:10:04')).toBe('2026-09-23 07:10:04 UTC');
  });

  it('formats scores and latency without fake precision', () => {
    expect(formatFallScore(0.87)).toBe('0.87');
    expect(formatFallScore(Number.NaN)).toBe('—');
    expect(formatLatency(12.4, 18.2)).toBe('12.4 ms avg / 18.2 ms p95');
  });
});

describe('status metadata is not color-only', () => {
  it('maps camera states to label + symbol + description', () => {
    expect(cameraStatusMeta('online')).toMatchObject({ label: 'Online', symbol: '●' });
    expect(cameraStatusMeta('degraded').symbol).toBe('◐');
    expect(cameraStatusMeta('offline')).toMatchObject({ label: 'Offline', symbol: '○' });
    expect(cameraStatusMeta('weird').label).toBe('weird');
  });

  it('maps connection states explicitly', () => {
    expect(connectionMeta(true).label).toBe('Live updates');
    expect(connectionMeta(false).label).toBe('Updates paused');
  });
});
