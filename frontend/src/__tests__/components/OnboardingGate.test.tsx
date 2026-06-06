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

const mockFetchProfileStatus = vi.fn();

vi.mock('@/lib/api', () => ({
  fetchProfileStatus: () => mockFetchProfileStatus(),
}));

describe('OnboardingGate', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchProfileStatus.mockReset();
    mockUsePathname.mockReset();
    mockUsePathname.mockReturnValue('/today');
  });

  it('redirects to /onboarding when onboarding_required is true', async () => {
    mockFetchProfileStatus.mockResolvedValue({ candidate_name: '', onboarding_required: true });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).toHaveBeenCalledWith('/onboarding');
  });

  it('does not redirect when onboarding_required is false', async () => {
    mockFetchProfileStatus.mockResolvedValue({ candidate_name: 'Arvind', onboarding_required: false });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('does not redirect when already on /onboarding (no infinite loop)', async () => {
    mockUsePathname.mockReturnValue('/onboarding');
    mockFetchProfileStatus.mockResolvedValue({ candidate_name: '', onboarding_required: true });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    await act(async () => { render(<OnboardingGate />); });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('renders null — no visible output', async () => {
    mockFetchProfileStatus.mockResolvedValue({ candidate_name: 'Arvind', onboarding_required: false });

    const { OnboardingGate } = await import('@/components/OnboardingGate');
    let container!: HTMLElement;
    await act(async () => { ({ container } = render(<OnboardingGate />)); });

    expect(container.firstChild).toBeNull();
  });
});
