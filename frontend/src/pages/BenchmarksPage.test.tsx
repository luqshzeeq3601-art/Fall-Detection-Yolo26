import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { BENCHMARK } from '../api/benchmarkData.ts';
import { BenchmarksPage } from './BenchmarksPage.tsx';

afterEach(() => cleanup());

function renderPage(): void {
  render(<MemoryRouter><BenchmarksPage /></MemoryRouter>);
}

describe('Model results', () => {
  it('keeps the snapshot consistent with the sealed evaluation counts', () => {
    expect(BENCHMARK.timeToAlert).toHaveLength(BENCHMARK.truePositives);
    expect(BENCHMARK.truePositives + BENCHMARK.falseNegatives).toBe(BENCHMARK.fallClips);
    expect(BENCHMARK.adlTrueNegatives + BENCHMARK.adlFalsePositiveClips).toBe(BENCHMARK.adlClips);
    const falls = BENCHMARK.activities.filter((a) => a.fall);
    expect(falls.reduce((sum, a) => sum + a.correct, 0)).toBe(BENCHMARK.truePositives);
    expect(BENCHMARK.activities.filter((a) => !a.fall).reduce((sum, a) => sum + a.correct, 0)).toBe(BENCHMARK.adlTrueNegatives);
    expect(BENCHMARK.cameras.reduce((sum, c) => sum + c.caught, 0)).toBe(BENCHMARK.truePositives);
    const sorted = [...BENCHMARK.timeToAlert].sort((a, b) => a - b);
    expect(sorted[Math.floor(sorted.length / 2)]).toBeCloseTo(BENCHMARK.medianSeconds, 1);
  });

  it('shows each headline against its gate with the confidence interval', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Model performance & evaluation' })).toBeDefined();
    expect(screen.getByRole('img', { name: /recall 98\.3%, 95% confidence 91\.1–99\.7%, gate at least 90%: passed/i })).toBeDefined();
    expect(screen.getByRole('img', { name: /precision 96\.7%.*gate at least 85%: passed/i })).toBeDefined();
    expect(screen.getByRole('img', { name: /p95 time to alert 1\.58 seconds, gate at most 3 seconds: passed/i })).toBeDefined();
    expect(screen.getByText('False-alarm rate under evaluation')).toBeDefined();
  });

  it('plots every detected fall and labels the version history as development data', () => {
    const { container } = render(<MemoryRouter><BenchmarksPage /></MemoryRouter>);
    expect(container.querySelectorAll('.tl-dot')).toHaveLength(59);
    expect(screen.getByText(/not the sealed test: only V6\.3 was run on Test-B/i)).toBeDefined();
    expect(screen.getByLabelText('Forward, onto hands: 11 of 12 correct')).toBeDefined();
    expect(screen.getByLabelText('Lying down: 11 of 12 correct')).toBeDefined();
  });
});
