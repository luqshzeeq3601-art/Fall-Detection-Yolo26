import { getApiClient } from '../api/index.ts';
import { useAsync } from './useAsync.ts';

export function useCameras() {
  return useAsync(() => getApiClient().listCameras());
}

export function useSystemStatus() {
  return useAsync(() => getApiClient().getSystemStatus());
}

export function useHealth() {
  return useAsync(() => getApiClient().getHealth());
}
