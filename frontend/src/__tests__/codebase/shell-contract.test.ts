/**
 * Regression guard: layout.tsx shell completeness.
 *
 * If any required component is removed from layout.tsx the corresponding
 * feature silently disappears for users. This test catches that.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const layout = fs.readFileSync(
  path.join(__dirname, '../../../src/app/layout.tsx'),
  'utf-8',
);
const gate = fs.readFileSync(
  path.join(__dirname, '../../../src/components/AppLockGate.tsx'),
  'utf-8',
);

describe('layout.tsx shell contract', () => {
  it('mounts the app-lock gate around the product shell', () => {
    expect(layout).toContain('<AppLockGate>');
  });

  it('mounts OnboardingGate (first-run redirect)', () => {
    expect(gate).toContain('OnboardingGate');
    expect(gate).toContain('<OnboardingGate');
  });

  it('mounts HatchNavShell (sidebar + mobile tabs)', () => {
    expect(gate).toContain('HatchNavShell');
    expect(gate).toContain('<HatchNavShell');
  });

  it('mounts HatchTopBarSlot (desktop top bar with bell + toggle)', () => {
    expect(gate).toContain('HatchTopBarSlot');
    expect(gate).toContain('<HatchTopBarSlot');
  });

  it('mounts HatchMobileBar (mobile bell + toggle)', () => {
    expect(gate).toContain('HatchMobileBar');
    expect(gate).toContain('<HatchMobileBar');
  });

  it('has dark-mode boot script (theme persisted across reload)', () => {
    expect(layout).toContain("localStorage.getItem('theme')");
    expect(layout).toContain('data-theme');
  });

  it('does NOT mount the old Navigation component', () => {
    expect(layout).not.toContain("from '@/components/Navigation'");
    expect(layout).not.toContain('from "@/components/Navigation"');
  });
});
