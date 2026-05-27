import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ScoreBadge } from '../../components/ScoreBadge';

describe('ScoreBadge', () => {
  it('renders green badge when score is above threshold', () => {
    render(<ScoreBadge score={0.85} threshold={0.75} />);
    const badge = screen.getByText('85%');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain('bg-green-100');
  });

  it('renders amber badge when score is between 0.5 and threshold', () => {
    render(<ScoreBadge score={0.60} threshold={0.75} />);
    const badge = screen.getByText('60%');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain('bg-amber-100');
  });

  it('renders grey badge when score is below 0.5', () => {
    render(<ScoreBadge score={0.30} threshold={0.75} />);
    const badge = screen.getByText('30%');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain('bg-slate-100');
  });

  it('renders dash when score is null', () => {
    render(<ScoreBadge score={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
