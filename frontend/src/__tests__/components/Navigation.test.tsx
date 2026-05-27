import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { Navigation } from '../../components/Navigation';

vi.mock('@/lib/api', () => ({
  fetchPendingApprovals: vi.fn().mockResolvedValue([]),
}));

import { fetchPendingApprovals } from '@/lib/api';

describe('Navigation', () => {
  beforeEach(() => {
    vi.mocked(fetchPendingApprovals).mockResolvedValue([]);
  });

  it('renders all nav items', () => {
    render(<Navigation />);
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByText('Approvals')).toBeInTheDocument();
    expect(screen.getByText('Pipeline')).toBeInTheDocument();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Interview prep')).toBeInTheDocument();
  });

  it('does not render Auto Apply', () => {
    render(<Navigation />);
    expect(screen.queryByText(/auto\s*apply/i)).not.toBeInTheDocument();
  });

  it('shows approval badge count when pending approvals exist', async () => {
    vi.mocked(fetchPendingApprovals).mockResolvedValue([
      { id: 'a1' } as never,
      { id: 'a2' } as never,
    ]);
    render(<Navigation />);
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });
});
