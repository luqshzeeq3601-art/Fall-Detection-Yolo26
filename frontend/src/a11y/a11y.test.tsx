import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installFakeApi } from '../test/fakeApi.ts';
import App from '../App.tsx';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';

beforeEach(() => { window.history.replaceState(null, '', '/app'); installFakeApi(); });

afterEach(() => {
  cleanup();
  setApiClient(null);
  vi.unstubAllGlobals();
});

describe('Dashboard accessibility and runtime QA', () => {
  it('exposes app landmarks, one h1, and the Overview hierarchy', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    expect(document.querySelector('header.app-topbar')).not.toBeNull();
    expect(screen.getByRole('main')).toBeDefined();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeDefined();
    expect(screen.getByRole('complementary', { name: 'Primary navigation' })).toBeDefined();
    expect(screen.getByRole('navigation', { name: 'Dashboard pages' })).toBeDefined();
  });

  it('labels the global search and keeps interactions on native controls', async () => {
    setApiClient(new MockApiClient());
    const { container } = render(<App />);
    expect(await screen.findByLabelText('Search incidents')).toBeDefined();
    const clickableDivs = container.querySelectorAll('div[onclick], div[role="button"]');
    expect(clickableDivs.length).toBe(0);
    const positives = container.querySelectorAll('[tabindex]');
    for (const element of Array.from(positives)) {
      expect(Number(element.getAttribute('tabindex'))).toBeLessThanOrEqual(0);
    }
  });

  it('keeps connection and data state meaningful in text as well as color', async () => {
    setApiClient(new MockApiClient());
    const { container } = render(<App />);
    expect(await screen.findByRole('status', { name: /event stream: live updates/i })).toBeDefined();
    const statuses = container.querySelectorAll('.status-pill, .conn');
    expect(statuses.length).toBeGreaterThan(0);
    for (const element of Array.from(statuses)) {
      expect((element.textContent ?? '').trim().length).toBeGreaterThan(1);
    }
  });

  it('opens and closes the fall alerts panel with keyboard-operable controls', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    const bell = await screen.findByRole('button', { name: /fall alerts/i });
    fireEvent.click(bell);
    const panel = screen.getByRole('dialog', { name: 'Fall alerts' });
    expect(panel.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(document.activeElement).toBe(bell));
    expect(screen.queryByRole('dialog', { name: 'Fall alerts' })).toBeNull();
  });

  it('traps the responsive drawer and returns focus after Escape', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    const menu = await screen.findByRole('button', { name: 'Open navigation' });
    fireEvent.click(menu);
    const close = document.querySelector('.sidebar-close');
    expect(close).not.toBeNull();
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    await waitFor(() => expect(document.activeElement).toBe(menu));
  });
});
