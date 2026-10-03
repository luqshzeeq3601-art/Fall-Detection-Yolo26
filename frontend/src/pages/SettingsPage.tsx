import { Activity, Bell, Camera, CheckCircle, Database, Download, Eye, EyeOff, History, Info, KeyRound, LockKeyhole, Mail, Pencil, Plus, Save, ShieldCheck, Trash2, User, UserPlus, Users } from 'lucide-react';
import { useEffect, useState, type FormEvent, type JSX, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { BENCHMARK } from '../api/benchmarkData.ts';
import { ApiError } from '../api/client.ts';
import { auditApi, authApi, cameraApi, incidentApi, liveApi, type AuditEvent, type CameraSourceConfig, type DetectedCamera, type TeamMember, type WorkspaceSettings } from '../api/platform.ts';
import type { Camera as CameraRow } from '../api/types.ts';
import { NoticeDialog } from '../components/common/Dialog.tsx';
import { Card, PageHeader } from '../components/common/Ui.tsx';
import { ErrorState, LoadingState } from '../components/common/States.tsx';
import { roleLabel } from '../features/auth/roles.ts';
import { useAuth } from '../features/auth/useAuth.ts';
import { useWorkspaceSettings } from '../features/settings/useWorkspaceSettings.ts';
import { useDashboardContext } from '../hooks/useDashboardContext.ts';
import { parseApiTime } from '../utils/format.ts';
import { cameraStatusMeta } from '../utils/status.ts';
import './SettingsPage.css';

const ALL_TABS = [
  { id: 'detection', label: 'Detection', icon: Activity },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'cameras', label: 'Cameras', icon: Camera },
  { id: 'data', label: 'Data & privacy', icon: ShieldCheck },
  { id: 'account', label: 'Account', icon: Users },
  { id: 'activity', label: 'Activity log', icon: History },
] as const;

const CAREGIVER_TABS = [
  { id: 'account', label: 'Account', icon: Users },
] as const;

type TabId = (typeof ALL_TABS)[number]['id'];
const SAVED_TABS: TabId[] = ['detection', 'alerts', 'data'];
const ESCALATION: [string, number | null][] = [['Off', null], ['After 1 minute', 60], ['After 2 minutes', 120], ['After 5 minutes', 300], ['After 10 minutes', 600]];
const RETENTION: [string, number | null][] = [['Keep until deleted', null], ['1 day', 1], ['7 days', 7], ['30 days', 30], ['90 days', 90]];

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : fallback;
}

function Toggle({ label, detail, checked, onChange }: { label: string; detail?: string; checked: boolean; onChange: (value: boolean) => void }): JSX.Element {
  return <label className="setting-toggle"><span><strong>{label}</strong>{detail ? <small>{detail}</small> : null}</span><input type="checkbox" role="switch" checked={checked} onChange={(event) => onChange(event.target.checked)} aria-label={label} /><span className="toggle-track" aria-hidden="true" /></label>;
}

function Section({ title, description, children, icon, action, className = '' }: { title: string; description: string; children: ReactNode; icon?: ReactNode; action?: ReactNode; className?: string }): JSX.Element {
  return (
    <section className={`settings-block ${className}`.trim()} aria-label={title}>
      <header className="settings-section-header">
        {icon ? <span className="settings-section-icon" aria-hidden="true">{icon}</span> : null}
        <div className="settings-section-copy"><h2>{title}</h2><p>{description}</p></div>
        {action ? <div className="settings-section-action">{action}</div> : null}
      </header>
      <div className="settings-block-body">{children}</div>
    </section>
  );
}

/** Webcams the server can see, for binding a camera to one. */
function WebcamSelect({ id, value, onChange, current }: { id: string; value: string; onChange: (value: string) => void; current?: string | null }): JSX.Element {
  const [found, setFound] = useState<DetectedCamera[] | null>(null);
  useEffect(() => {
    liveApi.detectCameras().then((result) => setFound(result.cameras)).catch(() => setFound([]));
  }, []);
  return (
    <>
      <label htmlFor={id}>Webcam</label>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{current ? `Keep Webcam ${current}` : 'Choose later'}</option>
        {(found ?? []).map((cam) => <option key={cam.index} value={String(cam.index)}>{cam.label}{cam.in_use ? ' (in use)' : ''}</option>)}
      </select>
      <p className="helper">{found === null ? 'Looking for webcams…' : found.length === 0 ? 'No webcam found on the server right now.' : 'Falls seen by this webcam are filed under this room.'}</p>
    </>
  );
}

function EditCamera({ camera, webcam, onClose, onSaved }: { camera: CameraRow; webcam: string | null; onClose: () => void; onSaved: () => void }): JSX.Element {
  const [name, setName] = useState(camera.name);
  const [nextWebcam, setNextWebcam] = useState('');
  const [error, setError] = useState('');
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    try {
      if (name.trim() !== camera.name) await cameraApi.update(camera.id, { name: name.trim() });
      if (nextWebcam && nextWebcam !== webcam) await cameraApi.setWebcam(camera.id, nextWebcam);
      onSaved();
    } catch (reason) { setError(message(reason, 'Camera was not saved.')); }
  }
  return (
    <NoticeDialog title="Edit camera" onClose={onClose}>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="camera-name">Name shown on incidents and alerts</label>
        <input id="camera-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} placeholder="e.g. Living room" />
        <WebcamSelect id="camera-webcam" value={nextWebcam} onChange={setNextWebcam} current={webcam} />
        {error ? <p className="decision-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={!name.trim()}>Save camera</button>
      </form>
    </NoticeDialog>
  );
}

function CameraSensitivity({ value, fallback, onChange }: { value: WorkspaceSettings['camera_sensitivity']; fallback: number; onChange: (next: WorkspaceSettings['camera_sensitivity']) => void }): JSX.Element | null {
  const { cameras } = useDashboardContext();
  const rooms = (cameras.data ?? []).filter((camera) => camera.id !== 'video-analysis');
  if (rooms.length === 0) return null;
  function set(id: string, threshold: number | null): void {
    const next = { ...value };
    if (threshold === null) delete next[id];
    else next[id] = { fall_threshold: threshold, min_down_sec: next[id]?.min_down_sec ?? null };
    onChange(next);
  }
  return (
    <Section title="Per-camera sensitivity" description="Override the trigger threshold for a room that alerts too often or too rarely. Other cameras use the workspace setting above.">
      <ul className="settings-camera-sensitivity">
        {rooms.map((camera) => {
          const override = value[camera.id]?.fall_threshold ?? null;
          return (
            <li key={camera.id}>
              <Toggle label={camera.name} detail={override === null ? `Workspace setting (${fallback.toFixed(2)})` : `Own threshold ${override.toFixed(2)}`} checked={override !== null} onChange={(on) => set(camera.id, on ? fallback : null)} />
              {override !== null ? (
                <input type="range" min="0.2" max="0.8" step="0.05" value={override} aria-label={`Trigger threshold for ${camera.name}`} onChange={(event) => set(camera.id, Number(event.target.value))} />
              ) : null}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/** In-app confirmation for irreversible actions (replaces window.confirm). */
function ConfirmDialog({ title, children, confirmLabel, onConfirm, onClose }: { title: string; children: ReactNode; confirmLabel: string; onConfirm: () => void; onClose: () => void }): JSX.Element {
  return (
    <NoticeDialog title={title} onClose={onClose}>
      {children}
      <div className="settings-dialog-actions">
        <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button type="button" className="btn btn-danger" onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </NoticeDialog>
  );
}

function slug(name: string): string {
  const base = name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'camera';
  return `cam-${base}-${Math.random().toString(36).slice(2, 6)}`;
}

function AddCameraDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (name: string) => void }): JSX.Element {
  const [name, setName] = useState('');
  const [webcam, setWebcam] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const camera = await cameraApi.create(slug(name), name.trim());
      if (webcam) await cameraApi.setWebcam(camera.id, webcam);
      onCreated(camera.name);
    } catch (reason) {
      setError(message(reason, 'Camera was not added.'));
    } finally {
      setSaving(false);
    }
  }
  return (
    <NoticeDialog title="Add camera" onClose={onClose}>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="new-camera-name">Room or place</label>
        <input id="new-camera-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} placeholder="e.g. Living room" />
        <WebcamSelect id="new-camera-webcam" value={webcam} onChange={setWebcam} />
        {error ? <p className="decision-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={saving || !name.trim()}>{saving ? 'Adding…' : 'Add camera'}</button>
      </form>
    </NoticeDialog>
  );
}

function CamerasTab(): JSX.Element {
  const { cameras } = useDashboardContext();
  const { user } = useAuth();
  const [renaming, setRenaming] = useState<CameraRow | null>(null);
  const [deleting, setDeleting] = useState<CameraRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [sources, setSources] = useState<CameraSourceConfig[]>([]);
  const reloadSources = (): void => { cameraApi.sources().then(setSources).catch(() => undefined); };
  useEffect(reloadSources, []);
  const sourceOf = (id: string): string | null => {
    const row = sources.find((item) => item.camera_id === id);
    return row ? (row.source_type === 'webcam' ? `Webcam ${row.source}` : 'Video file') : null;
  };
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  async function setEnabled(camera: CameraRow, enabled: boolean): Promise<void> {
    try { await cameraApi.update(camera.id, { enabled }); cameras.reload(); setNote({ ok: true, text: `${camera.name} ${enabled ? 'enabled' : 'disabled'}.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Update failed.') }); }
  }
  async function remove(camera: CameraRow): Promise<void> {
    setDeleting(null);
    try { await cameraApi.remove(camera.id); cameras.reload(); setNote({ ok: true, text: `${camera.name} deleted.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Delete failed.') }); }
  }
  return (
    <Section title="Cameras" description="Add a camera for each room and bind its webcam, so incidents and alerts name the room. Webcams started in Live monitor without a room appear here automatically.">
      <div className="settings-team-actions">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAdding(true)}><Plus aria-hidden="true" />Add camera</button>
      </div>
      {note ? <div className={`inline-alert ${note.ok ? 'inline-alert-success' : 'inline-alert-error'}`} role="status">{note.text}</div> : null}
      {cameras.loading && !cameras.data ? <LoadingState label="Loading cameras…" /> : cameras.error ? <ErrorState message={cameras.error} onRetry={cameras.reload} /> : (cameras.data ?? []).length === 0 ? (
        <p className="helper">No cameras yet. <Link to="/app/surveillance">Start one in Live monitor →</Link></p>
      ) : (
        <ul className="settings-camera-list">
          {(cameras.data ?? []).map((camera) => {
            const meta = cameraStatusMeta(camera.status);
            return (
              <li key={camera.id}>
                <span className="settings-camera-name"><strong>{camera.name}</strong><small>{sourceOf(camera.id) ? `${sourceOf(camera.id)} · ` : ''}<span className={`status status-${meta.tone}`}>{meta.label}</span></small></span>
                <label className="setting-toggle setting-toggle-inline"><span className="sr-only">Enable {camera.name}</span><input type="checkbox" role="switch" checked={camera.enabled !== false} onChange={(event) => void setEnabled(camera, event.target.checked)} aria-label={`Enable ${camera.name}`} /><span className="toggle-track" aria-hidden="true" /></label>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRenaming(camera)}><Pencil aria-hidden="true" />Edit</button>
                {user?.role === 'admin' ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDeleting(camera)} aria-label={`Delete ${camera.name}`}><Trash2 aria-hidden="true" /></button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <p className="helper">Disabling a camera stops its stream and prevents new starts. Cameras with recorded incidents can only be disabled, not deleted.</p>
      {renaming ? <EditCamera camera={renaming} webcam={sources.find((item) => item.camera_id === renaming.id && item.source_type === 'webcam')?.source ?? null} onClose={() => setRenaming(null)} onSaved={() => { setRenaming(null); cameras.reload(); reloadSources(); setNote({ ok: true, text: 'Camera saved.' }); }} /> : null}
      {adding ? <AddCameraDialog onClose={() => setAdding(false)} onCreated={(name) => { setAdding(false); cameras.reload(); reloadSources(); setNote({ ok: true, text: `${name} added.` }); }} /> : null}
      {deleting ? (
        <ConfirmDialog title="Delete camera" confirmLabel="Delete camera" onClose={() => setDeleting(null)} onConfirm={() => void remove(deleting)}>
          <p>Delete “{deleting.name}”? This cannot be undone.</p>
        </ConfirmDialog>
      ) : null}
    </Section>
  );
}

function AddMemberDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }): JSX.Element {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [jobRole, setJobRole] = useState<'caregiver' | 'facility-admin'>('caregiver');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      await authApi.createUser({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role: jobRole === 'facility-admin' ? 'admin' : 'operator',
        job_role: jobRole,
      });
      onCreated();
    } catch (reason) {
      setError(message(reason, 'Could not add team member.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <NoticeDialog title="Add team member" onClose={onClose}>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="member-name">Full name</label>
        <input id="member-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required placeholder="e.g. Jane Doe" />
        <label htmlFor="member-email">Email address</label>
        <input id="member-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="e.g. jane@facility.com" />
        <label htmlFor="member-password">Initial password</label>
        <input id="member-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} placeholder="At least 8 chars with letter & number" />
        <label htmlFor="member-role">Assigned role</label>
        <select id="member-role" value={jobRole} onChange={(e) => setJobRole(e.target.value as 'caregiver' | 'facility-admin')}>
          <option value="caregiver">Caregiver: monitoring and incident review</option>
          <option value="facility-admin">Admin: also settings, cameras and team</option>
        </select>
        {error ? <p className="decision-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={saving || !fullName.trim() || !email.trim() || !password}>
          {saving ? 'Creating…' : 'Add member'}
        </button>
      </form>
    </NoticeDialog>
  );
}

/** Desktop notification permission is per browser, so every signed-in user grants it on their own device. */
const AUDIT_TEXT: Record<string, string> = {
  'settings.updated': 'Changed settings',
  'camera.created': 'Added camera',
  'camera.updated': 'Changed camera',
  'camera.deleted': 'Deleted camera',
  'member.added': 'Added team member',
  'member.role_changed': 'Changed role',
  'member.password_reset': 'Reset password',
  'member.removed': 'Removed team member',
  'dataset.exported': 'Exported reviewed dataset',
  'video.uploaded': 'Uploaded video',
  'video.deleted': 'Deleted video',
  'retention.purged': 'Deleted old incidents',
};
const AUDIT_TIME = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function describeDetail(detail: Record<string, unknown> | null, cameraName: (id: string) => string): string {
  if (!detail) return '';
  return Object.entries(detail).map(([key, value]) => {
    if (key === 'camera_sensitivity' && value && typeof value === 'object') {
      const rooms = Object.entries(value as Record<string, { fall_threshold?: number | null }>).map(([id, item]) => `${cameraName(id)} ${item.fall_threshold ?? 'default'}`);
      return `per-camera threshold: ${rooms.length ? rooms.join(', ') : 'none'}`;
    }
    return `${key.replaceAll('_', ' ')}: ${value === null ? 'off' : typeof value === 'object' ? JSON.stringify(value) : String(value)}`;
  }).join(' · ');
}

function ActivityTab(): JSX.Element {
  const { cameras } = useDashboardContext();
  const cameraName = (id: string): string => cameras.data?.find((camera) => camera.id === id)?.name ?? id;
  const [page, setPage] = useState<{ items: AuditEvent[]; total: number } | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    auditApi.list(25, offset)
      .then((value) => { if (!cancelled) { setPage(value); setError(''); } })
      .catch((reason: unknown) => { if (!cancelled) setError(message(reason, 'Activity log unavailable.')); });
    return () => { cancelled = true; };
  }, [offset, attempt]);
  return (
    <Section title="Activity log" description="Changes to settings, cameras and the team, data exports and automatic deletions. Newest first.">
      {error ? <ErrorState message={error} onRetry={() => setAttempt((value) => value + 1)} /> : !page ? <LoadingState label="Loading activity…" /> : page.items.length === 0 ? <p className="helper">No changes recorded yet.</p> : (
        <>
          <ul className="settings-activity">
            {page.items.map((item) => (
              <li key={item.id}>
                <span><strong>{AUDIT_TEXT[item.action] ?? item.action}</strong>{item.target ? ` · ${item.target}` : ''}</span>
                <small>{item.actor ?? 'Unknown'} · {AUDIT_TIME.format(parseApiTime(item.created_at))}</small>
                {item.detail ? <small className="settings-activity-detail">{describeDetail(item.detail, cameraName)}</small> : null}
              </li>
            ))}
          </ul>
          <div className="settings-activity-pager">
            <button type="button" className="btn btn-ghost btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Newer</button>
            <span>{offset + 1}–{offset + page.items.length} of {page.total}</span>
            <button type="button" className="btn btn-ghost btn-sm" disabled={offset + 25 >= page.total} onClick={() => setOffset(offset + 25)}>Older</button>
          </div>
        </>
      )}
    </Section>
  );
}

function DeviceAlerts(): JSX.Element {
  const workspace = useWorkspaceSettings();
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(typeof Notification === 'undefined' ? 'unsupported' : Notification.permission);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState('');
  const enabledByAdmin = workspace.data?.settings.browser_alerts ?? true;
  async function allow(): Promise<void> {
    if (typeof Notification === 'undefined' || requesting) return;
    setRequesting(true);
    setError('');
    try {
      setPermission(await Notification.requestPermission());
    } catch (reason) {
      setError(message(reason, 'Notifications could not be allowed. Try again or check your browser settings.'));
    } finally {
      setRequesting(false);
    }
  }
  const status = !enabledByAdmin ? 'Your workspace admin has turned desktop notifications off.'
    : permission === 'granted' ? 'On: fall alerts show even when this tab is in the background.'
    : permission === 'denied' ? 'Blocked by the browser: allow notifications for this site in the browser settings.'
    : permission === 'unsupported' ? 'This browser does not support desktop notifications.'
    : 'Off: this browser has not been allowed to show notifications yet.';
  return (
    <Section
      title="Alerts on this device"
      description="Every open dashboard shows an on-screen alert when a fall is confirmed."
      icon={<Bell />}
      className="settings-device-alerts"
      action={enabledByAdmin && permission === 'default' ? (
        <button type="button" className="btn btn-primary settings-notification-button" disabled={requesting} onClick={() => void allow()}>
          <Bell aria-hidden="true" />{requesting ? 'Waiting for browser…' : 'Allow desktop notifications'}
        </button>
      ) : undefined}
    >
      <div className="settings-permission-note" role="status">
        <Info aria-hidden="true" />
        <div><p>Desktop notifications must be allowed separately in each browser.</p><p>{status}</p></div>
      </div>
      {error ? <p className="decision-error" role="alert">{error}</p> : null}
    </Section>
  );
}

function ResetPasswordDialog({ member, onClose, onSaved }: { member: TeamMember; onClose: () => void; onSaved: () => void }): JSX.Element {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    try { await authApi.updateUser(member.id, { new_password: password }); onSaved(); } catch (reason) { setError(message(reason, 'Password was not reset.')); }
  }
  return (
    <NoticeDialog title={`Reset password for ${member.full_name}`} onClose={onClose}>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="reset-password">New password</label>
        <input id="reset-password" type="password" autoComplete="new-password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required placeholder="At least 8 characters with a letter and a number" />
        <p className="helper">They are signed out everywhere and must sign in with this password. Share it with them directly.</p>
        {error ? <p className="decision-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={password.length < 8}>Reset password</button>
      </form>
    </NoticeDialog>
  );
}

function TeamSection(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [addingMember, setAddingMember] = useState(false);
  const [resetting, setResetting] = useState<TeamMember | null>(null);
  const [removing, setRemoving] = useState<TeamMember | null>(null);
  const reload = (): void => { authApi.team().then(setTeam).catch(() => undefined); };
  useEffect(reload, []);
  async function changeRole(member: TeamMember, role: 'admin' | 'operator'): Promise<void> {
    try { await authApi.updateUser(member.id, { role }); reload(); setNote({ ok: true, text: `${member.full_name} is now ${role === 'admin' ? 'an admin' : 'a caregiver'}.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Role was not changed.') }); }
  }
  async function remove(member: TeamMember): Promise<void> {
    setRemoving(null);
    try { await authApi.removeUser(member.id); reload(); setNote({ ok: true, text: `${member.full_name} removed.` }); } catch (reason) { setNote({ ok: false, text: message(reason, 'Member was not removed.') }); }
  }
  return (
    <Section
      title={`Team · ${team.length}`}
      description={isAdmin ? 'Everyone who can sign in to this workspace. Add caregivers and admins, change roles, reset passwords or remove accounts.' : 'Everyone who can sign in to this workspace.'}
      icon={<Users />}
      className="settings-account-team"
    >
      {note ? <div className={`inline-alert ${note.ok ? 'inline-alert-success' : 'inline-alert-error'}`} role="status">{note.text}</div> : null}
      {isAdmin ? (
        <div className="settings-team-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAddingMember(true)}><UserPlus aria-hidden="true" />Add team member</button>
        </div>
      ) : null}
      <ul className="settings-team">
        {team.map((member) => {
          const self = member.id === user?.id;
          return (
            <li key={member.id}>
              <span className="settings-team-identity"><strong>{member.full_name}{self ? ' (you)' : ''}</strong><small>{member.email ? `${member.email} · ` : ''}{roleLabel(member.role)}</small></span>
              {isAdmin && !self ? (
                <span className="settings-team-controls">
                  <label className="sr-only" htmlFor={`role-${member.id}`}>Role for {member.full_name}</label>
                  <select id={`role-${member.id}`} value={member.role === 'admin' ? 'admin' : 'operator'} onChange={(event) => void changeRole(member, event.target.value as 'admin' | 'operator')}>
                    <option value="operator">Caregiver</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setResetting(member)}><KeyRound aria-hidden="true" />Reset password</button>
                  <button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove ${member.full_name}`} onClick={() => setRemoving(member)}><Trash2 aria-hidden="true" /></button>
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {addingMember ? (
        <AddMemberDialog
          onClose={() => setAddingMember(false)}
          onCreated={() => { setAddingMember(false); reload(); setNote({ ok: true, text: 'Team member added. Share their starting password with them directly.' }); }}
        />
      ) : null}
      {resetting ? <ResetPasswordDialog member={resetting} onClose={() => setResetting(null)} onSaved={() => { setNote({ ok: true, text: `Password reset for ${resetting.full_name}.` }); setResetting(null); }} /> : null}
      {removing ? (
        <ConfirmDialog title="Remove team member" confirmLabel="Remove member" onClose={() => setRemoving(null)} onConfirm={() => void remove(removing)}>
          <p>Remove {removing.full_name}{removing.email ? ` (${removing.email})` : ''}? They can no longer sign in. Decisions they recorded stay in the incident history.</p>
        </ConfirmDialog>
      ) : null}
    </Section>
  );
}

function AccountTab(): JSX.Element {
  const { user } = useAuth();
  const [passwords, setPasswords] = useState({ current: '', next: '' });
  const [visible, setVisible] = useState({ current: false, next: false });
  const [savingPassword, setSavingPassword] = useState(false);
  const [profileNotice, setProfileNotice] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (savingPassword || !passwords.current || passwords.next.length < 8) return;
    setSavingPassword(true);
    setNote(null);
    try {
      await authApi.changePassword(passwords.current, passwords.next);
      setPasswords({ current: '', next: '' });
      setVisible({ current: false, next: false });
      setNote({ ok: true, text: 'Password changed.' });
    } catch (reason) {
      setNote({ ok: false, text: message(reason, 'Password was not changed.') });
    } finally {
      setSavingPassword(false);
    }
  }
  return (
    <div className="settings-account-stack">
      <Section
        title="Account"
        description="Your profile and role information."
        icon={<Users />}
        action={<button type="button" className="btn btn-secondary settings-edit-button" onClick={() => setProfileNotice(true)}><Pencil aria-hidden="true" />Edit</button>}
      >
        <dl className="settings-profile-details">
          <div><span className="settings-profile-icon" aria-hidden="true"><User /></span><dt>Name</dt><dd>{user?.full_name || 'Not available'}</dd></div>
          <div><span className="settings-profile-icon" aria-hidden="true"><Mail /></span><dt>Email</dt><dd>{user?.email || 'Not available'}</dd></div>
          <div><span className="settings-profile-icon" aria-hidden="true"><ShieldCheck /></span><dt>Role</dt><dd>{roleLabel(user?.role)}</dd></div>
        </dl>
      </Section>
      {user?.role !== 'admin' ? <DeviceAlerts /> : null}
      <Section title="Change password" description="At least 8 characters with a letter and a number." icon={<LockKeyhole />} className="settings-password-section">
        <form className="settings-password" onSubmit={(event) => void submit(event)} aria-busy={savingPassword}>
          <div className="settings-password-field">
            <label htmlFor="current-password">Current password</label>
            <div className="settings-password-input">
              <input id="current-password" type={visible.current ? 'text' : 'password'} autoComplete="current-password" value={passwords.current} onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} disabled={savingPassword} required />
              <button type="button" aria-label={visible.current ? 'Hide current password' : 'Show current password'} aria-pressed={visible.current} onClick={() => setVisible({ ...visible, current: !visible.current })}>
                {visible.current ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </div>
          </div>
          <div className="settings-password-field">
            <label htmlFor="new-password">New password</label>
            <div className="settings-password-input">
              <input id="new-password" type={visible.next ? 'text' : 'password'} autoComplete="new-password" aria-describedby="settings-password-help" minLength={8} value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} disabled={savingPassword} required />
              <button type="button" aria-label={visible.next ? 'Hide new password' : 'Show new password'} aria-pressed={visible.next} onClick={() => setVisible({ ...visible, next: !visible.next })}>
                {visible.next ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </div>
          </div>
          <span className="sr-only" id="settings-password-help">At least 8 characters with a letter and a number.</span>
          <button type="submit" className="btn btn-secondary settings-password-submit" disabled={savingPassword || !passwords.current || passwords.next.length < 8}>{savingPassword ? 'Updating…' : 'Update password'}</button>
          {note ? <div className={`inline-alert settings-password-result ${note.ok ? 'inline-alert-success' : 'inline-alert-error'}`} role={note.ok ? 'status' : 'alert'}>{note.text}</div> : null}
        </form>
      </Section>
      <TeamSection />
      {profileNotice ? <NoticeDialog title="Account editing unavailable" onClose={() => setProfileNotice(false)}><p>Your name, email and role are managed by your workspace. Profile changes are not available here yet.</p></NoticeDialog> : null}
    </div>
  );
}

export function SettingsPage(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const availableTabs = isAdmin ? ALL_TABS : CAREGIVER_TABS;
  const defaultTab: TabId = isAdmin ? 'detection' : 'account';
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab: TabId = availableTabs.some((item) => item.id === requested) ? (requested as TabId) : defaultTab;
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
  // Turning on or shortening retention deletes data once saved, so it needs an explicit confirmation.
  const shortensRetention = Boolean(draft?.retention_days && (saved?.retention_days === null || saved?.retention_days === undefined || draft.retention_days < saved.retention_days));
  const [confirmingRetention, setConfirmingRetention] = useState(false);
  async function save(confirmed = false): Promise<void> {
    if (!draft) return;
    if (shortensRetention && !confirmed) { setConfirmingRetention(true); return; }
    setConfirmingRetention(false);
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
  else if (tab === 'activity') body = <ActivityTab />;
  else if (!current) body = workspace.error ? <ErrorState message={workspace.error} onRetry={workspace.reload} /> : <LoadingState label="Loading settings…" />;
  else if (tab === 'detection') body = (
    <>
      <Section title="Sensitivity" description={`How readily the detector raises an alert. The published results (${BENCHMARK.recall}% recall, ${BENCHMARK.precision}% precision) were measured with the calibrated defaults.`}>
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
      <CameraSensitivity value={current.camera_sensitivity} fallback={current.fall_threshold ?? frozenThreshold} onChange={(camera_sensitivity) => patch({ camera_sensitivity })} />
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
      <label htmlFor="escalate-after">If nobody responds to a fall</label>
      <select id="escalate-after" value={current.escalate_after_sec ?? ''} onChange={(event) => patch({ escalate_after_sec: event.target.value ? Number(event.target.value) : null })}>
        {ESCALATION.map(([label, seconds]) => <option key={label} value={seconds ?? ''}>{label === 'Off' ? 'Do not escalate' : `Alert every dashboard again ${label.toLowerCase()}`}</option>)}
      </select>
      <p className="helper">Escalation repeats the alert on every open dashboard with a stronger warning. Text messages, phone calls and emergency services are not connected.</p>
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
    <div className={`settings-page${tab === 'account' ? ' settings-account-page' : ''}`}>
      <PageHeader
        eyebrow={isAdmin ? "SYSTEM" : "ACCOUNT"}
        title={isAdmin ? "Settings" : "Account settings"}
        subtitle={isAdmin
          ? "Tune detection and alerts, manage cameras and data, and update your account. Saved on the server for everyone."
          : "Manage your account, allow fall alerts on this device, and see your team."}
      />
      {toast ? <div className={`settings-toast${toast.ok ? '' : ' is-error'}`} role="status"><CheckCircle aria-hidden="true" /><span>{toast.text}</span><button type="button" className="icon-button" aria-label="Dismiss message" onClick={() => setToast(null)}>×</button></div> : null}
      <div className={`settings-layout${availableTabs.length > 1 ? '' : ' is-single'}`}>
        {availableTabs.length > 1 ? <nav className="settings-navigation" aria-label="Settings sections">
          {availableTabs.map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => selectTab(id)}><Icon aria-hidden="true" /><span>{label}</span></button>)}
        </nav> : null}
        {tab === 'account' ? body : <Card className="settings-panel" title={availableTabs.find((item) => item.id === tab)?.label} icon={(() => { const Icon = availableTabs.find((item) => item.id === tab)?.icon ?? Database; return <Icon />; })()}>{body}</Card>}
      </div>
      {isAdmin && SAVED_TABS.includes(tab) ? (
        <footer className="settings-savebar">
          <span>{dirty ? 'You have unsaved changes' : 'All changes saved'}</span>
          <button type="button" className="btn btn-ghost" disabled={!dirty || saving} onClick={() => { setDraft(null); setToast(null); }}>Discard</button>
          <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={() => void save()}><Save aria-hidden="true" />{saving ? 'Saving…' : 'Save changes'}</button>
        </footer>
      ) : null}
      {confirmingRetention && draft?.retention_days ? (
        <ConfirmDialog title="Delete old incidents?" confirmLabel="Save and delete" onClose={() => setConfirmingRetention(false)} onConfirm={() => void save(true)}>
          <p>Incidents older than {draft.retention_days} day{draft.retention_days === 1 ? '' : 's'} and their keyframes will be permanently deleted within the hour. This cannot be undone.</p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
