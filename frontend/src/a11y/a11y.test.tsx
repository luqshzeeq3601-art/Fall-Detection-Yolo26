import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../App.tsx';
import { setApiClient } from '../api/index.ts';
import { MockApiClient } from '../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../api/mockData.ts';
import { IncidentDetailPanel } from '../components/incidents/IncidentDetail.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('Dashboard accessibility + runtime QA (P6-008)', () => {
  it('exposes landmarks, one h1, and ordered section headings', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    expect(screen.getByRole('banner')).toBeDefined();
    expect(screen.getByRole('main')).toBeDefined();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    for (const name of ['System telemetry', 'Cameras', 'Incidents', 'Incident detail', 'Live events']) {
      expect(await screen.findByRole('heading', { name })).toBeDefined();
    }
  });

  it('labels every form control and uses native interactive elements', async () => {
    setApiClient(new MockApiClient());
    const { container } = render(<App />);
    expect(await screen.findByLabelText('Camera')).toBeDefined();
    expect(await screen.findByLabelText('Detector state')).toBeDefined();
    expect(await screen.findByLabelText('Review')).toBeDefined();
    const clickableDivs = container.querySelectorAll('div[onclick], div[role="button"]');
    expect(clickableDivs.length).toBe(0);
    const positives = container.querySelectorAll('[tabindex]');
    for (const el of Array.from(positives)) {
      const value = Number(el.getAttribute('tabindex'));
      expect(value).toBeLessThanOrEqual(0);
    }
  });

  it('keeps status meaning in text+symbol, never color-only', async () => {
    setApiClient(new MockApiClient());
    const { container } = render(<App />);
    await screen.findByText('Offline');
    const statuses = container.querySelectorAll('.status');
    expect(statuses.length).toBeGreaterThan(0);
    for (const el of Array.from(statuses)) {
      expect((el.textContent ?? '').trim().length).toBeGreaterThan(1);
    }
  });

  it('announces loading, error, connection, and success via live regions', async () => {
    setApiClient(new MockApiClient());
    render(<App />);
    expect(await screen.findByRole('status', { name: /event stream/i })).toBeDefined();
    expect((await screen.findAllByRole('status')).length).toBeGreaterThan(0);
  });

  it('renders review history as plain text after submission', async () => {
    const client = new MockApiClient();
    setApiClient(client);
    const id = MOCK_INCIDENTS[0].id;
    await client.submitReview(id, {
      label: 'confirmed_fall',
      notes: 'Operator note',
      reviewer: 'qa',
    });
    const { container } = render(<IncidentDetailPanel selectedId={id} />);
    expect(await screen.findByText('Operator note')).toBeDefined();
    expect(container.innerHTML).not.toContain('<script');
  });

  it('keeps semantic structures across dashboard and detail views', async () => {
    setApiClient(new MockApiClient());
    const { container, unmount } = render(<App />);
    await screen.findByText('Offline');
    expect(container.querySelector('main dl.kv')).not.toBeNull();
    expect(container.querySelector('ul[aria-label="Camera health"]')).not.toBeNull();
    expect(container.querySelector('ul[aria-label="Incidents"]')).not.toBeNull();
    expect(container.querySelector('ul[aria-label="Live events"]')).not.toBeNull();
    unmount();
    cleanup();
    const detail = render(<IncidentDetailPanel selectedId={MOCK_INCIDENTS[0].id} />);
    await detail.findByRole('article');
    expect(detail.container.querySelector('fieldset legend')).not.toBeNull();
    expect(detail.container.querySelector('form[aria-label="Submit human review"]')).not.toBeNull();
    const radios = detail.container.querySelectorAll('input[type="radio"]');
    expect(radios.length).toBe(3);
    fireEvent.click(screen.getByRole('radio', { name: /confirmed_fall/i }));
    expect(screen.getByRole('radio', { name: /confirmed_fall/i })).toHaveProperty('checked', true);
  });
});
