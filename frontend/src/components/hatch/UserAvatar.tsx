"use client";

interface UserAvatarProps {
  initials?: string;
  size?: number;
}

export function UserAvatar({ initials = 'AS', size = 32 }: UserAvatarProps) {
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: 999,
        flexShrink: 0,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg,#f97316,#ec4899)',
        color: '#fff',
        fontWeight: 700,
        fontSize: size * 0.36,
      }}
    >
      {initials}
    </span>
  );
}
