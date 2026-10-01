/**
 * Status metadata with text + symbol so meaning never relies on color alone.
 */

export interface StatusMeta {
  label: string;
  symbol: string;
  tone: 'ok' | 'warn' | 'bad' | 'neutral';
  description: string;
}

const CAMERA_STATUS: Record<string, StatusMeta> = {
  online: { label: 'Online', symbol: '●', tone: 'ok', description: 'Receiving frames' },
  degraded: { label: 'Degraded', symbol: '◐', tone: 'warn', description: 'Intermittent frames' },
  offline: { label: 'Offline', symbol: '○', tone: 'bad', description: 'No frames received' },
};

export function cameraStatusMeta(status: string): StatusMeta {
  const normalized = status.toLowerCase();
  return (
    CAMERA_STATUS[normalized] ?? {
      label: status || 'Unknown',
      symbol: '?',
      tone: 'neutral',
      description: 'Unknown state',
    }
  );
}

export function connectionMeta(connected: boolean): StatusMeta {
  return connected
    ? { label: 'Live', symbol: '●', tone: 'ok', description: 'Event stream connected' }
    : { label: 'Disconnected', symbol: '○', tone: 'bad', description: 'Event stream disconnected' };
}
