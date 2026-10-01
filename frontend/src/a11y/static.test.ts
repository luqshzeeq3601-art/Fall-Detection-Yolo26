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

describe('Dashboard static QA (P6-008)', () => {
  it('declares the document language', () => {
    expect(html).toContain('lang="en"');
  });

  it('meets WCAG AA contrast for body and muted text on surfaces', () => {
    const text = contrastRatio(cssVar('--text'), cssVar('--surface'));
    const muted = contrastRatio(cssVar('--muted'), cssVar('--surface'));
    expect(text).toBeGreaterThanOrEqual(7);
    expect(muted).toBeGreaterThanOrEqual(4.5);
  });

  it('shows visible focus and responsive rules without decorative excess', () => {
    expect(css).toContain(':focus-visible');
    expect(css).toContain('@media');
    for (const banned of ['backdrop-filter', 'linear-gradient', 'radial-gradient', 'glass']) {
      expect(css.toLowerCase()).not.toContain(banned);
    }
  });
});
