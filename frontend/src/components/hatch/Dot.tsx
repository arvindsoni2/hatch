"use client";

interface DotProps {
  color: string;
  size?: number;
  pulse?: boolean;
}

export function Dot({ color, size = 8, pulse = false }: DotProps) {
  return (
    <span style={{ position: 'relative', width: size, height: size, flexShrink: 0, display: 'inline-block' }}>
      {pulse && (
        <span style={{ position: 'absolute', inset: -3, borderRadius: 999, background: color, opacity: 0.25 }} />
      )}
      <span style={{ position: 'absolute', inset: 0, borderRadius: 999, background: color }} />
    </span>
  );
}
