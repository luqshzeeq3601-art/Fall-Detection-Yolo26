import { HttpApiClient, type ApiClient } from './client.ts';
import { MockApiClient } from './mockClient.ts';

let override: ApiClient | null = null;
let singleton: ApiClient | null = null;

function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  return typeof raw === 'string' ? raw.replace(/\/$/, '') : '';
}

function shouldUseMock(): boolean {
  const raw = import.meta.env.VITE_USE_MOCK;
  if (typeof raw === 'string') return raw.toLowerCase() !== 'false';
  return true;
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
