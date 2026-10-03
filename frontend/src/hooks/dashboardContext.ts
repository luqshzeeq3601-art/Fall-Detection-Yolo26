import { createContext } from 'react';
import type { Camera, ReadyResponse, SystemStatusResponse } from '../api/types.ts';
import type { AsyncState } from './useAsync.ts';
import type { EventsBundle } from './useEvents.ts';

export interface DashboardContextValue {
  cameras: AsyncState<Camera[]>;
  system: AsyncState<SystemStatusResponse>;
  ready: AsyncState<ReadyResponse>;
  events: EventsBundle;
}

export const DashboardContext = createContext<DashboardContextValue | null>(null);
