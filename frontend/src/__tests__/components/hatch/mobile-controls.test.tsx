/**
 * Task 6 — RED tests for HatchMobileBar.
 * Written BEFORE the component exists.
 */
import { render, screen, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const mockFetch = vi.fn();

describe('HatchMobileBar', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] });
    global.fetch = mockFetch;
    localStorage.clear();
  });

  it('renders a notifications button', async () => {
    const { HatchMobileBar } = await import('@/components/hatch/HatchMobileBar');
    await act(async () => { render(<HatchMobileBar />); });
    expect(screen.getByRole('button', { name: /notifications/i })).toBeTruthy();
  });

  it('renders a theme toggle button', async () => {
    const { HatchMobileBar } = await import('@/components/hatch/HatchMobileBar');
    await act(async () => { render(<HatchMobileBar />); });
    expect(screen.getByRole('button', { name: /toggle dark mode/i })).toBeTruthy();
  });

  it('renders an account menu for mobile settings access', async () => {
    const { HatchMobileBar } = await import('@/components/hatch/HatchMobileBar');
    await act(async () => { render(<HatchMobileBar />); });
    expect(screen.getByRole('button', { name: /open user menu/i })).toBeTruthy();
  });

  it('has md:hidden class so it is desktop-hidden', async () => {
    const { HatchMobileBar } = await import('@/components/hatch/HatchMobileBar');
    let container!: HTMLElement;
    await act(async () => { ({ container } = render(<HatchMobileBar />)); });
    const bar = container.firstElementChild as HTMLElement;
    expect(bar?.className).toContain('md:hidden');
  });

  it('shows bell badge count when listCompletedJobs returns jobs', async () => {
    const jobs = Array.from({ length: 2 }, (_, i) => ({
      id: `j-${i}`, type: 'tailor_analyse', status: 'done',
      result: null, error: null, created_at: new Date().toISOString(),
    }));
    mockFetch.mockResolvedValue({ ok: true, json: async () => jobs });

    const { HatchMobileBar } = await import('@/components/hatch/HatchMobileBar');
    await act(async () => { render(<HatchMobileBar />); });

    const badge = screen.getByTestId('bell-badge');
    expect(badge.textContent).toBe('2');
  });
});
