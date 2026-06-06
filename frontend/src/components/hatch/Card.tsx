"use client";

interface CardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  accent?: boolean;
  className?: string;
}

export function Card({ children, style, accent = false, className }: CardProps) {
  return (
    <div
      className={className}
      style={{
        background: 'var(--surface)',
        border: `1px solid ${accent ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 16,
        ...(accent ? { boxShadow: '0 0 0 3px var(--accent-soft)' } : {}),
        ...style,
      }}
    >
      {children}
    </div>
  );
}
