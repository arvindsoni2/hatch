/**
 * Task 1 — RED tests for HatchTopBarSlot.
 * Written BEFORE the component exists.
 * Bell + toggle assertions become GREEN after Tasks 2 & 3.
 */
import { render, screen, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/today'),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

vi.mock('@/lib/api', () => ({
  fetchProfileStatus: vi.fn().mockResolvedValue({ candidate_name: 'Arvind', onboarding_required: false }),
  listCompletedJobs: vi.fn().mockResolvedValue([]),
}));

describe('HatchTopBarSlot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders a header landmark', async () => {
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByRole('banner')).toBeTruthy();
  });

  it('shows "Today" for /today pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/today');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Today')).toBeTruthy();
  });

  it('shows "Pipeline" for /stream pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/stream');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Pipeline')).toBeTruthy();
  });

  it('shows "Applications" for /tracker pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/tracker');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Applications')).toBeTruthy();
  });

  it('shows "Interview Coach" for /coach pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/coach');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Interview Coach')).toBeTruthy();
  });

  it('shows "Profile" for /settings pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/settings');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Profile')).toBeTruthy();
  });

  it('shows "Master CV" for /settings/resume pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/settings/resume');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('Master CV')).toBeTruthy();
  });

  it('shows "CV Studio" for /tailor pathname', async () => {
    const nav = await import('next/navigation');
    vi.mocked(nav.usePathname).mockReturnValue('/tailor');
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByText('CV Studio')).toBeTruthy();
  });

  it('renders a notifications button', async () => {
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    expect(screen.getByRole('button', { name: /notifications/i })).toBeTruthy();
  });

  it('renders the user menu avatar (theme toggle moved into UserMenu dropdown)', async () => {
    const { HatchTopBarSlot } = await import('@/components/hatch/HatchTopBarSlot');
    await act(async () => { render(<HatchTopBarSlot />); });
    // UserMenu replaces standalone ThemeToggle — avatar button opens the dropdown
    expect(screen.getByRole('button', { name: /open user menu/i })).toBeTruthy();
  });
});
