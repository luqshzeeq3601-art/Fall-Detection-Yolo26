import type { JSX, ReactNode } from 'react';
import { ConnectionBadge } from '../common/ConnectionBadge.tsx';

export function Header({ connected }: { connected: boolean }): JSX.Element {
  return (
    <header className="app-header">
      <div>
        <h1>ElderCare Vision</h1>
        <p className="subtitle">Fall monitoring · Research POC, not a medical device</p>
      </div>
      <ConnectionBadge connected={connected} />
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }): JSX.Element {
  return <div className="app-shell">{children}</div>;
}
