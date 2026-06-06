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
    color = '#3ddc97';           // success
    bg    = 'rgba(61,220,151,0.14)';
  } else if (score >= threshold * 0.66) {
    color = '#f5b950';           // warning
    bg    = 'rgba(245,185,80,0.14)';
  } else {
    color = '#74747f';           // muted
    bg    = '#1d1d25';
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
