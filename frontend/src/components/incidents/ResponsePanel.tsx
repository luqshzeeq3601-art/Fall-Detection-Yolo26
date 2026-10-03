import { CheckCircle2, Footprints, Siren } from 'lucide-react';
import { useState, type JSX } from 'react';
import { incidentApi } from '../../api/platform.ts';
import type { IncidentResponseEntry, ResponseOutcome, ResponseStatus } from '../../api/types.ts';
import { parseApiTime } from '../../utils/format.ts';

const TIME = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

const OUTCOME_TEXT: Record<ResponseOutcome, string> = { resident_ok: 'resident OK', needed_help: 'needed help' };

/** Short status for lists: who is handling it, or that nobody has yet. */
export function ResponseTag({ status, responder }: { status?: ResponseStatus; responder?: string | null }): JSX.Element | null {
  if (status === 'escalated') return <span className="tag tag-fall">No response yet</span>;
  if (status === 'responding') return <span className="tag tag-blue">{responder ? `${responder} responding` : 'Responding'}</span>;
  return null;
}

function entryText(entry: IncidentResponseEntry): string {
  if (entry.action === 'escalated') return 'Escalated: nobody had responded';
  if (entry.action === 'responding') return `${entry.responder ?? 'Someone'} is responding`;
  return `${entry.responder ?? 'Someone'} resolved it: ${entry.outcome ? OUTCOME_TEXT[entry.outcome] : 'done'}`;
}

/**
 * Who is going to help, and how it ended. Separate from the review decision: a review
 * says whether the detector was right, a response says whether someone went to the room.
 */
export function ResponsePanel({ incidentId, status, responder, entries, onSaved }: {
  incidentId: string;
  status: ResponseStatus;
  responder: string | null | undefined;
  entries: IncidentResponseEntry[];
  onSaved: () => void;
}): JSX.Element {
  const [pending, setPending] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  async function send(key: string, call: () => Promise<unknown>): Promise<void> {
    setPending(key);
    setError('');
    try { await call(); setNote(''); onSaved(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Not saved. Try again.'); } finally { setPending(null); }
  }
  const resolve = (outcome: ResponseOutcome): Promise<void> => send(outcome, () => incidentApi.respond(incidentId, { action: 'resolved', outcome, ...(note.trim() ? { notes: note.trim() } : {}) }));

  const heading = status === 'resolved' ? 'Resolved'
    : status === 'responding' ? `${responder ?? 'Someone'} is responding`
    : status === 'escalated' ? 'Nobody has responded yet'
    : 'Does someone need to check on them?';

  return (
    <section className={`response-panel response-${status}`} aria-label="Response">
      <p className="response-heading">
        {status === 'resolved' ? <CheckCircle2 aria-hidden="true" /> : status === 'escalated' ? <Siren aria-hidden="true" /> : <Footprints aria-hidden="true" />}
        <strong>{heading}</strong>
      </p>
      {status === 'open' || status === 'escalated' ? (
        <button type="button" className="btn btn-primary" disabled={Boolean(pending)} onClick={() => void send('responding', () => incidentApi.respond(incidentId, { action: 'responding' }))}>
          {pending === 'responding' ? 'Saving…' : "I'm responding"}
        </button>
      ) : null}
      {status === 'responding' ? (
        <>
          <label className="sr-only" htmlFor={`response-note-${incidentId}`}>What happened (optional)</label>
          <textarea id={`response-note-${incidentId}`} rows={2} maxLength={2000} placeholder="What happened (optional)" value={note} onChange={(event) => setNote(event.target.value)} />
          <div className="response-actions">
            <button type="button" className="btn btn-secondary" disabled={Boolean(pending)} onClick={() => void resolve('resident_ok')}>{pending === 'resident_ok' ? 'Saving…' : 'Resolved: resident OK'}</button>
            <button type="button" className="btn btn-secondary" disabled={Boolean(pending)} onClick={() => void resolve('needed_help')}>{pending === 'needed_help' ? 'Saving…' : 'Resolved: needed help'}</button>
          </div>
        </>
      ) : null}
      {error ? <p className="decision-error" role="alert">{error}</p> : null}
      {entries.length ? (
        <ol className="response-history" aria-label="Response history">
          {entries.map((entry) => (
            <li key={entry.id}><span>{entryText(entry)}</span><small>{TIME.format(parseApiTime(entry.created_at))}</small>{entry.notes ? <p>{entry.notes}</p> : null}</li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
