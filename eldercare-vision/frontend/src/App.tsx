import { AppShell, Header } from './components/layout/Shell.tsx';
import type { JSX } from 'react';
import './index.css';
import { DashboardPage } from './pages/DashboardPage.tsx';

function App(): JSX.Element {
  return (
    <AppShell>
      <Header connected={false} />
      <DashboardPage />
    </AppShell>
  );
}

export default App;
