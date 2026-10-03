import type { IncidentDetail, ReviewLabel } from '../../api/types.ts';

export type QueueDecision = ReviewLabel | 'skip';

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable || Boolean(target.closest('[contenteditable="true"], [contenteditable=""]'));
}

export function shortcutDecision(event: KeyboardEvent, options?: { dialogOpen?: boolean }): QueueDecision | null {
  if (options?.dialogOpen || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || isEditableTarget(event.target)) return null;
  if (event.key.toLowerCase() === 'f') return 'confirmed_fall';
  if (event.key.toLowerCase() === 'n') return 'non_fall';
  if (event.key.toLowerCase() === 'u') return 'uncertain';
  if (event.key.toLowerCase() === 's') return 'skip';
  return null;
}

export function clampOffset(offset: number, total: number, limit: number): number {
  if (total <= 0 || limit <= 0) return 0;
  return Math.max(0, Math.min(offset, Math.floor((total - 1) / limit) * limit));
}

export function nextQueueId(ids: readonly string[], currentId: string | null): string | null {
  if (ids.length === 0) return null;
  const index = currentId ? ids.indexOf(currentId) : -1;
  return ids[(index + 1) % ids.length] ?? ids[0] ?? null;
}

export interface ExportRecord {
  schema_version: '1.0.0';
  incident_id: string;
  camera_id: string;
  track_id: string;
  confirmed_at: string;
  detector: {
    fall_score: number;
    model_name: string;
    model_version: string;
    config_version: string;
    features: Record<string, unknown>;
  };
  human_label: ReviewLabel;
  detector_correct: boolean | null;
  reviewer: string | null;
  reviewed_at: string;
  vlm: {
    fall_assessment: unknown;
    confidence_assessment: unknown;
    provider: string | null;
    model: string | null;
    prompt_version: string;
  } | null;
  vlm_agrees_with_human: boolean | null;
  keyframes: Array<{ path: string; sha256: string; mime_type: string }>;
}

export function buildReviewExport(details: readonly IncidentDetail[], includeUncertain = false): string {
  const records: ExportRecord[] = [];
  for (const detail of details) {
    const review = [...detail.reviews].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at) || right.id.localeCompare(left.id))[0];
    const label = review?.label as ReviewLabel | undefined;
    if (!label || (label === 'uncertain' && !includeUncertain)) continue;
    const enrichment = [...detail.enrichments]
      .filter((item) => item.status === 'completed' && item.output)
      .sort((left, right) => Date.parse(right.completed_at ?? right.created_at) - Date.parse(left.completed_at ?? left.created_at) || right.id.localeCompare(left.id))[0];
    const vlm = enrichment?.output ? {
      fall_assessment: enrichment.output.fall_assessment,
      confidence_assessment: enrichment.output.confidence_assessment,
      provider: enrichment.provider,
      model: enrichment.model,
      prompt_version: enrichment.prompt_version,
    } : null;
    const fallAssessment = vlm?.fall_assessment;
    records.push({
      schema_version: '1.0.0',
      incident_id: detail.id,
      camera_id: detail.camera_id,
      track_id: detail.track_id,
      confirmed_at: detail.confirmed_at,
      detector: {
        fall_score: detail.fall_score,
        model_name: detail.model_name,
        model_version: detail.model_version,
        config_version: detail.config_version,
        features: detail.evidence_features,
      },
      human_label: label,
      detector_correct: label === 'uncertain' ? null : label === 'confirmed_fall',
      reviewer: review.reviewer,
      reviewed_at: review.created_at,
      vlm,
      vlm_agrees_with_human: fallAssessment !== 'fall' && fallAssessment !== 'no_fall' || label === 'uncertain' ? null : (fallAssessment === 'fall') === (label === 'confirmed_fall'),
      keyframes: detail.evidence.filter((item) => item.evidence_type === 'snapshot').sort((left, right) => left.storage_path.localeCompare(right.storage_path)).map((item) => ({ path: item.storage_path, sha256: item.sha256, mime_type: item.mime_type })),
    });
  }
  return records.map((record) => JSON.stringify(record)).join('\n') + (records.length ? '\n' : '');
}
