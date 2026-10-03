import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import type { JSX } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  MemoryRouter,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { HttpApiClient } from '../api/client.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { MOCK_READY, MOCK_SYSTEM_STATUS } from '../api/mockData.ts';
import { setApiClient } from '../api/index.ts';
import { MockEventSocket } from './useEvents.ts';
import type { WsEvent } from '../api/types.ts';
import { DashboardProvider } from './DashboardContext.tsx';
import { useDashboardContext } from './useDashboardContext.ts';

function PublicRoute(): JSX.Element {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate('/app')}>
      Enter app
    </button>
  );
}

function DashboardRoute(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const { cameras, system, ready, events } = useDashboardContext();
  return (
    <div>
      <output data-testid="route">{location.pathname}</output>
      <output data-testid="connection">{events.connection}</output>
      <output data-testid="camera-state">{cameras.loading ? 'loading' : cameras.data?.[0]?.id ?? 'empty'}</output>
      <output data-testid="camera-status">{cameras.loading ? 'loading' : cameras.data?.[0]?.status ?? 'empty'}</output>
      <output data-testid="system-state">{system.loading ? 'loading' : system.data?.model_name ?? 'empty'}</output>
      <output data-testid="ready-state">{ready.loading ? 'loading' : ready.data?.status ?? 'empty'}</output>
      <button type="button" onClick={() => navigate('/app/incidents')}>
        Open incidents
      </button>
    </div>
  );
}

class LiveEventSocket {
  static instances: LiveEventSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor() {
    LiveEventSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  emit(event: WsEvent): void {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  serverClose(): void {
    this.onclose?.();
  }

  close(): void {
    this.closed = true;
  }
}

function AppLayout(): JSX.Element {
  return (
    <DashboardProvider>
      <Outlet />
    </DashboardProvider>
  );
}

function renderMiniRouter(initialEntry = '/public') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/public" element={<PublicRoute />} />
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<DashboardRoute />} />
          <Route path="incidents" element={<DashboardRoute />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  setApiClient(null);
  LiveEventSocket.instances = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('DashboardProvider route lifecycle', () => {
  it('mounts only inside the app layout and keeps one fetch/socket set across child routes', async () => {
    const api = new MockApiClient();
    const camerasSpy = vi.spyOn(api, 'listCameras');
    const systemSpy = vi.spyOn(api, 'getSystemStatus');
    const readySpy = vi.spyOn(api, 'getReady');
    const socketOpenSpy = vi.spyOn(MockEventSocket.prototype, 'open');
    const socketCloseSpy = vi.spyOn(MockEventSocket.prototype, 'close');
    setApiClient(api);

    const view = renderMiniRouter();
    expect(camerasSpy).not.toHaveBeenCalled();
    expect(systemSpy).not.toHaveBeenCalled();
    expect(readySpy).not.toHaveBeenCalled();
    expect(socketOpenSpy).not.toHaveBeenCalled();

    fireEvent.click(view.getByRole('button', { name: 'Enter app' }));
    await waitFor(() => expect(view.getByTestId('route').textContent).toBe('/app'));
    await waitFor(() => expect(view.getByTestId('connection').textContent).toBe('connected'));
    // The fixture socket replays camera status events, which refresh the camera list once.
    await waitFor(() => expect(camerasSpy).toHaveBeenCalledTimes(2));
    expect(systemSpy).toHaveBeenCalledTimes(1);
    expect(readySpy).toHaveBeenCalledTimes(1);
    expect(socketOpenSpy).toHaveBeenCalledTimes(1);
    expect(socketCloseSpy).not.toHaveBeenCalled();

    fireEvent.click(view.getByRole('button', { name: 'Open incidents' }));
    await waitFor(() => expect(view.getByTestId('route').textContent).toBe('/app/incidents'));
    expect(camerasSpy).toHaveBeenCalledTimes(2);
    expect(systemSpy).toHaveBeenCalledTimes(1);
    expect(readySpy).toHaveBeenCalledTimes(1);
    expect(socketOpenSpy).toHaveBeenCalledTimes(1);
    expect(socketCloseSpy).not.toHaveBeenCalled();

    view.unmount();
    expect(socketCloseSpy).toHaveBeenCalledTimes(1);
  });

  it('refreshes live cameras for a status event and a real socket reconnect without remounting', async () => {
    let status = 'online';
    const api = new HttpApiClient();
    const camerasSpy = vi.spyOn(api, 'listCameras').mockImplementation(async () => [{
      id: 'cam-live',
      name: 'Live camera',
      status,
      last_frame_at: null,
      last_heartbeat_at: null,
      reconnect_count: 0,
    }]);
    vi.spyOn(api, 'getSystemStatus').mockResolvedValue(MOCK_SYSTEM_STATUS);
    vi.spyOn(api, 'getReady').mockResolvedValue(MOCK_READY);
    vi.stubGlobal('WebSocket', LiveEventSocket as unknown as typeof WebSocket);
    setApiClient(api);

    const view = renderMiniRouter();
    fireEvent.click(view.getByRole('button', { name: 'Enter app' }));
    await waitFor(() => expect(view.getByTestId('connection').textContent).toBe('connected'));
    await waitFor(() => expect(view.getByTestId('camera-status').textContent).toBe('online'));
    expect(camerasSpy).toHaveBeenCalledTimes(1);

    status = 'offline';
    LiveEventSocket.instances[0].emit({ event_id: 'camera-offline-1', event_type: 'camera.offline', occurred_at: '2026-10-01T08:00:00Z', camera_id: 'cam-live', incident_id: null, payload: {} });
    await waitFor(() => expect(view.getByTestId('camera-status').textContent).toBe('offline'));
    expect(camerasSpy).toHaveBeenCalledTimes(2);

    LiveEventSocket.instances[0].serverClose();
    await waitFor(() => expect(LiveEventSocket.instances).toHaveLength(2), { timeout: 1500 });
    await waitFor(() => expect(camerasSpy).toHaveBeenCalledTimes(3), { timeout: 1500 });
  });
});
