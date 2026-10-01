import { connectionMeta } from '../../utils/status.ts';
import type { JSX } from 'react';

export function ConnectionBadge({ connected }: { connected: boolean }): JSX.Element {
  const meta = connectionMeta(connected);
  return (
    <span
      role="status"
      aria-label={`Event stream: ${meta.label}. ${meta.description}`}
      className={`conn conn-${meta.tone}`}
    >
      <span aria-hidden="true">{meta.symbol}</span> {meta.label}
    </span>
  );
}
