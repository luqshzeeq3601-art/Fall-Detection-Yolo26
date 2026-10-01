import { useState, type JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import { isReviewLabel, type ReviewLabel } from '../../api/types.ts';

const LABEL_HELP: Record<ReviewLabel, string> = {
  confirmed_fall: 'The evidence shows a fall needing attention.',
  non_fall: 'Normal activity — not a fall.',
  uncertain: 'Cannot tell from the evidence.',
};

/**
 * P6-005 append-only human review form over POST /incidents/{id}/reviews.
 * No label is pre-selected: the reviewer must make an explicit choice.
 */
export function ReviewForm({
  incidentId,
  onSubmitted,
}: {
  incidentId: string;
  onSubmitted: () => void;
}): JSX.Element {
  const [label, setLabel] = useState<ReviewLabel | ''>('');
  const [notes, setNotes] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!isReviewLabel(label)) {
      setError('Choose a review label before submitting.');
      return;
    }
    if (notes.length > 2000) {
      setError('Notes must be 2000 characters or fewer.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await getApiClient().submitReview(incidentId, {
        label,
        notes: notes || undefined,
        reviewer: reviewer || undefined,
      });
      setSuccess(true);
      setLabel('');
      setNotes('');
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review submission failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Submit human review">
      <h3>Submit review</h3>
      <fieldset>
        <legend>Review decision (required)</legend>
        {(Object.keys(LABEL_HELP) as ReviewLabel[]).map((option) => (
          <label key={option} style={{ display: 'block', fontWeight: 400, margin: '4px 0' }}>
            <input
              type="radio"
              name="review-label"
              value={option}
              checked={label === option}
              onChange={() => setLabel(option)}
              style={{ width: 'auto', marginRight: 8 }}
            />
            <strong>{option}</strong> — {LABEL_HELP[option]}
          </label>
        ))}
      </fieldset>
      <label htmlFor="review-notes">Notes (optional, max 2000)</label>
      <textarea
        id="review-notes"
        value={notes}
        maxLength={2000}
        rows={3}
        onChange={(event) => setNotes(event.target.value)}
      />
      <p style={{ color: '#5b6575', fontSize: 12 }}>{notes.length}/2000</p>
      <label htmlFor="reviewer-name">Reviewer (optional)</label>
      <input
        id="reviewer-name"
        value={reviewer}
        maxLength={128}
        onChange={(event) => setReviewer(event.target.value)}
      />
      {error ? <div role="alert">{error}</div> : null}
      {success ? <div role="status">Review saved.</div> : null}
      <button type="submit" className="primary" disabled={submitting}>
        {submitting ? 'Saving…' : 'Save review'}
      </button>
    </form>
  );
}
