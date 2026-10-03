import { Camera as CameraIcon, ChevronDown, Download, Eye, Maximize, Play, Scissors, Signal, Square, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useRef, useState, type JSX, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
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
  monitor,
}: {
  session?: LiveSessionStatus;
  onStop?: () => void;
  stopping?: boolean;
  placeholder: ReactNode;
  compact?: boolean;
  monitor?: { sourceType?: 'webcam' | 'file'; sourceLabel: string; onChoose: () => void; onStart: () => void; canStart: boolean; startLabel: string; overlayEnabled: boolean | null; canConfigure: boolean; statusUnavailable: boolean };
}): JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const recordAbort = useRef<AbortController | null>(null);
  const [recording, setRecording] = useState(false);
  const [note, setNote] = useState('');
  const [failedStream, setFailedStream] = useState<string | null>(null);
  const [loadedStream, setLoadedStream] = useState<string | null>(null);
  const running = Boolean(session?.active);
  const streamKey = session ? `${session.camera_id}-${session.started_at}` : '';
  const showStream = running && session && failedStream !== streamKey;
  const connected = showStream && loadedStream === streamKey;
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
          <img ref={image} src={liveApi.streamUrl(session.camera_id, session.started_at)} alt={`Live annotated video: ${session.source_label}`} onLoad={() => setLoadedStream(streamKey)} onError={() => setFailedStream(streamKey)} />
        ) : (
          <div className="live-placeholder" role="status"><span className="live-placeholder-icon"><CameraIcon aria-hidden="true" /></span>{running ? <><strong>{failedStream === streamKey ? 'Video unavailable' : 'Connecting to video…'}</strong><span>{failedStream === streamKey ? 'The video could not be loaded. Stop this source and start it again.' : 'Waiting for the first frame.'}</span></> : placeholder}</div>
        )}
        {showStream ? (
          <>
            <span className="live-badge">{monitor ? <><CameraIcon aria-hidden="true" /> {session.source_label}</> : <><i aria-hidden="true" /> {session.source_type === 'webcam' ? 'LIVE' : 'ANALYSING'} · {session.source_label}</>}</span>
            <span className={`live-verdict live-verdict-${state.toLowerCase()}`}>{STATE_LABEL[state] ?? state}</span>
            {monitor ? <span className="monitor-video-fps"><Signal aria-hidden="true" />FPS: {session.fps.toFixed(1)}</span> : null}
          </>
        ) : null}
      </div>
      {monitor ? <>
        <div className="monitor-viewer-toolbar">
          <button type="button" className="monitor-source-shortcut" onClick={monitor.onChoose} aria-label="Choose video source"><span><CameraIcon aria-hidden="true" /></span><span><strong>{monitor.sourceLabel}</strong><small>{monitor.sourceType === 'file' ? 'Recorded video' : 'Camera source'}</small></span><ChevronDown aria-hidden="true" /></button>
          {running ? <button type="button" className="btn btn-danger monitor-stop" onClick={onStop} disabled={stopping}><Square aria-hidden="true" />{stopping ? 'Stopping…' : 'Stop monitoring'}</button> : <button type="button" className="btn btn-primary monitor-start" onClick={monitor.onStart} disabled={!monitor.canStart} aria-label={monitor.startLabel}><Play aria-hidden="true" />{monitor.canStart ? monitor.startLabel.startsWith('Analyse') ? 'Analyse video' : 'Start monitoring' : 'Choose a source'}</button>}
          {monitor.canConfigure ? <Link className="monitor-overlay" to="/app/settings?tab=detection" aria-label="Configure pose overlays"><Eye aria-hidden="true" />{monitor.overlayEnabled === null ? 'Overlay settings' : `Overlay ${monitor.overlayEnabled ? 'ON' : 'OFF'}`}</Link> : <span className="monitor-overlay"><Eye aria-hidden="true" />{monitor.overlayEnabled === null ? 'Pose overlay' : `Overlay ${monitor.overlayEnabled ? 'ON' : 'OFF'}`}</span>}
          <button type="button" className="monitor-fullscreen" onClick={() => void fullscreen()} aria-label="Show video fullscreen"><Maximize aria-hidden="true" /></button>
        </div>
        <div className={`monitor-stream-connection${connected && !monitor.statusUnavailable ? ' is-connected' : ''}`} role="status">
          {connected && !monitor.statusUnavailable ? <Wifi aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
          <strong>{monitor.statusUnavailable ? 'Status unavailable' : connected ? 'Connected' : running ? failedStream === streamKey ? 'Video unavailable' : 'Connecting…' : 'Not connected'}</strong>
          <span>{session ? `${session.source_type === 'file' ? 'Recorded video' : 'Webcam'}${running && !monitor.statusUnavailable ? ` · ${session.fps.toFixed(1)} FPS` : ''}` : 'Waiting for a source'}</span>
        </div>
      </> : null}
      {running && session && !compact ? (
        <div className="live-toolbar">
          {onStop && !monitor ? <button type="button" className="btn btn-danger" onClick={onStop} disabled={stopping}><Square aria-hidden="true" />{stopping ? 'Stopping…' : 'Stop'}</button> : null}
          <span className="live-toolbar-spacer" />
          <a className="btn btn-secondary btn-sm" href={liveApi.snapshotUrl(session.camera_id)} download><Download aria-hidden="true" />Snapshot</a>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void clip()} disabled={!connected || recording}><Scissors aria-hidden="true" />{recording ? 'Recording…' : 'Record 10 s'}</button>
          {!monitor ? <button type="button" className="btn btn-ghost btn-sm" onClick={() => void fullscreen()} aria-label="Show video fullscreen"><Maximize aria-hidden="true" /></button> : null}
        </div>
      ) : null}
      {note ? <p className="helper" role="status">{note}</p> : null}
    </div>
  );
}
