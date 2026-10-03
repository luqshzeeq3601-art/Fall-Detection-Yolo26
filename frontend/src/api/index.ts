import { HttpApiClient, type ApiClient } from './client.ts';
import { MockApiClient } from './mockClient.ts';

let override: ApiClient | null = null;
let singleton: ApiClient | null = null;

/** Versioned API base; defaults to the same-origin `/api/v1` proxied by Vite. */
export function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  return typeof raw === 'string' && raw.trim() ? raw.trim().replace(/\/$/, '') : '/api/v1';
}

/** Fixture transport only when explicitly requested (tests set VITE_USE_MOCK=true). */
function shouldUseMock(): boolean {
  const raw = import.meta.env.VITE_USE_MOCK;
  return typeof raw === 'string' && raw.trim().toLowerCase() === 'true';
}

/** Whether the active API boundary is the deterministic demo transport. */
export function isDemoMode(): boolean {
  if (override instanceof MockApiClient) return true;
  if (override !== null) return false;
  return shouldUseMock();
}

/** Injectable singleton: tests call setApiClient, app uses getApiClient. */
export function getApiClient(): ApiClient {
  if (override) return override;
  if (!singleton) {
    singleton = shouldUseMock() ? new MockApiClient() : new HttpApiClient(apiBaseUrl());
  }
  return singleton;
}

export function setApiClient(client: ApiClient | null): void {
  override = client;
  if (client === null) singleton = null;
}

export type { ApiClient };
