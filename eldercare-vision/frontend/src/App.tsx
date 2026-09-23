import { AppShell, Header } from './components/layout/Shell.tsx';
import { useEvents } from './hooks/useEvents.ts';
import type { JSX } from 'react';
import './index.css';
import { DashboardPage } from './pages/DashboardPage.tsx';

function App(): JSX.Element {
  const events = useEvents();
  return (
    <AppShell>
      <Header connected={events.connected} />
      <DashboardPage events={events} />
    </AppShell>
  );
}

export default App;
