"use client";
import { NotificationBell } from '@/components/NotificationBell';
import { ThemeToggle } from '@/components/ThemeToggle';

export function HatchMobileBar() {
  return (
    <div
      className="md:hidden flex items-center justify-between sticky top-0 z-30 px-4"
      style={{
        height: 52,
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--accent)' }}>H</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <ThemeToggle />
        <NotificationBell />
      </div>
    </div>
  );
}
