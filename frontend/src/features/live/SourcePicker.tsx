import { Camera, Database, FileVideo, RefreshCw, Trash2, Upload, Video } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type JSX, type KeyboardEvent } from 'react';
import { liveApi, type DetectedCamera, type LiveSources, type SourceType, type VideoFile } from '../../api/platform.ts';
import { clipTitle } from './sourceLabels.ts';

export type SourceTab = 'camera' | 'dataset' | 'upload';

export interface PickedSource {
  source_type: SourceType;
  source: string;
  label: string;
  expected: 'fall' | 'no_fall' | null;
}

const ACCEPT = '.mp4,.avi,.mov,.mkv,.webm';
const ACCEPTED_EXT = ACCEPT.split(',');
const MAX_BYTES = 1024 ** 3;

function size(bytes: number): string {
  return bytes >= 2 ** 20 ? `${(bytes / 2 ** 20).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function ExpectedTag({ expected }: { expected: VideoFile['expected'] }): JSX.Element | null {
  if (!expected) return null;
  return expected === 'fall' ? <span className="tag tag-fall">Contains a fall</span> : <span className="tag tag-safe">No fall</span>;
}

/** Arrow-key navigation for a WAI-ARIA tablist. */
function onTabKey(event: KeyboardEvent<HTMLDivElement>, tabs: SourceTab[], current: SourceTab, select: (tab: SourceTab) => void): void {
  const index = tabs.indexOf(current);
  const next = event.key === 'ArrowRight' ? tabs[(index + 1) % tabs.length] : event.key === 'ArrowLeft' ? tabs[(index + tabs.length - 1) % tabs.length] : null;
  if (!next) return;
  event.preventDefault();
  select(next);
  document.getElementById(`source-tab-${next}`)?.focus();
}

/**
 * Three ways to feed the detector: a camera attached to the server, a labelled
 * dataset clip (for checking the detector against a known answer), or the user's own video.
 */
export function SourcePicker({ tab, onTab, picked, onPick, disabled }: { tab: SourceTab; onTab: (tab: SourceTab) => void; picked: PickedSource | null; onPick: (source: PickedSource | null) => void; disabled: boolean }): JSX.Element {
  const [cameras, setCameras] = useState<DetectedCamera[] | null>(null);
  const [scanId, setScanId] = useState(0);
  const [finishedScanId, setFinishedScanId] = useState(-1);
  const scanning = finishedScanId !== scanId;
  const [sources, setSources] = useState<LiveSources | null>(null);
  const [filter, setFilter] = useState<'all' | 'fall' | 'no_fall'>('all');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadAbort = useRef<AbortController | null>(null);

  const scan = (): void => setScanId((value) => value + 1);
  const loadFiles = useCallback((): Promise<void> => liveApi.sources().then(setSources).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Videos could not be listed.')), []);

  useEffect(() => {
    let cancelled = false;
    liveApi.detectCameras()
      .then((value) => { if (!cancelled) setCameras(value.cameras); })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Camera scan failed.'); })
      .finally(() => { if (!cancelled) setFinishedScanId(scanId); });
    return () => { cancelled = true; };
  }, [scanId]);
  useEffect(() => {
    let cancelled = false;
    liveApi.sources().then((value) => { if (!cancelled) setSources(value); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);
  useEffect(() => () => uploadAbort.current?.abort(), []);

  const samples = useMemo(() => (sources?.files ?? []).filter((file) => file.kind === 'sample'), [sources]);
  const uploads = useMemo(() => (sources?.files ?? []).filter((file) => file.kind === 'upload'), [sources]);
  const visibleSamples = samples.filter((file) => (filter === 'all' || file.expected === filter) && clipTitle(file.name).toLowerCase().includes(query.trim().toLowerCase()));

  function pickFile(file: VideoFile): void {
    onPick({ source_type: 'file', source: file.ref, label: file.kind === 'sample' ? clipTitle(file.name) : file.name, expected: file.expected });
  }

  async function upload(file: File): Promise<void> {
    const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
    if (!ACCEPTED_EXT.includes(ext)) { setError(`${file.name} is not a supported video. Use MP4, AVI, MOV, MKV or WebM.`); return; }
    if (file.size > MAX_BYTES) { setError(`${file.name} is larger than 1 GB.`); return; }
    const controller = new AbortController();
    uploadAbort.current = controller;
    setError('');
    setProgress(0);
    try {
      const stored = await liveApi.uploadWithProgress(file, setProgress, controller.signal);
      await loadFiles();
      pickFile(stored);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason instanceof Error ? reason.message : 'Upload failed.');
    } finally {
      setProgress(null);
      uploadAbort.current = null;
    }
  }

  async function remove(file: VideoFile): Promise<void> {
    if (!window.confirm(`Delete ${file.name}? Incidents already recorded from it are kept.`)) return;
    try {
      await liveApi.deleteUpload(file.name);
      if (picked?.source === file.ref) onPick(null);
      await loadFiles();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Delete failed.');
    }
  }

  function onDrop(event: DragEvent<HTMLButtonElement>): void {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !disabled) void upload(file);
  }

  const tabs: [SourceTab, string, JSX.Element][] = [['camera', 'Camera', <Camera key="c" aria-hidden="true" />], ['dataset', 'Dataset clip', <Database key="d" aria-hidden="true" />], ['upload', 'Your video', <Upload key="u" aria-hidden="true" />]];

  return (
    <div className="source-picker">
      <div className="segmented" role="tablist" aria-label="Video source type" onKeyDown={(event) => onTabKey(event, tabs.map(([id]) => id), tab, onTab)}>
        {tabs.map(([id, label, icon]) => (
          <button key={id} id={`source-tab-${id}`} type="button" role="tab" aria-selected={tab === id} aria-controls={`source-panel-${id}`} tabIndex={tab === id ? 0 : -1} onClick={() => onTab(id)}>{icon}{label}</button>
        ))}
      </div>

      {error ? <div className="inline-alert inline-alert-error" role="alert">{error}</div> : null}

      {tab === 'camera' ? (
        <div id="source-panel-camera" role="tabpanel" aria-labelledby="source-tab-camera" className="source-panel">
          <div className="source-panel-head"><p className="helper">Cameras connected to the computer running ElderCare Vision.</p><button type="button" className="btn btn-ghost btn-sm" onClick={scan} disabled={scanning}><RefreshCw aria-hidden="true" className={scanning ? 'spin' : undefined} />{scanning ? 'Scanning…' : 'Scan again'}</button></div>
          {cameras === null || (scanning && cameras.length === 0) ? <p className="helper" role="status">Looking for cameras…</p> : cameras.length === 0 ? (
            <div className="inline-alert inline-alert-info" role="status"><Camera aria-hidden="true" /><span><strong>No camera found.</strong> Plug a webcam into this computer, check that Windows allows apps to use the camera (Settings → Privacy &amp; security → Camera), close other apps using it, then scan again. You can still analyse a dataset clip or your own video.</span></div>
          ) : (
            <ul className="choice-list" role="radiogroup" aria-label="Detected cameras">
              {cameras.map((cam) => {
                const checked = picked?.source_type === 'webcam' && picked.source === String(cam.index);
                return <li key={cam.index}><button type="button" role="radio" aria-checked={checked} className="choice" disabled={disabled} onClick={() => onPick({ source_type: 'webcam', source: String(cam.index), label: cam.label, expected: null })}>
                  <span className="choice-icon"><Video aria-hidden="true" /></span>
                  <span className="choice-text"><strong>{cam.label}</strong><small>{cam.in_use ? 'Already streaming' : cam.width ? `${cam.width} × ${cam.height} · ready` : 'Ready'}</small></span>
                  {cam.in_use ? <span className="tag tag-blue">Live</span> : null}
                </button></li>;
              })}
            </ul>
          )}
        </div>
      ) : null}

      {tab === 'dataset' ? (
        <div id="source-panel-dataset" role="tabpanel" aria-labelledby="source-tab-dataset" className="source-panel">
          <p className="helper">Labelled URFD recordings. Each clip shows whether it contains a fall, so you can check the detector against a known answer.</p>
          {samples.length === 0 ? <div className="inline-alert inline-alert-info" role="status"><Database aria-hidden="true" /><span>No dataset clips found. Put the URFD videos in <code>datasets/raw/urfd/</code> on the server.</span></div> : <>
            <div className="source-filters">
              <div className="segmented segmented-sm" role="group" aria-label="Filter clips">
                {([['all', `All ${samples.length}`], ['fall', `Falls ${samples.filter((f) => f.expected === 'fall').length}`], ['no_fall', `No fall ${samples.filter((f) => f.expected === 'no_fall').length}`]] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}
              </div>
              <label className="sr-only" htmlFor="clip-search">Search clips</label>
              <input id="clip-search" type="search" placeholder="Search, e.g. 07" value={query} onChange={(event) => setQuery(event.target.value)} />
            </div>
            <ul className="choice-list source-scroll" role="radiogroup" aria-label="Dataset clips">
              {visibleSamples.map((file) => (
                <li key={file.ref}><button type="button" role="radio" aria-checked={picked?.source === file.ref} className="choice" disabled={disabled} onClick={() => pickFile(file)}>
                  <span className="choice-icon"><FileVideo aria-hidden="true" /></span>
                  <span className="choice-text"><strong>{clipTitle(file.name)}</strong><small>{file.name} · {size(file.size_bytes)}</small></span>
                  <ExpectedTag expected={file.expected} />
                </button></li>
              ))}
              {visibleSamples.length === 0 ? <li className="helper">No clips match.</li> : null}
            </ul>
          </>}
        </div>
      ) : null}

      {tab === 'upload' ? (
        <div id="source-panel-upload" role="tabpanel" aria-labelledby="source-tab-upload" className="source-panel">
          <button
            type="button"
            className={`dropzone${dragging ? ' is-dragging' : ''}`}
            disabled={disabled || progress !== null}
            onClick={() => fileInput.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <Upload aria-hidden="true" />
            <strong>{progress !== null ? `Uploading… ${Math.round(progress * 100)}%` : 'Drop a video here or browse'}</strong>
            <small>MP4, AVI, MOV, MKV or WebM · up to 1 GB · kept on this server</small>
          </button>
          {progress !== null ? <div className="progress-track" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress"><span style={{ width: `${Math.round(progress * 100)}%` }} /></div> : null}
          {progress !== null ? <button type="button" className="btn btn-ghost btn-sm" onClick={() => uploadAbort.current?.abort()}>Cancel upload</button> : null}
          <input ref={fileInput} type="file" accept={ACCEPT} hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload(file); }} />
          <p className="section-label">Your videos</p>
          {uploads.length === 0 ? <p className="helper">Nothing uploaded yet.</p> : (
            <ul className="choice-list source-scroll" role="radiogroup" aria-label="Uploaded videos">
              {uploads.map((file) => (
                <li key={file.ref} className="choice-row">
                  <button type="button" role="radio" aria-checked={picked?.source === file.ref} className="choice" disabled={disabled} onClick={() => pickFile(file)}>
                    <span className="choice-icon"><FileVideo aria-hidden="true" /></span>
                    <span className="choice-text"><strong>{file.name}</strong><small>{size(file.size_bytes)}</small></span>
                    <span />
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" aria-label={`Delete ${file.name}`} onClick={() => void remove(file)} disabled={disabled}><Trash2 aria-hidden="true" /></button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
