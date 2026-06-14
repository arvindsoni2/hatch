/**
 * Phase 4 — RED tests for Hatch screen client components.
 * Written BEFORE any implementation exists.
 *
 * Screen components receive pre-fetched data as props (server components do the fetching;
 * client components render). This makes them straightforwardly testable.
 */
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

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
  it('renders the briefing card with agent status', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Agents active/i)).toBeTruthy();
  });

  it('shows the funnel step counts', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText('75')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('renders the Needs you section with correct count', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Needs you/i)).toBeTruthy();
  });

  it('renders approve card listing each ready job title', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText('Solutions Architect')).toBeTruthy();
  });

  it('shows "Review & approve" CTA when ready jobs exist', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Review.*approve/i)).toBeTruthy();
  });

  it('shows empty state when no ready jobs', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const noReadyJobs = [TAILORING_JOB, PARKED_JOB];
    render(<TodayScreen jobs={noReadyJobs} funnel={FUNNEL} profileName="Arvind" />);
    expect(screen.getByText(/Approval queue clear/i)).toBeTruthy();
  });

  it('calls onReview with ready job ids when CTA clicked', async () => {
    const { TodayScreen } = await import('@/components/hatch/screens/TodayScreen');
    const onReview = vi.fn();
    render(<TodayScreen jobs={ALL_JOBS} funnel={FUNNEL} profileName="Arvind" onReview={onReview} />);
    fireEvent.click(screen.getByText(/Review.*approve/i));
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
    // StreamScreen renders dual layouts (mobile + desktop); use getAllByText to handle both
    expect(screen.getAllByText('Solutions Architect').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Solution Architect — On-Prem').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Service Architect').length).toBeGreaterThan(0);
  });

  it('filters to only ready jobs when Ready chip clicked', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    render(<StreamScreen jobs={ALL_JOBS} defaultFilter="all" />);
    fireEvent.click(screen.getByText('Ready'));
    expect(screen.getAllByText('Solutions Architect').length).toBeGreaterThan(0);
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
    expect(screen.getAllByText(/Nothing in this stage/i).length).toBeGreaterThan(0);
  });

  it('calls onReview when a ready job card is clicked', async () => {
    const { StreamScreen } = await import('@/components/hatch/screens/StreamScreen');
    const onReview = vi.fn();
    render(<StreamScreen jobs={[READY_JOB]} defaultFilter="ready" onReview={onReview} />);
    // StreamScreen renders dual layouts; click the first instance of the title
    fireEvent.click(screen.getAllByText('Solutions Architect')[0]);
    expect(onReview).toHaveBeenCalledWith([READY_JOB.id]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// TrackerScreen
// ─────────────────────────────────────────────────────────────────────────────
const APPLIED_JOB = { id: 'ca', title: 'Cloud Architect', company: 'Lloyds', loc: 'Remote', rate: '£650/day', score: 0.84, state: 'applied' as const };
const INTERVIEW_JOB = { id: 'la', title: 'Lead Architect', company: 'Capgemini', loc: 'London', rate: '£700/day', score: 0.91, state: 'interview' as const, when: 'Tue 9:00am' };

describe('TrackerScreen', () => {
  it('renders the 4 kanban column headers', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen jobs={ALL_JOBS} appliedJobs={[APPLIED_JOB]} interviewJobs={[INTERVIEW_JOB]} />);
    expect(screen.getByText('Discovered')).toBeTruthy();
    expect(screen.getByText('Applied')).toBeTruthy();
    expect(screen.getByText('Interview')).toBeTruthy();
    expect(screen.getByText('Offered')).toBeTruthy();
  });

  it('puts discovered/tailoring/parked jobs in the Discovered column', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen jobs={ALL_JOBS} appliedJobs={[]} interviewJobs={[]} />);
    // All 3 seeded jobs are in Discovered
    const discoveredCol = screen.getByTestId('col-discovered');
    expect(within(discoveredCol).getByText('Solutions Architect')).toBeTruthy();
  });

  it('puts applied jobs in the Applied column', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen jobs={ALL_JOBS} appliedJobs={[APPLIED_JOB]} interviewJobs={[]} />);
    const appliedCol = screen.getByTestId('col-applied');
    expect(within(appliedCol).getByText('Cloud Architect')).toBeTruthy();
  });

  it('shows empty dashed placeholder for the Offered column', async () => {
    const { TrackerScreen } = await import('@/components/hatch/screens/TrackerScreen');
    render(<TrackerScreen jobs={ALL_JOBS} appliedJobs={[]} interviewJobs={[]} />);
    const offeredCol = screen.getByTestId('col-offered');
    expect(within(offeredCol).getByText(/Nothing here yet/i)).toBeTruthy();
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

  it('primary button says "Approve & prepare"', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /Approve.*prepare/i })).toBeTruthy();
  });

  it('calls onAction("approve") when Approve & prepare button clicked', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /Approve.*prepare/i }));
    expect(onAction).toHaveBeenCalledWith('approve');
  });

  it('calls onAction("reject") when Reject button clicked', async () => {
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
    fireEvent.click(screen.getByText(/Reject/i));
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

  it('renders both CV and Cover Letter tab buttons', async () => {
    const { ReviewOverlay } = await import('@/components/hatch/ReviewOverlay');
    render(
      <ReviewOverlay
        queue={[READY_JOB]}
        idx={0}
        onAction={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText('CV')).toBeTruthy();
    expect(screen.getByText('Cover letter')).toBeTruthy();
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
