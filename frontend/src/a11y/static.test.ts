// @vitest-environment node
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, '..', 'index.css'), 'utf-8');
const html = readFileSync(join(here, '..', '..', 'index.html'), 'utf-8');

function cssVar(name: string): string {
  const match = css.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`CSS variable ${name} not found`);
  return match[1];
}

function luminance(hex: string): number {
  const rgb = [1, 3, 5].map((i) => {
    const channel = parseInt(hex.slice(i, i + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

function contrastRatio(foreground: string, background: string): number {
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

describe('Dashboard static QA (P6 redesign)', () => {
  it('declares the document language', () => {
    expect(html).toContain('lang="en"');
  });

  it('meets WCAG AA contrast using the solid fallback beneath translucent surfaces', () => {
    const fallback = cssVar('--surface-solid');
    expect(contrastRatio(cssVar('--text-strong'), fallback)).toBeGreaterThanOrEqual(7);
    expect(contrastRatio(cssVar('--text-muted'), fallback)).toBeGreaterThanOrEqual(4.5);
    expect(css).toContain('--surface: rgba(255, 255, 255, 0.78)');
  });

  it('defines keyboard focus, responsive layout, and reduced-motion behavior', () => {
    expect(css).toContain(':focus-visible');
    expect(css).toContain('@media (max-width: 820px)');
    expect(css).toContain('@media (prefers-reduced-motion: reduce)');
    expect(css).toContain('overflow-x: hidden');
    expect(css).toContain('input::placeholder');
    expect(css).toContain('color: var(--text-muted)');
  });
});
