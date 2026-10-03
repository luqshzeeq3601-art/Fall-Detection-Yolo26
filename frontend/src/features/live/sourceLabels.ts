/** "fall-03-cam0.mp4" → "Fall 03 · camera 0" for URFD clips; other names unchanged. */
export function clipTitle(name: string): string {
  const match = /^(fall|adl)-(\d+)-cam(\d+)\./i.exec(name);
  if (!match) return name;
  return `${match[1].toLowerCase() === 'fall' ? 'Fall' : 'Daily activity'} ${match[2]} · camera ${match[3]}`;
}

/** Display name for any source reference ("sample:x.mp4", "upload:y.mov", webcam index). */
export function sourceTitle(sourceType: string, source: string): string {
  if (sourceType === 'webcam') return `Camera ${source}`;
  const [kind, name = source] = source.split(/:(.*)/s);
  return kind === 'sample' ? clipTitle(name) : name;
}

/** Expected outcome of a URFD dataset clip, or null for anything else. */
export function clipExpectation(source: string): 'fall' | 'no_fall' | null {
  const name = source.replace(/^sample:/, '').toLowerCase();
  if (!source.startsWith('sample:')) return null;
  if (name.startsWith('fall')) return 'fall';
  if (name.startsWith('adl')) return 'no_fall';
  return null;
}

/** Detector state shown on the live video and in the state ladder. */
export const STATE_LABEL: Record<string, string> = {
  NO_PERSON: 'No person in view',
  NORMAL: 'Upright',
  FALLING: 'Possible fall',
  FALL_DETECTED: 'Fall confirmed',
};
