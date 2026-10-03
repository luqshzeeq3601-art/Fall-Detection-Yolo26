import { Activity, AlertTriangle, BarChart3, CheckCircle2, Clock3, Focus, Radio, ScanLine, TriangleAlert, UserRound, XCircle } from 'lucide-react';
import { useState, type JSX } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api/client.ts';
import { liveApi, type LiveSessionStatus } from '../../api/platform.ts';
import { Card, PageHeader, StatusPill } from '../../components/common/Ui.tsx';
import { useAuth } from '../auth/useAuth.ts';
import { useWorkspaceSettings } from '../settings/useWorkspaceSettings.ts';
import { LikelihoodTrace } from './LikelihoodTrace.tsx';
import { clipExpectation, sourceTitle, STATE_LABEL } from './sourceLabels.ts';
import { SourcePicker, type PickedSource, type SourceTab } from './SourcePicker.tsx';
import { StreamViewer } from './StreamViewer.tsx';
import { useLiveStatus } from './useLiveStatus.ts';
import '../../pages/OperationsPages.css';
import './LiveMonitorReference.css';

function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Request failed.';
}

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((part) => String(part).padStart(2, '0')).join(':');
}

/** Compare a finished dataset run with the clip's known label. */
function Verdict({ session }: { session: LiveSessionStatus }): JSX.Element | null {
  const expected = clipExpectation(session.source);
  if (!expected || session.phase !== 'finished') return null;
  const detected = session.falls > 0;
  const correct = detected === (expected === 'fall');
  const text = expected === 'fall'
    ? detected ? 'The clip contains a fall and the detector caught it.' : 'The clip contains a fall but the detector missed it.'
    : detected ? 'The clip has no fall, but the detector raised an alert (false alarm).' : 'The clip has no fall and the detector stayed quiet.';
  return <div className={`inline-alert ${correct ? 'inline-alert-success' : 'inline-alert-error'}`} role="status">{correct ? <CheckCircle2 aria-hidden="true" /> : <XCircle aria-hidden="true" />}<span><strong>{correct ? 'Matches the label.' : 'Does not match the label.'}</strong> {text}</span></div>;
}

function RunSummary({ session, technical }: { session: LiveSessionStatus; technical: boolean }): JSX.Element {
  const isFile = session.source_type === 'file';
  const progress = isFile && session.duration ? Math.min(1, session.video_time / session.duration) : null;
  const phaseText = session.phase === 'starting' ? 'Loading the detector…'
    : session.phase === 'running' ? (isFile ? 'Analysing video' : 'Monitoring live')
    : session.phase === 'finished' ? 'Analysis finished'
    : session.phase === 'error' ? 'Stopped with an error' : 'Stopped';
  return (
    <div className="run-summary">
      <div className="run-summary-head">
        <div><strong>{phaseText}</strong><span>{sourceTitle(session.source_type, session.source)}</span></div>
        <span className="run-clock">{isFile && session.duration ? `${formatClock(session.video_time)} / ${formatClock(session.duration)}` : formatClock(session.video_time)}</span>
      </div>
      {progress !== null ? <div className="progress-track" role="progressbar" aria-label="Video progress" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress * 100}%` }} /></div> : null}
      {session.error ? <div className="inline-alert inline-alert-error" role="alert"><AlertTriangle aria-hidden="true" /><span>{session.error}</span></div> : null}
      <Verdict session={session} />
      <div className="run-detections">
        <p className="section-label">Falls detected in this run · {session.falls}</p>
        {session.detections.length === 0 ? <p className="helper">{session.phase === 'running' ? 'None so far. Detected falls appear here with a link to the saved incident.' : 'None.'}</p> : (
          <ul>
            {session.detections.map((detection) => (
              <li key={`${detection.video_time}-${detection.track_id}`}>
                <span className="tag tag-fall"><TriangleAlert aria-hidden="true" />Fall</span>
                <span>at {detection.video_time.toFixed(1)} s · person {detection.track_id} · score {detection.fall_score.toFixed(2)}</span>
                {detection.incident_id ? <Link to={`/app/incidents?selected=${encodeURIComponent(detection.incident_id)}`}>Review incident →</Link> : <span className="helper">Not saved</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {technical && session.phase === 'running' && session.detector_ready ? <p className="helper">Detector speed {session.fps.toFixed(1)} frames/s · {session.latency_avg_ms.toFixed(0)} ms per frame</p> : null}
    </div>
  );
}

export function LiveMonitor(): JSX.Element {
  const [params] = useSearchParams();
  const live = useLiveStatus(1000);
  const workspace = useWorkspaceSettings();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [tab, setTab] = useState<SourceTab>(!isAdmin ? 'camera' : params.get('source') === 'video' ? 'dataset' : params.get('source') === 'upload' ? 'upload' : 'camera');

  const [picked, setPicked] = useState<PickedSource | null>(null);
  const [loop, setLoop] = useState(false);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const sessions = Object.values(live.sessions);
  const active = sessions.filter((session) => session.active);
  const latest = [...sessions].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  const viewing = (viewingId ? live.sessions[viewingId] : undefined) ?? active[0] ?? latest;
  const running = Boolean(viewing?.active);
  const threshold = workspace.data?.settings.fall_threshold ?? workspace.data?.frozen_defaults.fall_threshold ?? 0.55;
  const currentState = running ? viewing?.state : undefined;
  const detectorReady = running && viewing?.detector_ready && !live.error;
  const personDetected = detectorReady && currentState !== 'NO_PERSON' && viewing?.track_id !== null;
  const overlayEnabled = workspace.data ? workspace.data.settings.show_skeleton || workspace.data.settings.show_bbox : null;
  const stateTitle = !detectorReady ? 'Detector waiting' : personDetected ? 'Person detected' : 'No person in view';
  const stateDetail = !detectorReady ? running ? 'Loading the detector…' : 'Start a source to begin detection.'
    : currentState === 'NORMAL' ? 'Normal posture (Upright)' : currentState === 'FALLING' ? 'Rapid descent detected. Watching for a fall.'
    : currentState === 'FALL_DETECTED' ? 'Fall confirmed by the temporal detector.' : 'Monitoring for people in the frame.';

  function chooseSource(): void {
    const cameraSelect = document.getElementById('monitor-camera-select');
    const target = cameraSelect && !cameraSelect.matches(':disabled') ? cameraSelect : document.getElementById('monitor-source-control');
    target?.focus();
  }

  async function start(): Promise<void> {
    if (!picked) return;
    setBusy(true); setError('');
    try {
      const status = await liveApi.startSource(picked.source_type, picked.source, picked.source_type === 'file' && loop);
      setViewingId(status.camera_id);
      live.refresh();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function stop(): Promise<void> {
    if (!viewing) return;
    setBusy(true); setError('');
    try { await liveApi.stop(viewing.camera_id); live.refresh(); } catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }

  const placeholder = viewing && !viewing.active
    ? <><strong>{viewing.phase === 'finished' ? 'End of video' : viewing.phase === 'error' ? 'The stream stopped' : 'Stream stopped'}</strong><span>See the results below, or choose another source and start again.</span></>
    : <><strong>Ready to monitor</strong><span>Choose {isAdmin ? 'a camera or video' : 'a camera'}, then start monitoring.</span></>;

  return (
    <div className="operations-page live-monitor-page">
      <PageHeader
        eyebrow="MONITOR"
        title="Live Monitor"
        subtitle="Monitor people, posture and fall events in real time."
      >
        <div className={`monitor-status${detectorReady ? ' is-monitoring' : ''}`} role="status">
          <span className="monitor-status-icon"><Activity aria-hidden="true" /></span>
          <span><strong>{live.error ? 'Unavailable' : detectorReady ? 'Monitoring' : running ? 'Starting' : 'Idle'}</strong><small>{live.error ? 'Live status could not be refreshed' : detectorReady ? 'Detector active' : running ? 'Preparing the detector' : 'Ready when you are'}</small></span>
        </div>
      </PageHeader>

      {live.error ? <div className="inline-alert inline-alert-error monitor-connection-error" role="alert"><AlertTriangle aria-hidden="true" /><span>{live.error} Last reported session values may be out of date.</span><button type="button" className="btn btn-secondary btn-sm" onClick={live.refresh}>Retry</button></div> : null}

      {active.length > 1 ? (
        <div className="running-switcher" role="tablist" aria-label="Running sources">
          {active.map((session) => <button key={session.camera_id} type="button" role="tab" aria-selected={viewing?.camera_id === session.camera_id} onClick={() => setViewingId(session.camera_id)}><Radio aria-hidden="true" />{sourceTitle(session.source_type, session.source)}</button>)}
        </div>
      ) : null}

      <div className={`live-monitor-grid${viewing ? '' : ' is-idle'}`}>
        <div className="live-monitor-main">
          <Card className="monitor-viewer-card">
            <StreamViewer session={viewing} onStop={() => void stop()} stopping={busy} placeholder={placeholder} monitor={{ sourceLabel: running && viewing ? sourceTitle(viewing.source_type, viewing.source) : picked?.label ?? (viewing ? sourceTitle(viewing.source_type, viewing.source) : 'Select a source'), sourceType: running ? viewing?.source_type : picked?.source_type ?? viewing?.source_type, onChoose: chooseSource, onStart: () => void start(), canStart: Boolean(picked) && !busy && !live.error, startLabel: !picked ? 'Choose a source to start' : picked.source_type === 'webcam' ? `Start monitoring ${picked.label}` : `Analyse ${picked.label}`, overlayEnabled, canConfigure: isAdmin, statusUnavailable: Boolean(live.error) }} />
          </Card>
          {viewing && (!running || viewing.detections.length > 0 || viewing.error) ? <Card className="monitor-results-card" title="Run results"><RunSummary session={viewing} technical={isAdmin} /></Card> : null}
          {viewing && isAdmin ? (
            <Card title="Fall likelihood" icon={<Activity />} action={<span className="helper">last minute of video</span>}>
              <LikelihoodTrace trace={viewing.trace} detections={viewing.detections} threshold={threshold} />
            </Card>
          ) : null}
        </div>

        <aside className="live-monitor-side" aria-label="Source and detector state">
          <Card className="monitor-source-card">
            <SourcePicker tab={tab} onTab={setTab} picked={picked} onPick={setPicked} disabled={busy || Boolean(live.error)} allowFiles={isAdmin} reference />
            <div className="source-start">
              {picked?.source_type === 'file' ? <label className="live-loop"><input type="checkbox" checked={loop} onChange={(event) => setLoop(event.target.checked)} /> Repeat the video until stopped</label> : null}
              {error ? <div className="inline-alert inline-alert-error" role="alert">{error}</div> : null}
              {isAdmin
                ? <p className="helper">Detection uses the settings saved in <Link to="/app/settings?tab=detection">Settings → Detection</Link>.</p>
                : <p className="helper">Detection uses the sensitivity set by your workspace admin.</p>}
            </div>
          </Card>

          <Card className="monitor-detector-card" title="Detector State" icon={<UserRound />}>
            <div className={`monitor-person-state state-${detectorReady ? currentState?.toLowerCase() : 'idle'}`} role="status">
              <span className="monitor-person-icon"><UserRound aria-hidden="true" /></span>
              <div><strong>{stateTitle}</strong><span>{stateDetail}</span></div>
              {detectorReady ? <StatusPill tone={currentState === 'FALL_DETECTED' ? 'red' : currentState === 'FALLING' ? 'amber' : personDetected ? 'green' : 'neutral'}>{STATE_LABEL[currentState ?? 'NO_PERSON']}</StatusPill> : null}
            </div>
            <dl className="monitor-detector-metrics">
              <div><dt>Tracking ID</dt><dd>{personDetected ? viewing?.track_id : '—'}</dd></div>
              <div><dt>Confidence</dt><dd>{personDetected ? viewing?.confidence.toFixed(2) : '—'}</dd></div>
              <div><dt>State duration</dt><dd title="Not reported by the detector">—</dd></div>
              <div><dt>Persons detected</dt><dd title="Total person count is not reported by the detector">—</dd></div>
            </dl>
            {personDetected && viewing?.fall_likelihood !== null && viewing?.fall_likelihood !== undefined ? <p className="monitor-risk">Fall likelihood <strong>{Math.round(viewing.fall_likelihood * 100)}%</strong><span> · most at-risk person</span></p> : null}
          </Card>

          <Card className="monitor-session-card" title="Session" icon={<BarChart3 />}>
            <dl className="monitor-session-metrics">
              <div><dt><Clock3 aria-hidden="true" />{viewing?.source_type === 'file' ? 'Video time' : 'Stream time'}</dt><dd>{viewing ? formatClock(viewing.video_time) : '—'}</dd></div>
              <div><dt><ScanLine aria-hidden="true" />Frames processed</dt><dd>{viewing ? viewing.frames.toLocaleString() : '—'}</dd></div>
              <div><dt><Focus aria-hidden="true" />{running ? 'Current FPS' : 'Last reported FPS'}</dt><dd>{viewing?.detector_ready ? viewing.fps.toFixed(1) : '—'}</dd></div>
              <div><dt><Clock3 aria-hidden="true" />Incidents this session</dt><dd>{viewing ? viewing.falls : '—'}</dd></div>
            </dl>
          </Card>
        </aside>
      </div>
    </div>
  );
}
