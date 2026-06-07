/**
 * UserMenu — user settings dropdown triggered by the avatar in the top bar.
 *
 * TDD: these tests were written BEFORE the component existed.
 * Iron Law: every test must fail before implementation starts.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('UserMenu', () => {
  const defaultProps = { name: 'Arvind Soni', role: 'Delivery Lead' };

  it('renders avatar button with user initials', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /open user menu/i });
    expect(btn).toBeTruthy();
    // Initials "AS" derived from "Arvind Soni"
    expect(btn.textContent).toContain('AS');
  });

  it('dropdown is hidden by default', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    // The menu panel should not be in the DOM initially
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens dropdown on avatar click', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByRole('menu')).toBeTruthy();
  });

  it('shows user name in dropdown header', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByText('Arvind Soni')).toBeTruthy();
  });

  it('shows user role subtitle in dropdown header', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByText('Delivery Lead')).toBeTruthy();
  });

  it('renders all 4 settings navigation items', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByText('Profile & CV')).toBeTruthy();
    expect(screen.getByText('AI Provider')).toBeTruthy();
    expect(screen.getByText('System & Logs')).toBeTruthy();
    expect(screen.getByText('Resume')).toBeTruthy();
  });

  it('renders Appearance row with ThemeToggle', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByText('Appearance')).toBeTruthy();
    // ThemeToggle renders a button with aria-label="Toggle dark mode"
    expect(screen.getByRole('button', { name: /toggle dark mode/i })).toBeTruthy();
  });

  it('renders Re-run Onboarding at the bottom', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByText('Re-run Onboarding')).toBeTruthy();
  });

  it('closes dropdown when Escape is pressed', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /open user menu/i }));
    expect(screen.getByRole('menu')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('avatar button has aria-expanded=false when closed', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /open user menu/i });
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('avatar button has aria-expanded=true when open', async () => {
    const { UserMenu } = await import('@/components/hatch/UserMenu');
    render(<UserMenu {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /open user menu/i });
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });
});
