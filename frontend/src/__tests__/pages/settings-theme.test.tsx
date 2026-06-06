/**
 * Task 5 — Codebase guard: settings pages must not contain light-only Tailwind.
 * Any file that fails this test needs re-theming to CSS-var tokens.
 * Rule: bg-white, text-slate-900, text-slate-800, border-slate-200 are forbidden
 * (only allowed if preceded by "dark:" i.e. as a dark-variant companion).
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SETTINGS_PAGES = [
  'settings/page.tsx',
  'settings/profile/page.tsx',
  'settings/resume/page.tsx',
  'settings/system/page.tsx',
];

const FORBIDDEN = [
  /(?<!dark:)bg-white(?![\w-])/,
  /(?<!dark:)text-slate-900(?![\w-])/,
  /(?<!dark:)text-slate-800(?![\w-])/,
  /(?<!dark:)border-slate-200(?![\w-])/,
];

const appDir = path.join(__dirname, '../../../src/app');

describe('settings pages — no light-only Tailwind utilities', () => {
  for (const page of SETTINGS_PAGES) {
    it(`${page} contains no bare bg-white / text-slate-9xx / border-slate-200`, () => {
      const filePath = path.join(appDir, page);
      const content = fs.readFileSync(filePath, 'utf-8');

      for (const pattern of FORBIDDEN) {
        const matches = content.match(new RegExp(pattern.source, 'g'));
        expect(matches, `${page} still has light-only class matching ${pattern}`).toBeNull();
      }
    });
  }
});
