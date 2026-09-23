import type { JSX } from 'react';
import { useCameras } from '../../hooks/useDashboard.ts';
import { EmptyState, ErrorState, LoadingState } from '../common/States.tsx';
import { CameraCard } from './CameraCard.tsx';

/**
 * P6-002 camera-health view: full loading/error/empty/populated coverage
 * over GET /cameras. AC-040: camera state is visible.
 */
export function CameraList(): JSX.Element {
  const { data, loading, error, reload } = useCameras();
  if (loading) return <LoadingState label="Loading cameras…" />;
  if (error || !data)
    return <ErrorState message={error ?? 'Cameras unavailable'} onRetry={reload} />;
  if (data.length === 0)
    return <EmptyState title="No cameras registered" detail="Register a camera to begin monitoring." />;
  return (
    <ul aria-label="Camera health" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {data.map((camera) => (
        <CameraCard key={camera.id} camera={camera} />
      ))}
    </ul>
  );
}
