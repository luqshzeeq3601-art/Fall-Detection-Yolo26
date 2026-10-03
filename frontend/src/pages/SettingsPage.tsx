import { Activity, Bell, Camera, CheckCircle, Database, Download, Pencil, Save, ShieldCheck, Trash2, Users } from 'lucide-react';
import { useEffect, useState, type FormEvent, type JSX, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client.ts';
import { authApi, cameraApi, incidentApi, type User, type WorkspaceSettings } from '../api/platform.ts';
import type { Camera as CameraRow } from '../api/types.ts';
import { NoticeDialog } from '../components/common/Dialog.tsx';
import { Card, PageHeader } from '../components/common/Ui.tsx';
import { ErrorState, LoadingState } from '../components/common/States.tsx';
import { useAuth } from '../features/auth/useAuth.ts';
import { useWorkspaceSettings } from '../features/settings/useWorkspaceSettings.ts';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { cameraStatusMeta } from '../utils/status.ts';
import './SettingsPage.css';

const TABS = [
  { id: 'detection', label: 'Detection', icon: Activity },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'cameras', label: 'Cameras', icon: Camera },
  { id: 'data', label: 'Data & privacy', icon: ShieldCheck },
  { id: 'account', label: 'Account', icon: Users },
] as const;
type TabId = (typeof TABS)[number]['id'];
const SAVED_TABS: TabId[] = ['detection', 'alerts', 'data'];
const RETENTION: [string, number | null][] = [['Keep until deleted', null], ['1 day', 1], ['7 days', 7], ['30 days', 30], ['90 days', 90]];

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : fallback;
}

function Toggle({ label, detail, checked, onChange }: { label: string; detail?: string; checked: boolean; onChange: (value: boolean) => void }): JSX.Element {
  return <label className="setting-toggle"><span><strong>{label}</strong>{detail ? <small>{detail}</small> : null}</span><input type="checkbox" role="switch" checked={checked} onChange={(event) => onChange(event.target.checked)} aria-label={label} /><span className="toggle-track" aria-hidden="true" /></label>;
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }): JSX.Element {
  return <section className="settings-block"><header><h2>{title}</h2><p>{description}</p></header><div className="settings-block-body">{children}</div></section>;
}

function RenameCamera({ camera, onClose, onSaved }: { camera: CameraRow; onClose: () => void; onSaved: () => void }): JSX.Element {
  const [name, setName] = useState(camera.name);
  const [error, setError] = useState('');
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    try { await cameraApi.update(camera.id, { name: name.trim() }); onSaved(); } catch (reason) { setError(message(reason, 'Rename failed.')); }
  }
  return (
    <NoticeDialog title="Rename camera" onClose={onClose}>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="camera-name">Name shown on incidents and alerts</label>
        <input id="camera-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} placeholder="e.g. Living room" />
        {error ? <p className="decision-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={!name.trim()}>Save name</button>
      </form>
    </NoticeDialog>
  );
}

function CamerasTab(): JSX.Element {
  const { cameras } = useDashboardContext();
  const [renaming, setRenaming] = useState<CameraRow | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  async function setEnabled(camera: CameraRow, enabled: boolean): Promise<void> {
    try { await cameraApi.update(camera.id, { enabled }); cameras.reload(); setNote({ ok: true, text: `${camera.name} ${enabled ? 'enabled' : 'disabled'}.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Update failed.') }); }
  }
  async function remove(camera: CameraRow): Promise<void> {
    if (!window.confirm(`Delete “${camera.name}”? This cannot be undone.`)) return;
    try { await cameraApi.remove(camera.id); cameras.reload(); setNote({ ok: true, text: `${camera.name} deleted.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Delete failed.') }); }
  }
  return (
    <Section title="Cameras" description="A camera is added automatically the first time you start it (or analyse a video) in Live monitor. Rename cameras so incidents say where they happened.">
      {note ? <div className={`inline-alert ${note.ok ? 'inline-alert-success' : 'inline-alert-error'}`} role="status">{note.text}</div> : null}
      {cameras.loading && !cameras.data ? <LoadingState label="Loading cameras…" /> : cameras.error ? <ErrorState message={cameras.error} onRetry={cameras.reload} /> : (cameras.data ?? []).length === 0 ? (
        <p className="helper">No cameras yet. <Link to="/app/surveillance">Start one in Live monitor →</Link></p>
      ) : (
        <ul className="settings-camera-list">
          {(cameras.data ?? []).map((camera) => {
            const meta = cameraStatusMeta(camera.status);
            return (
              <li key={camera.id}>
                <span className="settings-camera-name"><strong>{camera.name}</strong><small>{camera.id} · <span className={`status status-${meta.tone}`}>{meta.label}</span></small></span>
                <label className="setting-toggle setting-toggle-inline"><span className="sr-only">Enable {camera.name}</span><input type="checkbox" role="switch" checked={camera.enabled !== false} onChange={(event) => void setEnabled(camera, event.target.checked)} aria-label={`Enable ${camera.name}`} /><span className="toggle-track" aria-hidden="true" /></label>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRenaming(camera)}><Pencil aria-hidden="true" />Rename</button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => void remove(camera)} aria-label={`Delete ${camera.name}`}><Trash2 aria-hidden="true" /></button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="helper">Disabling a camera stops its stream and prevents new starts. Cameras with recorded incidents can only be disabled, not deleted.</p>
      {renaming ? <RenameCamera camera={renaming} onClose={() => setRenaming(null)} onSaved={() => { setRenaming(null); cameras.reload(); setNote({ ok: true, text: 'Camera renamed.' }); }} /> : null}
    </Section>
  );
}

function AccountTab(): JSX.Element {
  const { user } = useAuth();
  const [team, setTeam] = useState<User[]>([]);
  const [passwords, setPasswords] = useState({ current: '', next: '' });
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { authApi.team().then(setTeam).catch(() => undefined); }, []);
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    try { await authApi.changePassword(passwords.current, passwords.next); setPasswords({ current: '', next: '' }); setNote({ ok: true, text: 'Password changed.' }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Password was not changed.') }); }
  }
  return (
    <>
      <Section title="Your account" description="Signed-in operators are recorded as the reviewer on every decision they make.">
        <dl className="kv"><dt>Name</dt><dd>{user?.full_name}</dd><dt>Email</dt><dd>{user?.email}</dd><dt>Access</dt><dd>{user?.role === 'admin' ? 'Workspace admin' : 'Operator'}{user?.job_role ? ` · ${user.job_role === 'caregiver' ? 'Caregiver' : 'Facility admin'}` : ''}</dd></dl>
      </Section>
      <Section title="Change password" description="At least 8 characters with a letter and a number.">
        <form className="settings-password" onSubmit={(event) => void submit(event)}>
          <label htmlFor="current-password">Current password</label>
          <input id="current-password" type="password" autoComplete="current-password" value={passwords.current} onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} required />
          <label htmlFor="new-password">New password</label>
          <input id="new-password" type="password" autoComplete="new-password" minLength={8} value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} required />
          {note ? <div className={`inline-alert ${note.ok ? 'inline-alert-success' : 'inline-alert-error'}`} role="status">{note.text}</div> : null}
          <button type="submit" className="btn btn-secondary">Change password</button>
        </form>
      </Section>
      <Section title={`Team · ${team.length}`} description="Everyone with an account on this server. New people join from the sign-up page.">
        <ul className="settings-team">{team.map((member) => <li key={member.id}><strong>{member.full_name}</strong><small>{member.email} · {member.role === 'admin' ? 'Admin' : 'Operator'}</small></li>)}</ul>
      </Section>
    </>
  );
}

export function SettingsPage(): JSX.Element {
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab: TabId = TABS.some((item) => item.id === requested) ? (requested as TabId) : 'detection';
  const workspace = useWorkspaceSettings();
  const [draft, setDraft] = useState<WorkspaceSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const [exporting, setExporting] = useState(false);
  const saved = workspace.data?.settings ?? null;
  const defaults = workspace.data?.frozen_defaults;
  const current = draft ?? saved;
  const dirty = Boolean(draft && saved && JSON.stringify(draft) !== JSON.stringify(saved));
  const permission = typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
  const frozenThreshold = defaults?.fall_threshold ?? 0.55;
  const frozenDown = defaults?.min_down_sec ?? 0.45;

  function patch(value: Partial<WorkspaceSettings>): void {
    if (!current) return;
    setDraft({ ...current, ...value });
    setToast(null);
  }
  function selectTab(id: TabId): void {
    const next = new URLSearchParams(params);
    next.set('tab', id);
    setParams(next, { replace: true });
  }
  async function save(): Promise<void> {
    if (!draft) return;
    setSaving(true);
    try { await workspace.save(draft); setDraft(null); setToast({ ok: true, text: 'Settings saved. Detection changes apply the next time a source starts.' }); } catch (reason) { setToast({ ok: false, text: message(reason, 'Settings were not saved.') }); } finally { setSaving(false); }
  }
  async function enableNotifications(value: boolean): Promise<void> {
    if (value && typeof Notification !== 'undefined' && Notification.permission === 'default') await Notification.requestPermission();
    patch({ browser_alerts: value });
  }
  async function exportDataset(): Promise<void> {
    setExporting(true);
    try { const count = await incidentApi.exportDataset({ includeUncertain: current?.export_include_uncertain }); setToast({ ok: true, text: `Downloaded ${count} reviewed incident${count === 1 ? '' : 's'}.` }); } catch (reason) { setToast({ ok: false, text: message(reason, 'Export failed.') }); } finally { setExporting(false); }
  }

  let body: ReactNode;
  if (tab === 'cameras') body = <CamerasTab />;
  else if (tab === 'account') body = <AccountTab />;
  else if (!current) body = workspace.error ? <ErrorState message={workspace.error} onRetry={workspace.reload} /> : <LoadingState label="Loading settings…" />;
  else if (tab === 'detection') body = (
    <>
      <Section title="Sensitivity" description="How readily the detector raises an alert. The published results (98.3% recall, 96.7% precision) were measured with the frozen calibration.">
        <Toggle label="Use the calibrated defaults (recommended)" detail={`Trigger ${frozenThreshold.toFixed(2)} · must stay down ${frozenDown.toFixed(2)} s`} checked={current.fall_threshold === null && current.min_down_sec === null} onChange={(useDefault) => patch(useDefault ? { fall_threshold: null, min_down_sec: null } : { fall_threshold: frozenThreshold, min_down_sec: frozenDown })} />
        <fieldset className="settings-sliders" disabled={current.fall_threshold === null && current.min_down_sec === null}>
          <label htmlFor="fall-threshold">Trigger threshold <strong>{(current.fall_threshold ?? frozenThreshold).toFixed(2)}</strong></label>
          <input id="fall-threshold" type="range" min="0.2" max="0.8" step="0.05" value={current.fall_threshold ?? frozenThreshold} onChange={(event) => patch({ fall_threshold: Number(event.target.value) })} />
          <div className="slider-scale"><span>Lower · catches more, more false alarms</span><span>Higher · fewer alerts</span></div>
          <label htmlFor="min-down">Time on the floor before alerting <strong>{(current.min_down_sec ?? frozenDown).toFixed(2)} s</strong></label>
          <input id="min-down" type="range" min="0.1" max="1.5" step="0.05" value={current.min_down_sec ?? frozenDown} onChange={(event) => patch({ min_down_sec: Number(event.target.value) })} />
          <div className="slider-scale"><span>Faster alert</span><span>Fewer brief-dip alerts</span></div>
        </fieldset>
      </Section>
      <Section title="Video overlay" description="What is drawn on the live video, snapshots and clips.">
        <Toggle label="Body skeleton" checked={current.show_skeleton} onChange={(show_skeleton) => patch({ show_skeleton })} />
        <Toggle label="Person box and label" checked={current.show_bbox} onChange={(show_bbox) => patch({ show_bbox })} />
        <Toggle label="Blur heads" detail="Hides faces in the video shown on screen. Detection is unaffected." checked={current.blur_faces} onChange={(blur_faces) => patch({ blur_faces })} />
      </Section>
    </>
  );
  else if (tab === 'alerts') body = (
    <Section title="When a fall is confirmed" description="Every open dashboard shows an on-screen alert. Choose what else happens.">
      <Toggle label="Desktop notification" detail={permission === 'denied' ? 'Blocked by the browser: allow notifications for this site in the browser settings.' : permission === 'unsupported' ? 'Not supported in this browser.' : 'Shows even when this tab is in the background.'} checked={current.browser_alerts} onChange={(value) => void enableNotifications(value)} />
      <Toggle label="Alert sound" detail="Three short tones in open dashboard tabs." checked={current.alert_sound} onChange={(alert_sound) => patch({ alert_sound })} />
      <button type="button" className="btn btn-secondary" onClick={() => { if (permission === 'granted') { new Notification('ElderCare Vision', { body: 'Desktop notifications are working.' }); setToast({ ok: true, text: 'Test notification sent.' }); } else setToast({ ok: false, text: 'Notifications are not allowed yet: turn on “Desktop notification” and accept the browser prompt.' }); }}><Bell aria-hidden="true" />Send a test notification</button>
      <p className="helper">Text messages, phone calls and emergency escalation are not connected.</p>
    </Section>
  );
  else body = (
    <>
      <Section title="Keep incidents for" description="Live video is never recorded. Each incident stores three keyframes and the detector's scores.">
        <label className="sr-only" htmlFor="retention">Retention</label>
        <select id="retention" value={current.retention_days ?? ''} onChange={(event) => patch({ retention_days: event.target.value ? Number(event.target.value) : null })}>
          {RETENTION.map(([label, days]) => <option key={label} value={days ?? ''}>{label}</option>)}
        </select>
        {current.retention_days ? <div className="inline-alert inline-alert-error" role="note"><Trash2 aria-hidden="true" /><span>Incidents older than {current.retention_days} day{current.retention_days === 1 ? '' : 's'} and their keyframes will be permanently deleted (checked every hour).</span></div> : null}
      </Section>
      <Section title="Reviewed dataset" description="Export your decisions as a JSON Lines file for retraining or audit.">
        <Toggle label="Include “Unsure” decisions" detail="Off by default: only real falls and false alarms are exported." checked={current.export_include_uncertain} onChange={(export_include_uncertain) => patch({ export_include_uncertain })} />
        <button type="button" className="btn btn-secondary" disabled={exporting} onClick={() => void exportDataset()}><Download aria-hidden="true" />{exporting ? 'Preparing…' : 'Download reviewed dataset'}</button>
      </Section>
    </>
  );

  return (
    <div className="settings-page">
      <PageHeader title="Settings" subtitle="Tune detection and alerts, manage cameras and data, and update your account. Saved on the server for everyone." />
      {toast ? <div className={`settings-toast${toast.ok ? '' : ' is-error'}`} role="status"><CheckCircle aria-hidden="true" /><span>{toast.text}</span><button type="button" className="icon-button" aria-label="Dismiss message" onClick={() => setToast(null)}>×</button></div> : null}
      <div className="settings-layout">
        <nav className="settings-navigation" aria-label="Settings sections">
          {TABS.map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => selectTab(id)}><Icon aria-hidden="true" /><span>{label}</span></button>)}
        </nav>
        <Card className="settings-panel" title={TABS.find((item) => item.id === tab)?.label} icon={(() => { const Icon = TABS.find((item) => item.id === tab)?.icon ?? Database; return <Icon />; })()}>{body}</Card>
      </div>
      {SAVED_TABS.includes(tab) ? (
        <footer className="settings-savebar">
          <span>{dirty ? 'You have unsaved changes' : 'All changes saved'}</span>
          <button type="button" className="btn btn-ghost" disabled={!dirty || saving} onClick={() => { setDraft(null); setToast(null); }}>Discard</button>
          <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={() => void save()}><Save aria-hidden="true" />{saving ? 'Saving…' : 'Save changes'}</button>
        </footer>
      ) : null}
    </div>
  );
}
