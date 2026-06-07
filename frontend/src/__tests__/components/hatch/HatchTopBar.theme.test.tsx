/**
 * ThemeToggle in UserMenu — accessed via the user avatar dropdown in HatchTopBar.
 * (Previously tested ThemeToggle as a standalone button in the top bar;
 *  v4.1 UserMenu moved it into the dropdown for cleaner UX.)
 */
import { render, screen, act, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => '/today'),
}));

const mockFetch = vi.fn();

describe('HatchTopBar — ThemeToggle (via UserMenu)', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] });
    global.fetch = mockFetch;
    localStorage.clear();
    localStorage.setItem('theme', 'dark');
    document.documentElement.setAttribute('data-theme', 'dark');
    document.documentElement.classList.add('dark');
  });

  it('renders a "Toggle dark mode" button inside the user menu dropdown', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });
    // Toggle is inside the dropdown — open it first
    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });
    expect(screen.getByRole('button', { name: /toggle dark mode/i })).toBeTruthy();
  });

  it('switches to light when toggle is clicked from dark', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });

    const toggle = screen.getByRole('button', { name: /toggle dark mode/i });
    await act(async () => { fireEvent.click(toggle); });

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('switches back to dark on second click', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });

    const toggle = screen.getByRole('button', { name: /toggle dark mode/i });
    await act(async () => { fireEvent.click(toggle); }); // → light
    await act(async () => { fireEvent.click(toggle); }); // → dark

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});
