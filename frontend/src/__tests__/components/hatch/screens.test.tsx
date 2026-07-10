/**
 * Phase 4 — RED tests for Hatch screen client components.
 * Written BEFORE any implementation exists.
 *
 * Screen components receive pre-fetched data as props (server components do the fetching;
 * client components render). This makes them straightforwardly testable.
 */
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';

// ─────────────────────────────────────────────────────────────────────────────
// Shared seed data
// ─────────────────────────────────────────────────────────────────────────────
const READY_JOB = {
  id: 'sa', title: 'Solutions Architect', company: 'Hays', loc: 'London',
  rate: '£600–675/day', score: 1.0, ats: 95, state: 'ready' as const,
};
const TAILORING_JOB = {
  id: 'soa', title: 'Solution Architect — On-Prem', company: 'Outsource UK',
  loc: 'Preston', rate: '£71–96/day', score: 0.90, ats: undefined, state: 'tailoring' as const,
};
const PARKED_JOB = {
  id: 'sv', title: 'Service Architect', company: 'Involved',
  loc: 'London', rate: '£600–675/day', score: 0.68, ats: undefined, state: 'parked' as const,
};
const ALL_JOBS = [READY_JOB, TAILORING_JOB, PARKED_JOB];

const FUNNEL = { scout: 75, scorer: 12, tailor: 3, coach: 1 };

// ─────────────────────────────────────────────────────────────────────────────
// TodayScreen
// ─────────────────────────────────────────────────────────────────────────────
describe('TodayScreen', () => {
  it('renders agent progress as supporting evidence', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Agent progress/i)).toBeTruthy();
  });

  it('shows the funnel step counts', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText('75')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('renders the Ready for you section with correct count', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Ready for you/i)).toBeTruthy();
  });

  it('renders approve card listing each ready job title', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
  });

  it('shows one outcome-led review CTA when ready jobs exist', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByRole('button', { name: 'Review roles' })).toBeTruthy();
  });

  it('shows empty state when no ready jobs', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const noReadyJobs = [TAILORING_JOB, PARKED_JOB];
    render(<TodayScreen jobs={noReadyJobs} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/No roles need review/i)).toBeTruthy();
  });

  it('gives first-use users one setup action and one Jobs link', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const onOpenCvStudio = vi.fn();

    render(
      <TodayScreen
        jobs={[]}
        funnel={{ scout: 0, scorer: 0, tailor: 0, coach: 0 }}
        profileName="Arvind"
        followUpCount={0}
        onOpenCvStudio={onOpenCvStudio}
      />,
    );

    expect(screen.getByRole('heading', { name: 'No actions yet' })).toBeTruthy();
    expect(screen.getByText('Start by uploading your Master CV or running Job Scout.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Open CV Studio' }));
    expect(onOpenCvStudio).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Browse Jobs' })).toHaveAttribute('href', '/jobs');
  });

  it('calls onReview with ready job ids when CTA clicked', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const onReview = vi.fn();
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" onReview={onReview} />);
    fireEvent.click(screen.getByRole('button', { name: 'Review roles' }));
    expect(onReview).toHaveBeenCalledWith(expect.arrayContaining(['sa']));
  });

  it('renders the follow-ups overdue card', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" followUpCount={2} />);
    expect(screen.getByText(/follow-up/i)).toBeTruthy();
  });

  it('shows finish-applying section when ready_to_apply jobs exist', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const rtaJob = { ...READY_JOB, id: 'rta1', state: 'ready_to_apply' as const, jobUrl: 'https://jobs.example.com/1' };
    render(<TodayScreen jobs={[rtaJob]} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Finish applying/i)).toBeTruthy();
    expect(screen.getByText(/Solutions Architect/i)).toBeTruthy();
  });

  it('shows new roles from watched companies separately', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const watchedJob = {
      id: 'watch-1',
      title: 'Delivery Lead',
      company: 'Example Cloud',
      loc: 'London',
      rate: '—',
      score: 0.72,
      state: 'ready' as const,
    };

    render(
      <TodayScreen
        jobs={[]}
        watchedCompanyJobs={[watchedJob]}
        funnel={FUNNEL}
        profileName="Arvind"
      />,
    );

    expect(screen.getByText('New roles from watched companies')).toBeTruthy();
    expect(screen.getByText('Delivery Lead')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open watched companies' })).toHaveAttribute('href', '/tracker/watched-companies');
  });

  it('does not show finish-applying section when no ready_to_apply jobs', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.queryByText(/Finish applying/i)).toBeNull();
  });

  it('calls onMarkApplied when Mark as applied is clicked in finish-applying section', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const onMarkApplied = vi.fn();
    const rtaJob = { ...READY_JOB, id: 'rta2', state: 'ready_to_apply' as const, jobUrl: 'https://jobs.example.com/2' };
    render(<TodayScreen jobs={[rtaJob]} funnel={FUNNEL} profileName="Arvind" onMarkApplied={onMarkApplied} />);
    fireEvent.click(screen.getByText(/Mark as applied/i));
    expect(onMarkApplied).toHaveBeenCalledWith('rta2');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// StreamScreen
// ─────────────────────────────────────────────────────────────────────────────
describe('StreamScreen', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/stream');
  });

  it('renders filter chips: All / Ready / Tailoring / Parked', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={ALL_JOBS} />);
    expect(screen.getByText('All')).toBeTruthy();
    expect(screen.getByText('Ready')).toBeTruthy();
    expect(screen.getByText('Tailoring')).toBeTruthy();
    expect(screen.getByText('Parked')).toBeTruthy();
  });

  it('shows all active jobs by default (All filter)', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={ALL_JOBS} defaultFilter="all" />);
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
    expect(screen.getByText('Solution Architect — On-Prem')).toBeTruthy();
    expect(screen.getByText('Service Architect')).toBeTruthy();
  });

  it('filters to only ready jobs when Ready chip clicked', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={ALL_JOBS} defaultFilter="all" />);
    fireEvent.click(screen.getByText('Ready'));
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
    expect(screen.queryByText('Solution Architect — On-Prem')).toBeNull();
  });

  it('shows score pill for each job card', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={ALL_JOBS} defaultFilter="all" />);
    // Each job should show a percentage (from ScorePill)
    const pills = screen.getAllByText(/\d+%/);
    expect(pills.length).toBeGreaterThanOrEqual(3);
  });

  it('shows empty state message when no jobs in filter', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={[TAILORING_JOB]} defaultFilter="ready" />);
    expect(screen.getAllByText(/No roles match this stage/i).length).toBeGreaterThan(0);
  });

  it('persists the selected Pipeline stage in the URL query string', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');

    render(<StreamScreen jobs={ALL_JOBS} defaultFilter="all" />);
    fireEvent.click(screen.getByText('Ready').closest('button')!);

    expect(new URL(window.location.href).searchParams.get('stage')).toBe('ready');
  });

  it('offers View all jobs from an empty Pipeline stage', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={[TAILORING_JOB]} defaultFilter="ready" />);

    expect(screen.getByRole('link', { name: 'View all jobs' })).toHaveAttribute('href', '/jobs?view=all');
  });

  it('calls onReview when a ready job card is clicked', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    const onReview = vi.fn();
    render(<StreamScreen jobs={[READY_JOB]} defaultFilter="ready" onReview={onReview} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate CV pack' }));
    expect(onReview).not.toHaveBeenCalled();
  });

  it('does not reopen the approval overlay for tailoring jobs', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    const onReview = vi.fn();
    render(<StreamScreen jobs={[TAILORING_JOB]} onReview={onReview} />);
    expect(screen.getByRole('button', { name: 'In progress' })).toBeDisabled();
    fireEvent.click(screen.getByText(TAILORING_JOB.title));
    expect(onReview).not.toHaveBeenCalled();
  });

  it('renders each role once instead of separate desktop and mobile copies', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={[TAILORING_JOB]} />);
    expect(screen.getAllByText(TAILORING_JOB.title)).toHaveLength(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// TrackerScreen
// ─────────────────────────────────────────────────────────────────────────────
function trackerApplication(id: string, title: string, status: 'discovered' | 'preparing' | 'ready_to_apply' | 'applied' | 'interview' | 'offered') {
  return {
    id,
    job_id: id,
    status,
    priority: 'normal' as const,
    applied_date: status === 'applied' ? '2026-06-15T08:00:00Z' : null,
    recruiter_name: null,
    agency_name: null,
    salary_offered: null,
    is_active: true,
    created_at: '2026-06-15T08:00:00Z',
    updated_at: '2026-06-15T08:00:00Z',
    job_title: title,
    job_company: 'Example Ltd',
    job_location: 'London',
    job_rate_text: 'Competitive',
    job_rate_min: null,
    job_source: 'test',
    job_url: null,
    agent_score: 0.84,
    agent_created: true,
    approval_status: 'approved',
  };
}

const TRACKER_APPS = [
  trackerApplication('d1', 'Data Architect', 'discovered'),
  trackerApplication('p1', 'Platform Architect', 'preparing'),
  trackerApplication('r1', 'Ready Architect', 'ready_to_apply'),
  trackerApplication('a1', 'Cloud Architect', 'applied'),
  trackerApplication('i1', 'Lead Architect', 'interview'),
  trackerApplication('o1', 'Enterprise Architect', 'offered'),
];

describe('TrackerScreen', () => {
  function expectActionHint(helper: string) {
    expect(document.querySelector(`[data-tooltip="${helper}"]`)).toBeTruthy();
  }

  it('renders the full left-to-right application journey', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);
    for (const name of ['Discovered', 'Preparing', 'Ready to apply', 'Applied', 'Interview', 'Offered', 'Accepted']) {
      expect(screen.getByRole('heading', { name })).toBeTruthy();
    }
  });

  it('keeps preparation and submission-ready work in distinct columns', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);
    expect(within(screen.getByTestId('col-preparing')).getByText('Platform Architect')).toBeTruthy();
    expect(within(screen.getByTestId('col-ready_to_apply')).getByText('Ready Architect')).toBeTruthy();
  });

  it('shows real offered applications instead of a hard-coded empty column', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);
    expect(within(screen.getByTestId('col-offered')).getByText('Enterprise Architect')).toBeTruthy();
  });

  it('provides a keyboard-accessible forward move control', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    const onStatusChange = vi.fn().mockResolvedValue(undefined);
    render(<TrackerScreen applications={TRACKER_APPS} onStatusChange={onStatusChange} />);
    fireEvent.change(screen.getByLabelText('Move Cloud Architect to another stage'), { target: { value: 'interview' } });
    expect(screen.getByRole('alertdialog', { name: 'Move Application?' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Move Application' }));
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith('a1', 'interview'));
    expect(within(screen.getByTestId('col-interview')).getByText('Cloud Architect')).toBeTruthy();
  });

  it('uses Move wording for the forward control instead of Drag-only language', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);

    expect(screen.getByRole('button', { name: 'Move Cloud Architect forward to Interview' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Drag Cloud Architect forward/i })).toBeNull();
  });

  it('gives first-use Applications users one primary setup action and one secondary Jobs link', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={[]} />);

    expect(screen.getByRole('heading', { name: 'No applications tracked yet' })).toBeTruthy();
    expect(screen.getByText('Start by adding the first role you want to track.')).toBeTruthy();
    expectActionHint('Use this when you applied outside Hatch or only have notes to track.');
    expectActionHint('Paste a job post link so Hatch can create the application record for you.');
    expectActionHint('Track target employers and scan for new roles from Applications.');
    expect(screen.getByRole('link', { name: 'Browse Jobs' })).toHaveAttribute('href', '/jobs');
    fireEvent.click(screen.getByRole('button', { name: 'Add manually' }));
    expect(screen.getByRole('dialog', { name: 'Add Application' })).toBeTruthy();
  });

  it('explains Applications action shortcuts when the board has active cards', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);

    expectActionHint('Track target employers and scan for new roles from Applications.');
    expectActionHint('Paste a job post link so Hatch can create the application record for you.');
    expectActionHint('Use this when you applied outside Hatch or only have notes to track.');
    expect(screen.getByRole('link', { name: 'Watched companies' })).toHaveAttribute('href', '/tracker/watched-companies');
  });

  it('explains horizontal lane scrolling when the Applications board has active cards', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen applications={TRACKER_APPS} />);

    expect(screen.getByText('Scroll sideways to see later stages.')).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// PrepScreen
// ─────────────────────────────────────────────────────────────────────────────
const PREP_SESSIONS = [
  { id: 'la', title: 'Lead Architect', company: 'Capgemini', status: 'ready' as const, when: 'Tue 9:00am',
    companyResearch: 'Capgemini UK scales cloud-migration for FS clients.',
    questions: [{ q: 'Walk me through a complex migration.', cat: 'Behavioural' as const, star: 'Situation: UK bank migration...' }] },
  { id: 'sa', title: 'Solutions Architect', company: 'Hays', status: 'progress' as const },
];

describe('PrepScreen', () => {
  it('renders each session with title and company', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} />);
    expect(screen.getByText('Lead Architect')).toBeTruthy();
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
  });

  it('shows the session status chip', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} />);
    expect(screen.getByText('Prep ready')).toBeTruthy();
    expect(screen.getByText('In progress')).toBeTruthy();
  });

  it('shows company research when a ready session is opened', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} openSessionId="la" />);
    expect(screen.getByText(/Capgemini UK scales/i)).toBeTruthy();
  });

  it('shows questions list in the detail view', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} openSessionId="la" />);
    expect(screen.getByText(/Walk me through/i)).toBeTruthy();
  });

  it('presents Question Bank as an explained Interview Prep tool', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} openSessionId="la" />);

    expect(screen.getByRole('link', { name: 'Open Question Bank' })).toHaveAttribute('href', '/prep/question-bank');
    expect(screen.getByText('Save, tag, and reuse strong interview answers across sessions.')).toBeTruthy();
  });

  it('expands a STAR answer when question is clicked', async () => {
    const { PrepScreen } = await import('@/components/hatch/screens/PrepScreen');
    render(<PrepScreen sessions={PREP_SESSIONS} openSessionId="la" />);
    fireEvent.click(screen.getByText(/Walk me through/i));
    expect(screen.getByText(/STAR ANSWER/i)).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ReviewOverlay
// ─────────────────────────────────────────────────────────────────────────────
describe('ReviewOverlay', () => {
  it('renders the job title and company', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
    expect(screen.getByText(/Hays/)).toBeTruthy();
  });

  it('shows the score and verdict', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/100%/)).toBeTruthy();
    expect(screen.getByText(/Excellent match/i)).toBeTruthy();
  });

  it('shows "Application 1 of 1" progress label', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/Application 1 of 1/i)).toBeTruthy();
  });

  it('primary button describes generating the CV pack', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /Generate CV pack/i })).toBeTruthy();
  });

  it('calls onAction("approve") when Generate CV pack is clicked', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    const onAction = vi.fn();
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={onAction}
        onClose={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /Generate CV pack/i }));
    expect(onAction).toHaveBeenCalledWith('approve');
  });

  it('calls onAction("reject") when Dismiss role is clicked', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    const onAction = vi.fn();
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={onAction}
        onClose={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /Dismiss role/i }));
    expect(onAction).toHaveBeenCalledWith('reject');
  });

  it('calls onClose when the × button is clicked', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    const onClose = vi.fn();
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={onClose}
      />
    );
    const closeBtn = screen.getByLabelText(/close/i);
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('does not claim documents exist before generation', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/No documents generated yet/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'CV' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cover letter' })).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ApplicationReadyCard
// ─────────────────────────────────────────────────────────────────────────────
const MOCK_PKG = {
  job_id: 'sa',
  job_url: 'https://boards.greenhouse.io/jobs/1',
  cv_path: '/tmp/cv.docx',
  cover_letter_path: '/tmp/cl.docx',
  cv_document_id: 'cv-doc',
  cl_document_id: 'cl-doc',
  prefill_map: { name: 'Arvind Soni', email: 'arvind@example.com' },
  screening_answers: { work_authorisation: 'British Citizen', notice_period: 'Immediately available.' },
  paste_map: { 'First Name': 'Arvind', 'Email Address': 'arvind@example.com' },
};

describe('ApplicationReadyCard', () => {
  it('renders the job title and company', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
    expect(screen.getByText(/Hays/)).toBeTruthy();
  });

  it('renders screening answers', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);
    expect(screen.getByText(/British Citizen/i)).toBeTruthy();
    expect(screen.getByText(/Immediately available/i)).toBeTruthy();
  });

  it('renders paste map fields', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);
    expect(screen.getByText(/First Name/i)).toBeTruthy();
  });

  it('renders Open application and Mark as applied buttons', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);
    expect(screen.getByText(/Open application/i)).toBeTruthy();
    expect(screen.getByText(/Mark as applied/i)).toBeTruthy();
  });

  it('calls onMarkApplied with job id when Mark as applied is clicked', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    const onMarkApplied = vi.fn();
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={onMarkApplied} onRevert={vi.fn()} />);
    fireEvent.click(screen.getByText(/Mark as applied/i));
    expect(onMarkApplied).toHaveBeenCalledWith(READY_JOB.id);
  });

  it('calls onRevert when Undo is clicked', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    const onRevert = vi.fn();
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={onRevert} />);
    fireEvent.click(screen.getByText(/Undo/i));
    expect(onRevert).toHaveBeenCalledWith(READY_JOB.id);
  });

  it('reassurance text mentions human submits', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    render(<ApplicationReadyCard job={READY_JOB} pkg={MOCK_PKG} onMarkApplied={vi.fn()} onRevert={vi.fn()} />);
    expect(screen.getByText(/Hatch prepared everything/i)).toBeTruthy();
  });

  it('offers retry and blocks mark-applied when documents are incomplete', async () => {
    const { ApplicationReadyCard } = await import('@/components/hatch/ApplicationReadyCard');
    const onRetry = vi.fn();
    const incomplete = { ...MOCK_PKG, cl_document_id: null, cover_letter_path: null };
    render(
      <ApplicationReadyCard
        job={READY_JOB}
        pkg={incomplete}
        onMarkApplied={vi.fn()}
        onRevert={vi.fn()}
        onRetry={onRetry}
      />
    );

    expect(screen.queryByText(/Mark as applied/i)).toBeNull();
    fireEvent.click(screen.getByText(/Retry documents/i));
    expect(onRetry).toHaveBeenCalledWith(READY_JOB);
  });
});
