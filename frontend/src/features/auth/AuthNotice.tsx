import { NoticeDialog } from '../../components/common/Dialog.tsx';
import type { JSX, ReactNode } from 'react';

export type AuthNoticeKind = 'research' | 'reset' | 'terms' | 'privacy' | 'google';

const NOTICE_COPY: Record<AuthNoticeKind, { title: string; body: string }> = {
  google: {
    title: 'Google sign-in',
    body: 'Google sign-in is not available in this workspace. Use your email and password to sign in.',
  },
  research: {
    title: 'Research notes',
    body: 'ElderCare Vision is a research prototype: YOLO26 pose estimation with the frozen V6.3 fall classifier, running on this server. It is not a certified medical device or an emergency service.',
  },
  reset: {
    title: 'Reset your password',
    body: 'Email delivery is not configured on this server, so passwords cannot be reset by email. Ask your workspace admin, or change your password from Settings → Account & Team while signed in.',
  },
  terms: {
    title: 'Terms of use',
    body: 'Accounts give operators access to this ElderCare Vision deployment. Alerts support, but never replace, human supervision; the system is a research prototype, not a medical device or emergency service.',
  },
  privacy: {
    title: 'Privacy',
    body: 'Video is analysed on this server and is not uploaded elsewhere. Only detected incidents (three keyframes and detector scores) are stored. Passwords are kept as salted scrypt hashes; sessions use an HttpOnly cookie.',
  },
};

export function AuthNotice({ kind, onClose, children }: { kind: AuthNoticeKind; onClose: () => void; children?: ReactNode }): JSX.Element {
  const copy = NOTICE_COPY[kind];
  return (
    <NoticeDialog title={copy.title} onClose={onClose}>
      <p>{copy.body}</p>
      {children}
    </NoticeDialog>
  );
}
