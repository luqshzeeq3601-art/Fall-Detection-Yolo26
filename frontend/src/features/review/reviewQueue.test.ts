import { describe, expect, it } from 'vitest';
import type { IncidentDetail } from '../../api/types.ts';
import { buildReviewExport, clampOffset, nextQueueId, shortcutDecision } from './reviewQueue.ts';

describe('review queue helpers', () => {
  it('accepts F/N/S shortcuts and ignores editable or modified key events', () => {
    expect(shortcutDecision(new KeyboardEvent('keydown', { key: 'f' }))).toBe('confirmed_fall');
    expect(shortcutDecision(new KeyboardEvent('keydown', { key: 'n', repeat: true }))).toBeNull();
    expect(shortcutDecision(new KeyboardEvent('keydown', { key: 's', ctrlKey: true }))).toBeNull();
    expect(shortcutDecision(new KeyboardEvent('keydown', { key: 'f' }), { dialogOpen: true })).toBeNull();
    const editor = document.createElement('span');
    editor.contentEditable = 'true';
    editor.setAttribute('contenteditable', 'true');
    const child = document.createElement('span');
    editor.appendChild(child);
    document.body.appendChild(editor);
    Object.defineProperty(child, 'isContentEditable', { value: false });
    Object.defineProperty(editor, 'isContentEditable', { value: true });
    const childEvent = new KeyboardEvent('keydown', { key: 'f', bubbles: true });
    Object.defineProperty(childEvent, 'target', { value: child });
    expect(shortcutDecision(childEvent)).toBeNull();
    document.body.removeChild(editor);
  });

  it('clamps an empty final page and advances to the next remaining id', () => {
    expect(clampOffset(8, 9, 4)).toBe(8);
    expect(clampOffset(8, 8, 4)).toBe(4);
    expect(nextQueueId(['a', 'b'], 'b')).toBe('a');
  });

  it('exports only reviewed labels and excludes uncertain by default', () => {
    const detail = {
      id: 'a', camera_id: 'cam', track_id: '1', started_at: '2026-09-23T07:10:00Z', confirmed_at: '2026-09-23T07:10:04Z', ended_at: null,
      detector_state: 'FALL_CONFIRMED', fall_score: .7, model_name: 'pose', model_version: '1', config_version: '1', evidence_features: { rapid_vertical_drop: true }, created_at: '2026-09-23T07:10:05Z',
      evidence: [{ id: 'e', incident_id: 'a', evidence_type: 'snapshot', storage_path: 'e.jpg', mime_type: 'image/jpeg', sha256: 'abc', captured_at: '2026-09-23T07:10:04Z', created_at: '2026-09-23T07:10:05Z' }],
      reviews: [{ id: 'r', incident_id: 'a', label: 'confirmed_fall', notes: 'omit', reviewer: 'operator', created_at: '2026-09-23T07:12:00Z' }], enrichments: [],
    } as IncidentDetail;
    const body = buildReviewExport([detail]);
    const record = JSON.parse(body) as Record<string, unknown>;
    expect(Object.keys(record).sort()).toEqual(['camera_id', 'confirmed_at', 'detector', 'detector_correct', 'human_label', 'incident_id', 'keyframes', 'reviewed_at', 'reviewer', 'schema_version', 'track_id', 'vlm', 'vlm_agrees_with_human'].sort());
    expect(record.human_label).toBe('confirmed_fall');
    expect(record.reviewed_at).toBe('2026-09-23T07:12:00Z');
    expect(record).not.toHaveProperty('notes');
    expect(record).not.toHaveProperty('label');
    expect(record).not.toHaveProperty('detector_state');
    expect(record).not.toHaveProperty('fall_score');
    expect(body).not.toContain('uncertain');
  });
});
