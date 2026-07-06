/**
 * Theme toggle in UserMenu — accessed via the user avatar dropdown in HatchTopBar.
 * The "Theme" row is a full-width menuitem button that toggles dark/light on click.
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

  it('renders a "Theme" menuitem button inside the user menu dropdown', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" />); });
    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });
    expect(screen.getByRole('menuitem', { name: /theme/i })).toBeTruthy();
  });

  it('switches to light when Theme button is clicked from dark', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" />); });

    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });

    const themeBtn = screen.getByRole('menuitem', { name: /theme/i });
    await act(async () => { fireEvent.click(themeBtn); });

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('switches back to dark on second click', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" />); });

    const avatar = screen.getByRole('button', { name: /open user menu/i });
    await act(async () => { fireEvent.click(avatar); });

    const themeBtn = screen.getByRole('menuitem', { name: /theme/i });
    await act(async () => { fireEvent.click(themeBtn); }); // → light
    await act(async () => { fireEvent.click(themeBtn); }); // → dark

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});
