/**
 * Task 3 — RED test for dark/light ThemeToggle in HatchTopBar.
 * Written BEFORE ThemeToggle is wired into HatchTopBar.
 */
import { render, screen, act, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const mockFetch = vi.fn();

describe('HatchTopBar — ThemeToggle', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] });
    global.fetch = mockFetch;
    localStorage.clear();
    // Prime ThemeToggle to start in dark mode (localStorage is read by useEffect)
    localStorage.setItem('theme', 'dark');
    document.documentElement.setAttribute('data-theme', 'dark');
    document.documentElement.classList.add('dark');
  });

  it('renders a "Toggle dark mode" button', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });
    expect(screen.getByRole('button', { name: /toggle dark mode/i })).toBeTruthy();
  });

  it('switches to light when toggle is clicked from dark', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    const toggle = screen.getByRole('button', { name: /toggle dark mode/i });
    await act(async () => { fireEvent.click(toggle); });

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('switches back to dark on second click', async () => {
    const { HatchTopBar } = await import('@/components/hatch/HatchTopBar');
    await act(async () => { render(<HatchTopBar name="Arvind" pageTitle="Today" />); });

    const toggle = screen.getByRole('button', { name: /toggle dark mode/i });
    await act(async () => { fireEvent.click(toggle); }); // → light
    await act(async () => { fireEvent.click(toggle); }); // → dark

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});
