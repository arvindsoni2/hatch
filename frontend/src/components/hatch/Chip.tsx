"use client";
import { HatchIcon } from './HatchIcon';

interface ChipProps {
  children: React.ReactNode;
  color?: string;
  bg?: string;
  icon?: string;
  style?: React.CSSProperties;
}

export function Chip({ children, color = '#a8a8b3', bg = '#1d1d25', icon, style }: ChipProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 8px',
        borderRadius: 999,
        fontSize: 11.5,
        fontWeight: 600,
        letterSpacing: '0.01em',
        color,
        background: bg,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {icon && <HatchIcon name={icon} size={11} color={color} strokeWidth={2.4} />}
      {children}
    </span>
  );
}
