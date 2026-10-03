import { Camera as CameraIcon, Download, Maximize, Scissors, Square } from 'lucide-react';
import { useEffect, useRef, useState, type JSX, type ReactNode } from 'react';
import { liveApi, type LiveSessionStatus } from '../../api/platform.ts';
import { recordImageClip } from './clipRecorder.ts';
import { STATE_LABEL } from './sourceLabels.ts';
import './LiveStream.css';


/**
 * Annotated MJPEG view of one running session, with stop / snapshot / clip / fullscreen.
 * Renders `placeholder` when nothing is streaming.
 */
export function StreamViewer({
  session,
  onStop,
  stopping = false,
  placeholder,
  compact = false,
}: {
  session?: LiveSessionStatus;
  onStop?: () => void;
  stopping?: boolean;
  placeholder: ReactNode;
  compact?: boolean;
}): JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const recordAbort = useRef<AbortController | null>(null);
  const [recording, setRecording] = useState(false);
  const [note, setNote] = useState('');
  const [failedStream, setFailedStream] = useState<string | null>(null);
  const running = Boolean(session?.active);
  const streamKey = session ? `${session.camera_id}-${session.started_at}` : '';
  const showStream = running && session && failedStream !== streamKey;
  const state = session?.state ?? 'NO_PERSON';

  useEffect(() => () => recordAbort.current?.abort(), []);
  useEffect(() => { if (!running) recordAbort.current?.abort(); }, [running]);

  async function clip(): Promise<void> {
    if (!image.current || recording || !session) return;
    const controller = new AbortController();
    recordAbort.current = controller;
    setRecording(true);
    setNote('Recording 10 seconds of the annotated video…');
    try {
      await recordImageClip(image.current, 10, `${session.camera_id}-${Date.now()}.webm`, controller.signal);
      setNote('Clip saved to your downloads.');
    } catch (error) {
      setNote(error instanceof DOMException && error.name === 'AbortError' ? 'Recording stopped.' : error instanceof Error ? error.message : 'Recording failed.');
    } finally {
      setRecording(false);
      recordAbort.current = null;
    }
  }

  async function fullscreen(): Promise<void> {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await container.current?.requestFullscreen();
    } catch {
      setNote('Fullscreen is not available here.');
    }
  }

  return (
    <div ref={container} className={`live-panel${compact ? ' live-panel-compact' : ''}`}>
      <div className={`live-frame live-state-${state.toLowerCase()}${showStream ? '' : ' is-empty'}`}>
        {showStream ? (
          <img ref={image} src={liveApi.streamUrl(session.camera_id, session.started_at)} alt={`Live annotated video: ${session.source_label}`} onError={() => setFailedStream(streamKey)} />
        ) : (
          <div className="live-placeholder" role="status"><CameraIcon aria-hidden="true" />{placeholder}</div>
        )}
        {showStream ? (
          <>
            <span className="live-badge"><i aria-hidden="true" /> {session.source_type === 'webcam' ? 'LIVE' : 'ANALYSING'} · {session.source_label}</span>
            <span className={`live-verdict live-verdict-${state.toLowerCase()}`}>{STATE_LABEL[state] ?? state}</span>
          </>
        ) : null}
      </div>
      {running && session && !compact ? (
        <div className="live-toolbar">
          {onStop ? <button type="button" className="btn btn-danger" onClick={onStop} disabled={stopping}><Square aria-hidden="true" />{stopping ? 'Stopping…' : 'Stop'}</button> : null}
          <span className="live-toolbar-spacer" />
          <a className="btn btn-secondary btn-sm" href={liveApi.snapshotUrl(session.camera_id)} download><Download aria-hidden="true" />Snapshot</a>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void clip()} disabled={!showStream || recording}><Scissors aria-hidden="true" />{recording ? 'Recording…' : 'Record 10 s'}</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void fullscreen()} aria-label="Show video fullscreen"><Maximize aria-hidden="true" /></button>
        </div>
      ) : null}
      {note ? <p className="helper" role="status">{note}</p> : null}
    </div>
  );
}
