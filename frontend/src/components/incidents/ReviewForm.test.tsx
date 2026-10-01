import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { getApiClient, setApiClient } from '../../api/index.ts';
import { MockApiClient } from '../../api/mockClient.ts';
import { MOCK_INCIDENTS } from '../../api/mockData.ts';
import { ReviewForm } from './ReviewForm.tsx';

afterEach(() => {
  cleanup();
  setApiClient(null);
});

describe('ReviewForm (P6-005)', () => {
  it('requires an explicit label choice', async () => {
    setApiClient(new MockApiClient());
    render(<ReviewForm incidentId={MOCK_INCIDENTS[0].id} onSubmitted={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /save review/i }));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(await screen.findByText(/Choose a review label/)).toBeDefined();
  });

  it('submits a review and appends it without touching detector output', async () => {
    const client = new MockApiClient();
    setApiClient(client);
    const id = MOCK_INCIDENTS[0].id;
    const before = await client.getIncident(id);
    let submitted = 0;
    render(<ReviewForm incidentId={id} onSubmitted={() => { submitted += 1; }} />);
    fireEvent.click(screen.getByRole('radio', { name: /non_fall/i }));
    fireEvent.change(screen.getByLabelText(/notes/i), { target: { value: 'Sitting test' } });
    fireEvent.click(screen.getByRole('button', { name: /save review/i }));
    expect(await screen.findByRole('status')).toBeDefined();
    expect(submitted).toBe(1);
    const after = await getApiClient().getIncident(id);
    expect(after.fall_score).toBe(before.fall_score);
    expect(after.model_name).toBe(before.model_name);
    expect(after.evidence_features).toEqual(before.evidence_features);
    expect(after.reviews.length).toBe(before.reviews.length + 1);
    expect(after.reviews[after.reviews.length - 1].label).toBe('non_fall');
  });

  it('shows backend errors and preserves input for retry', async () => {
    const client = new MockApiClient();
    client.setFailureMode('reviews');
    setApiClient(client);
    render(<ReviewForm incidentId={MOCK_INCIDENTS[0].id} onSubmitted={() => {}} />);
    fireEvent.click(screen.getByRole('radio', { name: /uncertain/i }));
    fireEvent.change(screen.getByLabelText(/notes/i), { target: { value: 'keep me' } });
    fireEvent.click(screen.getByRole('button', { name: /save review/i }));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByLabelText(/notes/i)).toHaveProperty('value', 'keep me');
  });
});
