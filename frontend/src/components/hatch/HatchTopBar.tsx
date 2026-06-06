"use client";
import { HatchIcon } from './HatchIcon';
import { UserAvatar } from './UserAvatar';

interface HatchTopBarProps {
  name: string;
  pageTitle: string;
  pageSub?: string;
  notifCount?: number;
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export function HatchTopBar({ name, pageTitle, pageSub, notifCount = 0 }: HatchTopBarProps) {
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

  return (
    <header
      className="hidden md:flex items-center gap-4 sticky top-0 z-30"
      style={{
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        padding: '0 32px',
        height: 60,
        flexShrink: 0,
      }}
    >
      {/* Greeting + page title */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-3">
          <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)' }}>
            {pageTitle}
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {pageSub ?? `${getGreeting()}, ${name}`}
          </span>
        </div>
      </div>

      {/* Search */}
      <div className="relative" style={{ width: 240 }}>
        <HatchIcon
          name="search"
          size={15}
          color="var(--text-muted)"
          style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}
        />
        <input
          type="search"
          placeholder="Search roles…"
          aria-label="Search roles"
          style={{
            width: '100%',
            padding: '7px 10px 7px 32px',
            borderRadius: 9,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            fontSize: 13,
            outline: 'none',
          }}
        />
      </div>

      {/* Bell */}
      <button
        aria-label="Notifications"
        style={{
          position: 'relative',
          width: 36,
          height: 36,
          borderRadius: 9,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        <HatchIcon name="bell" size={17} color="var(--text-dim)" />
        {notifCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: -3,
              right: -3,
              width: 16,
              height: 16,
              borderRadius: 999,
              background: 'var(--danger)',
              border: '2px solid var(--bg)',
              fontSize: 9,
              fontWeight: 700,
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {notifCount > 9 ? '9+' : notifCount}
          </span>
        )}
      </button>

      <UserAvatar initials={initials} size={32} />
    </header>
  );
}
