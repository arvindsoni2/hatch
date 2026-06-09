"use client";

interface CardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  accent?: boolean;
  className?: string;
  onClick?: React.MouseEventHandler<HTMLDivElement>;
}

export function Card({ children, style, accent = false, className, onClick }: CardProps) {
  return (
    <div
      className={className}
      onClick={onClick}
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
