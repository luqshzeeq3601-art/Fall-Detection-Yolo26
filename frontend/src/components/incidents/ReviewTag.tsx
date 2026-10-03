import type { JSX } from 'react';

/** One vocabulary for review state across Overview, Incidents and the Review queue. */
export function ReviewTag({ label }: { label: string | null | undefined }): JSX.Element {
  if (label === 'confirmed_fall') return <span className="tag tag-fall">Confirmed fall</span>;
  if (label === 'non_fall') return <span className="tag tag-safe">False alarm</span>;
  if (label === 'uncertain') return <span className="tag tag-neutral">Unsure</span>;
  return <span className="tag tag-review">Needs review</span>;
}
