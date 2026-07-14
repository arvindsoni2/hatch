/**
 * Task 4 — RED tests for OnboardingGate.
 * Written BEFORE the component exists.
 */
import { render, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const mockReplace = vi.fn();
const mockUsePathname = vi.fn(() => '/today');

vi.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ replace: mockReplace }),
}));

const mockGetAppLockStatus = vi.fn();

vi.mock('@/lib/api', () => ({
  getAppLockStatus: () => mockGetAppLockStatus(),
}));

describe('OnboardingGate', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockGetAppLockStatus.mockReset();
    mockUsePathname.mockReset();
    mockUsePathname.mockReturnValue('/today');
  });

  it('redirects to /onboarding when authoritative onboarding is incomplete', async () => {
    mockGetAppLockStatus.mockResolvedValue({ onboarding: { status: 'in_progress' } });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).toHaveBeenCalledWith('/onboarding');
  });

  it('does not redirect when authoritative onboarding is complete', async () => {
    mockGetAppLockStatus.mockResolvedValue({ onboarding: { status: 'complete' } });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('does not redirect when already on /onboarding (no infinite loop)', async () => {
    mockUsePathname.mockReturnValue('/onboarding');
    mockGetAppLockStatus.mockResolvedValue({ onboarding: { status: 'in_progress' } });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('renders null — no visible output', async () => {
    mockGetAppLockStatus.mockResolvedValue({ onboarding: { status: 'complete' } });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    let container!: HTMLElement;
    await act(async () => { ({ container } = render(<OnboardingGate />)); });

    expect(container.firstChild).toBeNull();
  });
});
