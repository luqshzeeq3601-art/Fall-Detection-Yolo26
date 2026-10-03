/**
 * Timestamp + metric formatting. Single consistent readable format.
 * Invalid input never throws; falls back to the raw value.
 */
/** The API stores UTC; SQLite returns it without an offset, so treat bare ISO times as UTC. */
export function parseApiTime(iso: string): Date {
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasZone || !iso.includes('T') ? iso : `${iso}Z`);
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = parseApiTime(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ` +
    `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`
  );
}

export function formatFallScore(score: number): string {
  if (!Number.isFinite(score)) return '—';
  return score.toFixed(2);
}

export function formatLatency(avg: number, p95: number): string {
  if (!Number.isFinite(avg) || !Number.isFinite(p95)) return '—';
  return `${avg.toFixed(1)} ms avg / ${p95.toFixed(1)} ms p95`;
}

export function formatFps(fps: number): string {
  if (!Number.isFinite(fps)) return '—';
  return `${fps.toFixed(1)} fps`;
}
