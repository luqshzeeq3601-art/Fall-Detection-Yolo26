import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from './App.tsx';
import { setApiClient } from './api/index.ts';
import { MockApiClient } from './api/mockClient.ts';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('App shell (P6-001)', () => {
  it('renders header, connection state, and dashboard sections', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    expect(screen.getByRole('heading', { name: /eldercare vision/i })).toBeDefined();
    expect(screen.getByText(/not a medical device/i)).toBeDefined();
    expect(screen.getByRole('status', { name: /event stream/i })).toBeDefined();
    const hallway = await screen.findAllByText('Hallway Camera');
    expect(hallway.length).toBeGreaterThan(0);
  });
});
