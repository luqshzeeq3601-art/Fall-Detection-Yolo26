import { Activity, AlertTriangle, CheckCircle2, HeartPulse, Play, Radio, SlidersHorizontal, TriangleAlert, UserRound, XCircle } from 'lucide-react';
import { useState, type JSX } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api/client.ts';
import { liveApi, type LiveSessionStatus } from '../../api/platform.ts';
import { Card, PageHeader, StatusPill } from '../../components/common/Ui.tsx';
import { useWorkspaceSettings } from '../settings/useWorkspaceSettings.ts';
import { LikelihoodTrace } from './LikelihoodTrace.tsx';
import { clipExpectation, sourceTitle, STATE_LABEL } from './sourceLabels.ts';
import { SourcePicker, type PickedSource, type SourceTab } from './SourcePicker.tsx';
import { StreamViewer } from './StreamViewer.tsx';
import { useLiveStatus } from './useLiveStatus.ts';
import '../../pages/OperationsPages.css';

const STATES: { state: string; label: string; detail: string }[] = [
  { state: 'NO_PERSON', label: 'No person', detail: 'Nobody tracked' },
  { state: 'NORMAL', label: 'Upright', detail: 'Normal posture' },
  { state: 'FALLING', label: 'Possible fall', detail: 'Rapid descent seen' },
  { state: 'FALL_DETECTED', label: 'Fall confirmed', detail: 'Stayed down · alert sent' },
];

function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Request failed.';
}

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
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

function RunSummary({ session }: { session: LiveSessionStatus }): JSX.Element {
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
        {session.detections.length === 0 ? <p className="helper">{session.phase === 'running' ? 'None so far. Confirmed falls appear here with a link to the saved incident.' : 'None.'}</p> : (
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
      {session.phase === 'running' && session.detector_ready ? <p className="helper">Detector speed {session.fps.toFixed(1)} frames/s · {session.latency_avg_ms.toFixed(0)} ms per frame</p> : null}
    </div>
  );
}

export function LiveMonitor(): JSX.Element {
  const [params] = useSearchParams();
  const live = useLiveStatus(1000);
  const workspace = useWorkspaceSettings();
  const [tab, setTab] = useState<SourceTab>(params.get('source') === 'video' ? 'dataset' : params.get('source') === 'upload' ? 'upload' : 'camera');
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
    : <><strong>Nothing is being monitored</strong><span>Choose a camera, a dataset clip or your own video on the right, then press Start.</span></>;

  return (
    <div className="operations-page live-monitor-page">
      <PageHeader title="Live monitor" subtitle="Watch a camera or analyse a recorded video. Every person is tracked, and a fall is saved as an incident once they stay down.">
        <StatusPill tone={active.length ? 'green' : 'neutral'}>{active.length ? `${active.length} running` : 'Idle'}</StatusPill>
      </PageHeader>

      {active.length > 1 ? (
        <div className="running-switcher" role="tablist" aria-label="Running sources">
          {active.map((session) => <button key={session.camera_id} type="button" role="tab" aria-selected={viewing?.camera_id === session.camera_id} onClick={() => setViewingId(session.camera_id)}><Radio aria-hidden="true" />{sourceTitle(session.source_type, session.source)}</button>)}
        </div>
      ) : null}

      <div className={`live-monitor-grid${viewing ? '' : ' is-idle'}`}>
        <div className="live-monitor-main">
          <Card title={viewing ? sourceTitle(viewing.source_type, viewing.source) : 'Viewer'} icon={<HeartPulse />} action={running ? <StatusPill tone="green">{viewing?.source_type === 'webcam' ? 'Live' : 'Analysing'}</StatusPill> : undefined}>
            <StreamViewer session={viewing} onStop={() => void stop()} stopping={busy} placeholder={placeholder} />
            {viewing ? <RunSummary session={viewing} /> : null}
          </Card>
          {viewing ? (
            <Card title="Fall likelihood" icon={<Activity />} action={<span className="helper">last minute of video</span>}>
              <LikelihoodTrace trace={viewing.trace} detections={viewing.detections} threshold={threshold} />
            </Card>
          ) : null}
        </div>

        <aside className="live-monitor-side" aria-label="Source and detector state">
          <Card title="Video source" icon={<SlidersHorizontal />}>
            <SourcePicker tab={tab} onTab={setTab} picked={picked} onPick={setPicked} disabled={busy} />
            <div className="source-start">
              {picked?.source_type === 'file' ? <label className="live-loop"><input type="checkbox" checked={loop} onChange={(event) => setLoop(event.target.checked)} /> Repeat the video until stopped</label> : null}
              {error ? <div className="inline-alert inline-alert-error" role="alert">{error}</div> : null}
              <button type="button" className="btn btn-primary btn-block" disabled={!picked || busy} onClick={() => void start()}>
                <Play aria-hidden="true" />{!picked ? 'Choose a source to start' : picked.source_type === 'webcam' ? `Start monitoring ${picked.label}` : `Analyse ${picked.label}`}
              </button>
              <p className="helper">Detection uses the settings saved in <Link to="/app/settings?tab=detection">Settings → Detection</Link>.</p>
            </div>
          </Card>

          <Card title="Detector state" icon={<UserRound />} action={running && viewing?.track_id !== null && viewing?.track_id !== undefined ? <StatusPill tone="blue">Person {viewing.track_id}</StatusPill> : undefined}>
            <ol className="state-ladder" aria-label="Detector state for the most at-risk person">
              {STATES.map((step) => (
                <li key={step.state} className={`state-${step.state.toLowerCase()}${currentState === step.state ? ' is-current' : ''}`} aria-current={currentState === step.state ? 'step' : undefined}>
                  <span className="state-dot" aria-hidden="true" />
                  <span><strong>{step.label}</strong><small>{step.detail}</small></span>
                </li>
              ))}
            </ol>
            <p className="helper">{running ? `Now: ${STATE_LABEL[currentState ?? 'NO_PERSON']}${viewing?.fall_likelihood !== null && viewing?.fall_likelihood !== undefined ? ` · fall likelihood ${Math.round(viewing.fall_likelihood * 100)}%` : ''}` : 'Shows the person most at risk while a source is running.'}</p>
          </Card>
        </aside>
      </div>
    </div>
  );
}
