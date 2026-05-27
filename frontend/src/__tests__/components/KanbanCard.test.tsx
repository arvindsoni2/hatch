import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { KanbanCard } from '../../components/KanbanCard';
import type { ApplicationListItem } from '@/lib/api';

function makeApplication(overrides: Partial<ApplicationListItem> = {}): ApplicationListItem {
  return {
    id: 'app-1',
    job_id: 'job-1',
    status: 'applied',
    priority: 'normal',
    applied_date: null,
    recruiter_name: null,
    agency_name: null,
    salary_offered: null,
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    job_title: 'Cloud Architect',
    job_company: 'Acme Corp',
    job_location: 'London, UK',
    job_rate_text: '£700/day',
    job_rate_min: 700,
    job_source: 'reed',
    agent_score: null,
    agent_created: false,
    approval_status: null,
    ...overrides,
  };
}

describe('KanbanCard', () => {
  it('shows job title when provided', () => {
    render(<KanbanCard application={makeApplication({ job_title: 'Senior Architect' })} />);
    expect(screen.getByText('Senior Architect')).toBeInTheDocument();
  });

  it('does not show "Untitled Application" when job_title is present', () => {
    render(<KanbanCard application={makeApplication({ job_title: 'Cloud Architect' })} />);
    expect(screen.queryByText('Untitled Application')).not.toBeInTheDocument();
  });

  it('falls back to "Untitled Application" when no job_title or agency_name', () => {
    render(<KanbanCard application={makeApplication({ job_title: null, agency_name: null })} />);
    expect(screen.getByText('Untitled Application')).toBeInTheDocument();
  });
});
