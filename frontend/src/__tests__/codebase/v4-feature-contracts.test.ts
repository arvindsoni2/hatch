/**
 * Regression guard: v4 / v4.1 feature contracts.
 *
 * Each test pins a critical architectural invariant. A future change that
 * accidentally breaks one of these features will make this test go RED,
 * surfacing the problem before it ships.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const srcDir = path.join(__dirname, '../../../src');

function read(...parts: string[]) {
  return fs.readFileSync(path.join(srcDir, ...parts), 'utf-8');
}

function exists(...parts: string[]) {
  return fs.existsSync(path.join(srcDir, ...parts));
}

// ── Direction A routes ────────────────────────────────────────────────────────
describe('Direction A routes', () => {
  for (const route of ['today', 'stream', 'tracker', 'tailor', 'prep']) {
    it(`app/${route}/page.tsx exists`, () => {
      expect(exists('app', route, 'page.tsx')).toBe(true);
    });
  }

  it('app/page.tsx redirects to /today', () => {
    const root = read('app', 'page.tsx');
    expect(root).toContain('/today');
  });
});

// ── Navigation shell cleanup ──────────────────────────────────────────────────
describe('Navigation cleanup (v4.1)', () => {
  it('old Navigation.tsx is deleted', () => {
    expect(exists('components', 'Navigation.tsx')).toBe(false);
  });

  it('HatchTopBar has no notifCount prop (replaced by live NotificationBell)', () => {
    const topBar = read('components', 'hatch', 'HatchTopBar.tsx');
    expect(topBar).not.toContain('notifCount');
  });

  it('HatchTopBar imports NotificationBell', () => {
    const topBar = read('components', 'hatch', 'HatchTopBar.tsx');
    expect(topBar).toContain('NotificationBell');
  });

  it('HatchTopBar imports UserMenu (ThemeToggle moved into UserMenu dropdown)', () => {
    const topBar = read('components', 'hatch', 'HatchTopBar.tsx');
    expect(topBar).toContain('UserMenu');
  });

  it('primary navigation exposes CV Studio without changing its route', () => {
    const sidebar = read('components', 'hatch', 'HatchSidebar.tsx');
    const mobileNav = read('components', 'hatch', 'HatchNav.tsx');
    expect(sidebar).toContain("label: 'CV Studio'");
    expect(sidebar).toContain("href: '/tailor'");
    expect(mobileNav).toContain("label: 'CV Studio'");
    expect(mobileNav).toContain("href: '/tailor'");
  });

  it('mobile shell exposes the user menu', () => {
    const mobileBar = read('components', 'hatch', 'HatchMobileBar.tsx');
    expect(mobileBar).toContain('UserMenu');
    expect(mobileBar).toContain('<UserMenu');
  });

  it('UserMenu.tsx exists with ThemeToggle inside (v4.1 user settings dropdown)', () => {
    expect(exists('components', 'hatch', 'UserMenu.tsx')).toBe(true);
    const menu = read('components', 'hatch', 'UserMenu.tsx');
    expect(menu).toContain('ThemeToggle');
  });
});

// ── Two-step assisted apply invariants ───────────────────────────────────────
describe('Two-step assisted apply (v4)', () => {
  it('ReviewOverlay keeps document generation separate from application submission', () => {
    const overlay = read('components', 'hatch', 'ReviewOverlay.tsx');
    const hasGeneratePack = overlay.includes('Generate CV pack');
    const hasApproveAndApply = overlay.includes('Approve & apply') || overlay.includes('Approve &amp; apply');
    expect(hasGeneratePack).toBe(true);
    expect(hasApproveAndApply).toBe(false);
  });

  it('ApplicationReadyCard has "Mark as applied" CTA', () => {
    const card = read('components', 'hatch', 'ApplicationReadyCard.tsx');
    expect(card).toContain('Mark as applied');
  });

  it('ApplicationReadyCard has "Open application" CTA', () => {
    const card = read('components', 'hatch', 'ApplicationReadyCard.tsx');
    expect(card).toContain('Open application');
  });

  it('ApplicationReadyCard has "Undo" escape hatch', () => {
    const card = read('components', 'hatch', 'ApplicationReadyCard.tsx');
    expect(card).toContain('Undo');
  });

  it('TodayScreen renders "Finish applying" nudge for ready_to_apply jobs', () => {
    const screen = read('components', 'hatch', 'screens', 'TodayScreen.tsx');
    expect(screen).toContain('Finish applying');
    expect(screen).toContain('ready_to_apply');
  });
});

// ── Onboarding gate ───────────────────────────────────────────────────────────
describe('OnboardingGate (v4.1)', () => {
  it('OnboardingGate.tsx exists', () => {
    expect(exists('components', 'OnboardingGate.tsx')).toBe(true);
  });

  it('OnboardingGate redirects to /onboarding', () => {
    const gate = read('components', 'OnboardingGate.tsx');
    expect(gate).toContain('/onboarding');
    expect(gate).toContain('router.replace');
  });

  it('OnboardingGate renders null (invisible)', () => {
    const gate = read('components', 'OnboardingGate.tsx');
    expect(gate).toContain('return null');
  });
});

// ── Settings theme (v4.1) ─────────────────────────────────────────────────────
describe('Settings pages — no light-only Tailwind', () => {
  const FORBIDDEN = [/(?<!dark:)bg-white(?![\w-])/, /(?<!dark:)text-slate-900(?![\w-])/];
  const SETTINGS_FILES = [
    path.join(srcDir, 'app/settings/page.tsx'),
    path.join(srcDir, 'app/settings/profile/page.tsx'),
    path.join(srcDir, 'app/settings/preferences/page.tsx'),
    path.join(srcDir, 'app/settings/ai/page.tsx'),
    path.join(srcDir, 'app/settings/resume/page.tsx'),
    path.join(srcDir, 'app/settings/security/page.tsx'),
    path.join(srcDir, 'app/settings/system/page.tsx'),
  ];

  for (const file of SETTINGS_FILES) {
    const label = file.replace(srcDir + '/', '');
    it(`${label} has no bare bg-white or text-slate-900`, () => {
      const content = fs.readFileSync(file, 'utf-8');
      for (const pattern of FORBIDDEN) {
        const matches = content.match(new RegExp(pattern.source, 'g'));
        expect(matches, `${label} still has light-only class matching ${pattern}`).toBeNull();
      }
    });
  }
});
