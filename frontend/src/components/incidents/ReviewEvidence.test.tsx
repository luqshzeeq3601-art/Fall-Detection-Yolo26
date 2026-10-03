import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setApiClient, type ApiClient } from '../../api/index.ts';
import type { IncidentEvidence } from '../../api/types.ts';
import { ReviewEvidence } from './ReviewEvidence.tsx';

beforeEach(() => {
  setApiClient({
    evidenceUrl: (incidentId: string, evidenceId: string) => `/api/v1/incidents/${incidentId}/evidence/${evidenceId}`,
  } as unknown as ApiClient);
});

afterEach(() => {
  setApiClient(null);
  cleanup();
});

const frames: IncidentEvidence[] = [0, 1, 2].map((index) => ({
  id: `frame-${index}`,
  incident_id: 'incident',
  evidence_type: 'snapshot',
  storage_path: `keyframe_0${index}.jpg`,
  mime_type: 'image/jpeg',
  sha256: 'test',
  captured_at: `2026-10-01T10:10:0${4 - index}Z`,
  created_at: '2026-10-01T10:10:04Z',
}));

describe('Review evidence', () => {
  it('selects saved frames without adding recording controls or invented timestamps', () => {
    render(<ReviewEvidence items={frames} />);
    const first = screen.getByRole('button', { name: /select keyframe 1/i });
    expect(first.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /select keyframe 3/i }));
    expect(first.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('link', { name: /selected keyframe: open full size/i }).getAttribute('href')).toContain('frame-2');
    expect(screen.queryByRole('button', { name: /play/i })).toBeNull();
    expect(screen.queryByText('Depth view')).toBeNull();
  });

  it('reports failed images and never replaces them with synthetic evidence', () => {
    render(<ReviewEvidence items={frames.slice(0, 1)} />);
    fireEvent.error(screen.getByRole('img', { name: 'Selected saved keyframe' }));
    expect(screen.getByText('This saved image is unavailable.')).toBeDefined();
    expect(screen.queryByRole('img', { name: 'Selected saved keyframe' })).toBeNull();
  });

  it('handles absent image evidence and ignores unsupported video records', () => {
    render(<ReviewEvidence items={[{ ...frames[0], mime_type: 'video/mp4' }]} />);
    expect(screen.getByText('No keyframes were saved for this incident.')).toBeDefined();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
