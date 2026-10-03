import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../features/auth/AuthProvider.tsx';
import { DashboardProvider } from '../hooks/DashboardContext.tsx';
import { LocationProbe } from './LocationProbe.tsx';

/** Render a dashboard page with the real providers (fixture transport for incidents). */
export function renderPage(page: ReactElement, path = '/app'): RenderResult {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <DashboardProvider>
          <Routes><Route path="*" element={page} /></Routes>
          <LocationProbe />
        </DashboardProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}
