import { useContext } from 'react';
import { DashboardContext } from './dashboardContext.ts';

export function useDashboardContext() {
  const context = useContext(DashboardContext);
  if (context === null) {
    throw new Error('useDashboardContext must be used within a DashboardProvider');
  }
  return context;
}
