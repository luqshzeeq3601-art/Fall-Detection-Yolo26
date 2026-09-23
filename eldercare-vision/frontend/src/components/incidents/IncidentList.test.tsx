import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { IncidentList } from './IncidentList.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('IncidentList (P6-003)', () => {
  it('renders incidents with score and detector state', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByText(/Showing 3 of 3 incidents/)).toBeDefined();
    expect(await screen.findByText(/Score 0\.87/)).toBeDefined();
  });

  it('filters by camera through the select', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByText(/Showing 3 of 3 incidents/)).toBeDefined();
    fireEvent.change(screen.getByLabelText(/camera/i), { target: { value: 'cam-02' } });
    expect(await screen.findByText(/Showing 1 of 1 incidents/)).toBeDefined();
  });

  it('shows empty state when no incidents match', async () => {
    setApiClient(new MockApiClient());
    render(<IncidentList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByText(/Showing 3 of 3 incidents/)).toBeDefined();
    fireEvent.change(screen.getByLabelText(/review/i), { target: { value: 'confirmed_fall' } });
    expect(await screen.findByText(/No incidents match these filters/)).toBeDefined();
  });

  it('notifies selection via keyboard-accessible buttons', async () => {
    setApiClient(new MockApiClient());
    const onSelect = vi.fn();
    render(<IncidentList selectedId={null} onSelect={onSelect} />);
    const buttons = await screen.findAllByRole('button', { name: /open incident/i });
    expect(buttons.length).toBe(3);
    fireEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('shows error + retry on failure', async () => {
    const client = new MockApiClient();
    client.setFailureMode('incidents');
    setApiClient(client);
    render(<IncidentList selectedId={null} onSelect={vi.fn()} />);
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeDefined();
  });
});
