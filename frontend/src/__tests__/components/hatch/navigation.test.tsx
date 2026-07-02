/**
 * Phase 4 — RED tests for Hatch navigation components.
 * Written BEFORE any implementation exists.
 * v4.1: extended with live NotificationBell assertions (Task 2).
 */
import { render, screen, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// ── HatchNav (mobile bottom tab bar) ─────────────────────────────────────────
describe('HatchNav', () => {
  it('renders all 4 tab labels', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    render(<HatchNav activeTab="today" />);
    expect(screen.getByText('Today')).toBeTruthy();
    expect(screen.getByText('Pipeline')).toBeTruthy();
    expect(screen.getByText('Applications')).toBeTruthy();
    expect(screen.getByText('Interview Prep')).toBeTruthy();
  });

  it('marks the active tab with accent colour', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    const { container } = render(<HatchNav activeTab="stream" />);
    // Active tab link/item should have data-active or accent style
    const activeEl = container.querySelector('[data-active="true"]');
    expect(activeEl).toBeTruthy();
  });

  it('does not show "Approvals" or "Home" or "Jobs" labels — old nav gone', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    render(<HatchNav activeTab="today" />);
    expect(screen.queryByText('Approvals')).toBeNull();
    expect(screen.queryByText('Jobs')).toBeNull();
    expect(screen.queryByText('Home')).toBeNull();
  });

  it('renders 4 anchor/link elements pointing to the 4 routes', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    const { container } = render(<HatchNav activeTab="today" />);
    const links = container.querySelectorAll('a');
    const hrefs = Array.from(links).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/today');
    expect(hrefs).toContain('/stream');
    expect(hrefs).toContain('/tracker');
    expect(hrefs).toContain('/prep');
  });

  it('identifies the active destination semantically', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    render(<HatchNav activeTab="stream" />);
    expect(screen.getByRole('link', { name: 'Pipeline' }).getAttribute('aria-current')).toBe('page');
  });

  it('lets the responsive utility hide the mobile bar on desktop', async () => {
    const { HatchNav } = await import('@/components/hatch/HatchNav');
    const { container } = render(<HatchNav activeTab="today" />);
    const nav = container.querySelector('nav') as HTMLElement;
    expect(nav.className).toContain('md:hidden');
    expect(nav.className).toContain('flex');
    expect(nav.style.display).toBe('');
  });
});

// ── HatchSidebar ──────────────────────────────────────────────────────────────
describe('HatchSidebar', () => {
  it('renders the 4 nav item labels', async () => {
    const { HatchSidebar } = await import('@/components/hatch/HatchSidebar');
    render(<HatchSidebar activeTab="today" />);
    expect(screen.getByText('Today')).toBeTruthy();
    expect(screen.getByText('Pipeline')).toBeTruthy();
    expect(screen.getByText('Applications')).toBeTruthy();
    expect(screen.getByText('Interview Prep')).toBeTruthy();
  });

  it('links to all 4 routes', async () => {
    const { HatchSidebar } = await import('@/components/hatch/HatchSidebar');
    const { container } = render(<HatchSidebar activeTab="today" />);
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/today');
    expect(hrefs).toContain('/stream');
    expect(hrefs).toContain('/tracker');
    expect(hrefs).toContain('/prep');
  });

  it('renders the Hatch brand word in the header', async () => {
    const { HatchSidebar } = await import('@/components/hatch/HatchSidebar');
    render(<HatchSidebar activeTab="today" />);
    expect(screen.getByText('Hatch')).toBeTruthy();
  });

  it('renders an "Agents" section with the 4 agent names', async () => {
    const { HatchSidebar } = await import('@/components/hatch/HatchSidebar');
    render(<HatchSidebar activeTab="today" />);
    expect(screen.getByText('Scout')).toBeTruthy();
    expect(screen.getByText('Scorer')).toBeTruthy();
    expect(screen.getByText('Tailor')).toBeTruthy();
    expect(screen.getByText('Coach')).toBeTruthy();
    expect(screen.getByText('Your agents')).toBeTruthy();
    expect(screen.queryByText('Agents running')).toBeNull();
  });

  it('does not render the old Discover/Track/Prepare nav groups', async () => {
    const { HatchSidebar } = await import('@/components/hatch/HatchSidebar');
    render(<HatchSidebar activeTab="today" />);
    expect(screen.queryByText('Discover')).toBeNull();
    expect(screen.queryByText('Shortlist')).toBeNull();
    expect(screen.queryByText('Inbox')).toBeNull();
  });
});

// ── HatchTopBar ───────────────────────────────────────────────────────────────
describe('HatchTopBar', () => {
  it('renders a greeting with "Arvind" when name provided', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    render(<HatchTopBar name="Arvind" pageTitle="Today" />);
    expect(screen.getByText(/Arvind/)).toBeTruthy();
  });

  it('renders the page title', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    render(<HatchTopBar name="Arvind" pageTitle="Stream" />);
    expect(screen.getByText('Stream')).toBeTruthy();
  });

  it('renders a search input', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    const { container } = render(<HatchTopBar name="Arvind" pageTitle="Today" />);
    expect(container.querySelector('input[type="search"], input[placeholder]')).toBeTruthy();
  });

  it('renders a bell notification button', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });
    const bellBtn = screen.getByRole('button', { name: /notification/i });
    expect(bellBtn).toBeTruthy();
  });
});

// ── HatchTopBar — live NotificationBell (Task 2) ───────────────────────────
describe('HatchTopBar — live NotificationBell', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    mockFetch.mockReset();
    global.fetch = mockFetch;
    localStorage.clear();
  });

  it('shows bell-badge count when listCompletedJobs returns 3 jobs', async () => {
    const jobs = Array.from({ length: 3 }, (_, i) => ({
      id: `j-${i}`, type: 'tailor_analyse', status: 'done',
      result: null, error: null, created_at: new Date().toISOString(),
    }));
    mockFetch.mockResolvedValue({ ok: true, json: async () => jobs });

    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    const badge = screen.getByTestId('bell-badge');
    expect(badge.textContent).toBe('3');
  });

  it('shows no badge when there are no jobs', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] });

    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    expect(screen.queryByTestId('bell-badge')).toBeNull();
  });
});
