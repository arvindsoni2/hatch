import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { JobCard } from '../../components/JobCard';
import type { Job } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  trackFromJob: vi.fn().mockResolvedValue({}),
}));

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    title: 'Cloud Architect',
    company: 'Acme Corp',
    location: 'London, UK',
    rate_text: '£700/day',
    rate_min: 700,
    rate_max: 700,
    currency: 'GBP',
    ir35_status: null,
    contract_length: '6 months',
    description: 'Senior cloud architect role.',
    url: 'https://example.com/job-1',
    source: 'reed',
    posted_at: new Date().toISOString(),
    scraped_at: new Date().toISOString(),
    skills: ['AWS', 'Terraform'],
    is_active: true,
    sync_status: 'synced',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    employment_type: null,
    working_pattern: null,
    match_score: 0.88,
    match_reasons: null,
    skill_match: null,
    experience_match: null,
    rate_match: null,
    location_match: null,
    ghost_score: null,
    ghost_verdict: null,
    ghost_signals: null,
    ghost_analysed_at: null,
    scoring_method: null,
    score_reasoning: null,
    keyword_matches: null,
    keyword_misses: null,
    legal_fields: {},
    ...overrides,
  };
}

describe('JobCard', () => {
  it('displays company and location', () => {
    render(<JobCard job={makeJob()} />);
    // Company and location are concatenated into one meta line "Acme Corp · London, UK · …"
    expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
    expect(screen.getByText(/London, UK/)).toBeInTheDocument();
  });

  it('displays match score via ScoreBadge', () => {
    render(<JobCard job={makeJob({ match_score: 0.88 })} />);
    expect(screen.getByText('88%')).toBeInTheDocument();
  });

  it('does not show an IR35 label when ir35_status is null', () => {
    render(<JobCard job={makeJob({ ir35_status: null })} />);
    expect(screen.queryByText(/ir35/i)).not.toBeInTheDocument();
  });
});
