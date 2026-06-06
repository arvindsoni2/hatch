"use client";
import { HatchIcon } from './HatchIcon';

type BtnKind = 'primary' | 'soft' | 'ghost' | 'success';
type BtnSize = 'sm' | 'md';

interface BtnProps {
  children: React.ReactNode;
  kind?: BtnKind;
  size?: BtnSize;
  icon?: string;
  iconR?: string;
  full?: boolean;
  style?: React.CSSProperties;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
}

const KIND_STYLES: Record<BtnKind, React.CSSProperties> = {
  primary: { background: 'var(--accent)', color: '#fff', border: 'none' },
  soft:    { background: '#1d1d25', color: '#f1f1f4', border: '1px solid #26262f' },
  ghost:   { background: 'transparent', color: '#a8a8b3', border: '1px solid #26262f' },
  success: { background: '#3ddc97', color: '#06231a', border: 'none' },
};

export function Btn({
  children,
  kind = 'primary',
  size = 'md',
  icon,
  iconR,
  full = false,
  style,
  onClick,
  type = 'button',
  disabled,
}: BtnProps) {
  const pad  = size === 'sm' ? '8px 12px' : '11px 16px';
  const fs   = size === 'sm' ? 13 : 14;
  const kStyle = KIND_STYLES[kind];
  const iconColor = String(kStyle.color ?? 'currentColor');

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 7,
        padding: pad,
        borderRadius: 10,
        fontSize: fs,
        fontWeight: 600,
        fontFamily: 'var(--font-sans)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        whiteSpace: 'nowrap',
        width: full ? '100%' : 'auto',
        opacity: disabled ? 0.5 : 1,
        ...kStyle,
        ...style,
      }}
    >
      {icon  && <HatchIcon name={icon}  size={fs + 2} color={iconColor} strokeWidth={2.2} />}
      {children}
      {iconR && <HatchIcon name={iconR} size={fs + 2} color={iconColor} strokeWidth={2.2} />}
    </button>
  );
}
