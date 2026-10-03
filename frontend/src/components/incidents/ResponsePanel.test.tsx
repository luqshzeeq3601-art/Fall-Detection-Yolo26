import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { installFakeApi } from '../../test/fakeApi.ts';
import { ResponsePanel } from './ResponsePanel.tsx';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('ResponsePanel', () => {
  it('lets someone claim an open incident', async () => {
    const { calls } = installFakeApi();
    const onSaved = vi.fn();
    render(<ResponsePanel incidentId="inc-1" status="escalated" responder={null} entries={[]} onSaved={onSaved} />);
    expect(screen.getByText('Nobody has responded yet')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: "I'm responding" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls.find((call) => call.path === '/incidents/inc-1/responses')?.body).toEqual({ action: 'responding' });
  });

  it('closes a claimed incident with an outcome and note', async () => {
    const { calls } = installFakeApi();
    const onSaved = vi.fn();
    render(<ResponsePanel incidentId="inc-1" status="responding" responder="Casey" entries={[]} onSaved={onSaved} />);
    expect(screen.getByText('Casey is responding')).toBeDefined();
    fireEvent.change(screen.getByLabelText('What happened (optional)'), { target: { value: 'Helped up' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolved: needed help' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls.find((call) => call.path === '/incidents/inc-1/responses')?.body).toEqual({ action: 'resolved', outcome: 'needed_help', notes: 'Helped up' });
  });
});
