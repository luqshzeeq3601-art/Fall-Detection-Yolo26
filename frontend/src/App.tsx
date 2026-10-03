import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import type { JSX } from 'react';
import { DashboardProvider } from './hooks/DashboardContext.tsx';
import { AppShell } from './components/layout/Shell.tsx';
import { DashboardPage } from './pages/DashboardPage.tsx';
import { LandingPage } from './pages/LandingPage.tsx';
import { SignInPage } from './pages/SignInPage.tsx';
import { SignUpPage } from './pages/SignUpPage.tsx';
import { SurveillancePage } from './pages/SurveillancePage.tsx';
import { IncidentsPage } from './pages/IncidentsPage.tsx';
import { ReviewQueuePage } from './pages/ReviewQueuePage.tsx';
import { BenchmarksPage } from './pages/BenchmarksPage.tsx';
import { TelemetryPage } from './pages/TelemetryPage.tsx';
import { SettingsPage } from './pages/SettingsPage.tsx';
import { AuthProvider, RequireAdmin, RequireAuth } from './features/auth/AuthProvider.tsx';
import './index.css';
import './theme-tokens.css';
import './pages/Polish.css';

function App(): JSX.Element {
  return (
    <BrowserRouter>
      <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <DashboardProvider>
                <AppShell />
              </DashboardProvider>
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="surveillance" element={<SurveillancePage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="review" element={<ReviewQueuePage />} />
          <Route path="benchmarks" element={<RequireAdmin><BenchmarksPage /></RequireAdmin>} />
          <Route path="telemetry" element={<RequireAdmin><TelemetryPage /></RequireAdmin>} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

function NotFoundPage(): JSX.Element {
  return <main className="not-found"><h1>Page not found</h1><p>The requested page is unavailable.</p><Link to="/">Return to home</Link></main>;
}

export default App;
