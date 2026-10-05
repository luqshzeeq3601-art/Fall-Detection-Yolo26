import { Wifi, WifiOff } from 'lucide-react';
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
      {connected ? (
        <Wifi className="conn-icon" size={14} strokeWidth={2.4} aria-hidden="true" />
      ) : (
        <WifiOff className="conn-icon" size={14} strokeWidth={2.4} aria-hidden="true" />
      )}
      <span>{meta.label}</span>
    </span>
  );
}
