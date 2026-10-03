import { Check, HelpCircle, X } from 'lucide-react';
import { useState, type JSX } from 'react';
import { getApiClient } from '../../api/index.ts';
import type { ReviewLabel } from '../../api/types.ts';

const DECISIONS: { label: ReviewLabel; text: string; key: string; className: string; icon: JSX.Element }[] = [
  { label: 'confirmed_fall', text: 'Real fall', key: 'F', className: 'decision-fall', icon: <Check aria-hidden="true" /> },
  { label: 'non_fall', text: 'False alarm', key: 'N', className: 'decision-safe', icon: <X aria-hidden="true" /> },
  { label: 'uncertain', text: 'Unsure', key: 'U', className: 'decision-unsure', icon: <HelpCircle aria-hidden="true" /> },
];

/**
 * Record a human decision. Reviews are append-only: changing your mind adds a new
 * decision and the latest one counts; the detector's own output is never edited.
 */
export function DecisionBar({ incidentId, current, onSaved, showKeys = false }: { incidentId: string; current: string | null | undefined; onSaved: (label: ReviewLabel) => void; showKeys?: boolean }): JSX.Element {
  const [note, setNote] = useState('');
  const [pending, setPending] = useState<ReviewLabel | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function decide(label: ReviewLabel): Promise<void> {
    if (pending) return;
    setPending(label);
    setMessage(null);
    try {
      await getApiClient().submitReview(incidentId, note.trim() ? { label, notes: note.trim() } : { label });
      setNote('');
      setMessage({ ok: true, text: `Saved as “${DECISIONS.find((d) => d.label === label)?.text}”.` });
      onSaved(label);
    } catch (error) {
      setMessage({ ok: false, text: error instanceof Error ? error.message : 'The decision was not saved. Try again.' });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="decision-bar">
      <p className="section-label">{current ? 'Change the decision' : 'Was this a real fall?'}</p>
      <div className="decision-buttons">
        {DECISIONS.map((decision) => (
          <button key={decision.label} type="button" className={`decision ${decision.className}${current === decision.label ? ' is-current' : ''}`} disabled={Boolean(pending)} aria-pressed={current === decision.label} onClick={() => void decide(decision.label)}>
            {decision.icon}<span>{pending === decision.label ? 'Saving…' : decision.text}</span>{showKeys ? <kbd>{decision.key}</kbd> : null}
          </button>
        ))}
      </div>
      <label className="sr-only" htmlFor={`note-${incidentId}`}>Note (optional)</label>
      <textarea id={`note-${incidentId}`} rows={2} maxLength={2000} placeholder="Optional note, e.g. “sat down on purpose”" value={note} onChange={(event) => setNote(event.target.value)} />
      {message ? <p className={message.ok ? 'decision-ok' : 'decision-error'} role={message.ok ? 'status' : 'alert'}>{message.text}</p> : null}
    </div>
  );
}
