/**
 * Phase 4 — RED tests for Hatch shared primitives.
 * Written BEFORE any implementation exists. Every test must fail first.
 *
 * Iron Law: no production code until these are RED.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// ── AgentBadge ────────────────────────────────────────────────────────────────
describe('AgentBadge', () => {
  it('renders for each of the 4 agents without throwing', async () => {
    const { AgentBadge } = await import('@/components/hatch/AgentBadge');
    for (const agent of ['scout', 'scorer', 'tailor', 'coach'] as const) {
      const { unmount } = render(<AgentBadge agent={agent} />);
      // Each agent should render an accessible container
      unmount();
    }
  });

  it('shows a visually distinct container for scout vs tailor', async () => {
    const { AgentBadge } = await import('@/components/hatch/AgentBadge');
    const { rerender, container } = render(<AgentBadge agent="scout" />);
    const scoutBg = (container.firstChild as HTMLElement).style.background;

    rerender(<AgentBadge agent="tailor" />);
    const tailorBg = (container.firstChild as HTMLElement).style.background;

    expect(scoutBg).not.toBe(tailorBg);
  });

  it('applies a ring glow box-shadow when ring=true', async () => {
    const { AgentBadge } = await import('@/components/hatch/AgentBadge');
    const { container } = render(<AgentBadge agent="tailor" ring />);
    const el = container.firstChild as HTMLElement;
    expect(el.style.boxShadow).toMatch(/0 0 0/);
  });

  it('accepts a custom size and applies it to width/height', async () => {
    const { AgentBadge } = await import('@/components/hatch/AgentBadge');
    const { container } = render(<AgentBadge agent="scout" size={42} />);
    const el = container.firstChild as HTMLElement;
    expect(el.style.width).toBe('42px');
    expect(el.style.height).toBe('42px');
  });
});

// ── StageTrack ────────────────────────────────────────────────────────────────
describe('StageTrack', () => {
  it('renders 4 stage nodes', async () => {
    const { StageTrack } = await import('@/components/hatch/StageTrack');
    const { container } = render(<StageTrack stage={0} />);
    // 4 circular nodes
    const nodes = container.querySelectorAll('[data-stage-node]');
    expect(nodes).toHaveLength(4);
  });

  it('renders agent-name labels by default', async () => {
    const { StageTrack } = await import('@/components/hatch/StageTrack');
    render(<StageTrack stage={1} />);
    expect(screen.getByText('Scout')).toBeTruthy();
    expect(screen.getByText('Scorer')).toBeTruthy();
    expect(screen.getByText('Tailor')).toBeTruthy();
    expect(screen.getByText('Coach')).toBeTruthy();
  });

  it('shows pct label on Scorer node when stage=1 and pct provided', async () => {
    const { StageTrack } = await import('@/components/hatch/StageTrack');
    render(<StageTrack stage={1} pct={87} />);
    expect(screen.getByText('87%')).toBeTruthy();
  });

  it('hides labels in compact mode', async () => {
    const { StageTrack } = await import('@/components/hatch/StageTrack');
    render(<StageTrack stage={0} compact />);
    expect(screen.queryByText('Scout')).toBeNull();
  });
});

// ── ScorePill ─────────────────────────────────────────────────────────────────
describe('ScorePill', () => {
  it('renders the percentage integer', async () => {
    const { ScorePill } = await import('@/components/hatch/ScorePill');
    render(<ScorePill score={0.87} />);
    expect(screen.getByText('87%')).toBeTruthy();
  });

  it('uses green colour for scores at or above threshold', async () => {
    const { ScorePill } = await import('@/components/hatch/ScorePill');
    const { container } = render(<ScorePill score={0.85} threshold={0.75} />);
    // green = success = #3ddc97
    expect((container.firstChild as HTMLElement).style.color).toBe('rgb(61, 220, 151)');
  });

  it('uses amber colour for scores in the mid range', async () => {
    const { ScorePill } = await import('@/components/hatch/ScorePill');
    const { container } = render(<ScorePill score={0.6} threshold={0.75} />);
    // amber = warning = #f5b950
    expect((container.firstChild as HTMLElement).style.color).toBe('rgb(245, 185, 80)');
  });

  it('uses muted colour for low scores', async () => {
    const { ScorePill } = await import('@/components/hatch/ScorePill');
    const { container } = render(<ScorePill score={0.3} threshold={0.75} />);
    // muted = #74747f
    expect((container.firstChild as HTMLElement).style.color).toBe('rgb(116, 116, 127)');
  });

  it('renders a larger pill when size=lg', async () => {
    const { ScorePill } = await import('@/components/hatch/ScorePill');
    const { container: sm } = render(<ScorePill score={0.8} size="md" />);
    const { container: lg } = render(<ScorePill score={0.8} size="lg" />);
    const smFs = parseFloat((sm.firstChild as HTMLElement).style.fontSize);
    const lgFs = parseFloat((lg.firstChild as HTMLElement).style.fontSize);
    expect(lgFs).toBeGreaterThan(smFs);
  });
});

// ── Dot ───────────────────────────────────────────────────────────────────────
describe('Dot', () => {
  it('renders without crashing', async () => {
    const { Dot } = await import('@/components/hatch/Dot');
    const { container } = render(<Dot color="#3ddc97" />);
    expect(container.firstChild).toBeTruthy();
  });

  it('renders an extra pulse halo span when pulse=true', async () => {
    const { Dot } = await import('@/components/hatch/Dot');
    const { container: withPulse } = render(<Dot color="#3ddc97" pulse />);
    const { container: noPulse } = render(<Dot color="#3ddc97" />);
    expect(withPulse.querySelectorAll('span').length).toBeGreaterThan(
      noPulse.querySelectorAll('span').length
    );
  });
});

// ── Chip ──────────────────────────────────────────────────────────────────────
describe('Chip', () => {
  it('renders its children text', async () => {
    const { Chip } = await import('@/components/hatch/Chip');
    render(<Chip>ATS 92</Chip>);
    expect(screen.getByText('ATS 92')).toBeTruthy();
  });

  it('renders an icon element when icon prop provided', async () => {
    const { Chip } = await import('@/components/hatch/Chip');
    const { container } = render(<Chip icon="check">Done</Chip>);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
  });

  it('applies custom color to text', async () => {
    const { Chip } = await import('@/components/hatch/Chip');
    const { container } = render(<Chip color="#3ddc97">Ready</Chip>);
    expect((container.firstChild as HTMLElement).style.color).toBe('rgb(61, 220, 151)');
  });
});

// ── Btn ───────────────────────────────────────────────────────────────────────
describe('Btn', () => {
  it('renders its label text', async () => {
    const { Btn } = await import('@/components/hatch/Btn');
    render(<Btn>Review &amp; approve</Btn>);
    expect(screen.getByText('Review & approve')).toBeTruthy();
  });

  it('calls onClick when clicked', async () => {
    const { Btn } = await import('@/components/hatch/Btn');
    const onClick = vi.fn();
    render(<Btn onClick={onClick}>Click me</Btn>);
    fireEvent.click(screen.getByText('Click me'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('renders as full-width when full=true', async () => {
    const { Btn } = await import('@/components/hatch/Btn');
    const { container } = render(<Btn full>Wide</Btn>);
    expect((container.firstChild as HTMLElement).style.width).toBe('100%');
  });

  it('applies accent bg for primary kind', async () => {
    const { Btn } = await import('@/components/hatch/Btn');
    const { container } = render(<Btn kind="primary">Primary</Btn>);
    // primary uses var(--accent) or the resolved teal value
    const bg = (container.firstChild as HTMLElement).style.background;
    expect(bg).toBeTruthy();
  });

  it('renders leading icon when icon prop provided', async () => {
    const { Btn } = await import('@/components/hatch/Btn');
    const { container } = render(<Btn icon="check">With Icon</Btn>);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
  });
});

// ── UserAvatar ────────────────────────────────────────────────────────────────
describe('UserAvatar', () => {
  it('renders the initials text', async () => {
    const { UserAvatar } = await import('@/components/hatch/UserAvatar');
    render(<UserAvatar initials="AS" />);
    expect(screen.getByText('AS')).toBeTruthy();
  });

  it('has a gradient background', async () => {
    const { UserAvatar } = await import('@/components/hatch/UserAvatar');
    const { container } = render(<UserAvatar initials="AS" />);
    expect((container.firstChild as HTMLElement).style.background).toContain('gradient');
  });

  it('accepts a custom size', async () => {
    const { UserAvatar } = await import('@/components/hatch/UserAvatar');
    const { container } = render(<UserAvatar initials="AS" size={48} />);
    expect((container.firstChild as HTMLElement).style.width).toBe('48px');
  });
});
