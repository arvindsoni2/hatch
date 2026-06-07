/**
 * CSS token guard: no light-only Tailwind utilities in v4/v4.1 code paths.
 *
 * Scope: new Direction A routes + hatch components + onboarding.
 * Legacy pre-v4 components (coach, jobs, applications, agents, calendar) use
 * correct dark: paired variants and are excluded from this guard — they'll be
 * migrated incrementally.
 *
 * Exception: dark: prefixed variants are always allowed.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const FORBIDDEN: { pattern: RegExp; label: string }[] = [
  { pattern: /(?<!dark:)bg-white(?![\w-])/, label: 'bg-white' },
  { pattern: /(?<!dark:)text-slate-900(?![\w-])/, label: 'text-slate-900' },
  { pattern: /(?<!dark:)text-slate-800(?![\w-])/, label: 'text-slate-800' },
  { pattern: /(?<!dark:)border-slate-200(?![\w-])/, label: 'border-slate-200' },
];

// Only scan v4/v4.1 code — Direction A routes + hatch components + onboarding
const SCAN_DIRS = [
  'app/today', 'app/stream', 'app/tracker', 'app/prep',
  'app/onboarding', 'app/settings',
  'components/hatch',
];
const EXCLUDE_PATTERNS = ['__tests__', 'node_modules', '.test.', '.spec.'];

function collectTsxFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectTsxFiles(full));
    } else if (/\.(tsx|ts)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

const srcDir = path.join(__dirname, '../../../src');
const filesToScan = SCAN_DIRS.flatMap((d) => collectTsxFiles(path.join(srcDir, d))).filter(
  (f) => !EXCLUDE_PATTERNS.some((ex) => f.includes(ex)),
);

describe('No bare light-only Tailwind in src/app and src/components', () => {
  for (const file of filesToScan) {
    const label = file.replace(srcDir + '/', '');
    it(`${label} — no forbidden light classes`, () => {
      const content = fs.readFileSync(file, 'utf-8');
      const violations: string[] = [];
      for (const { pattern, label: cls } of FORBIDDEN) {
        const matches = content.match(new RegExp(pattern.source, 'g'));
        if (matches) violations.push(`${cls} (×${matches.length})`);
      }
      expect(violations, `${label} has light-only classes: ${violations.join(', ')}`).toHaveLength(0);
    });
  }
});
