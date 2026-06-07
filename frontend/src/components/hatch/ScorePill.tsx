"use client";

interface ScorePillProps {
  score: number;
  threshold?: number;
  size?: 'md' | 'lg';
}

export function ScorePill({ score, threshold = 0.75, size = 'md' }: ScorePillProps) {
  const pct = Math.round(score * 100);
  const big = size === 'lg';

  let color: string;
  let bg: string;
  if (score >= threshold) {
    color = 'var(--success)';
    bg    = 'var(--success-soft)';
  } else if (score >= threshold * 0.66) {
    color = 'var(--warning)';
    bg    = 'var(--warning-soft)';
  } else {
    color = 'var(--text-muted)';
    bg    = 'var(--surface-2)';
  }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: big ? 54 : 42,
        padding: big ? '6px 10px' : '3px 7px',
        borderRadius: 8,
        fontFamily: 'var(--font-mono)',
        fontWeight: 700,
        fontSize: big ? 17 : 12.5,
        color,
        background: bg,
      }}
    >
      {pct}%
    </span>
  );
}
