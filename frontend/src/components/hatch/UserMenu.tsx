"use client";
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { HatchIcon } from './HatchIcon';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface UserMenuProps {
  name: string;
  role?: string;
}

const QUICK_LINKS: { label: string; icon: string; href: string }[] = [
  { label: 'Analytics', icon: 'trending', href: '/analytics' },
];

const SETTINGS_ITEMS: { label: string; icon: string; href: string }[] = [
  { label: 'Profile',         icon: 'user',     href: '/settings/profile'     },
  { label: 'Job Preferences', icon: 'briefcase', href: '/settings/preferences' },
  { label: 'AI Provider',     icon: 'zap',      href: '/settings/ai'          },
  { label: 'Master CV',       icon: 'fileText', href: '/settings/resume'      },
  { label: 'Security',        icon: 'lock',     href: '/settings/security'    },
  { label: 'Diagnostics',     icon: 'settings', href: '/settings/system'      },
];

function getInitials(name: string): string {
  return name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
}

const menuRow: React.CSSProperties = {
  width: '100%',
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '9px 16px',
  minHeight: 44,
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontSize: 13,
  textAlign: 'left',
};

export function UserMenu({ name, role }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const router = useRouter();
  const initials = getInitials(name);

  useEffect(() => {
    const stored = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setIsDark(stored === 'dark' || (!stored && prefersDark));
  }, []);

  const handleThemeToggle = () => {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle('dark', next);
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');
    localStorage.setItem('theme', next ? 'dark' : 'light');
  };

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <button
          aria-label="Open user menu"
          aria-haspopup="menu"
          className="hatch-interactive"
          style={{
          width: 44,
          height: 44,
          borderRadius: '50%',
          background: 'var(--accent)',
          color: 'var(--on-accent)',
          fontSize: 12,
          fontWeight: 700,
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          }}
        >
          {initials}
        </button>
      </PopoverTrigger>

      <PopoverContent
          className="min-w-[220px] overflow-hidden p-0"
          role="menu"
          aria-label="User menu"
        >
          {/* Identity header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '14px 16px',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{
              width: 36, height: 36,
              borderRadius: '50%',
              background: 'var(--accent)',
              color: 'var(--on-accent)',
              fontSize: 13, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              {initials}
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{name}</div>
              {role && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 1 }}>{role}</div>}
            </div>
          </div>

          {/* Quick links (Analytics) */}
          <div style={{ padding: '6px 0' }}>
            {QUICK_LINKS.map(({ label, icon, href }) => (
              <button
                key={label}
                role="menuitem"
                onClick={() => { setOpen(false); router.push(href); }}
                style={{ ...menuRow, color: 'var(--text)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
              >
                <HatchIcon name={icon} size={15} color="var(--text-dim)" />
                {label}
              </button>
            ))}
          </div>

          {/* Settings items */}
          <div style={{ padding: '6px 0', borderTop: '1px solid var(--border)' }}>
            {SETTINGS_ITEMS.map(({ label, icon, href }) => (
              <button
                key={label}
                role="menuitem"
                onClick={() => { setOpen(false); router.push(href); }}
                style={{ ...menuRow, color: 'var(--text)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
              >
                <HatchIcon name={icon} size={15} color="var(--text-dim)" />
                {label}
              </button>
            ))}
          </div>

          {/* Theme row */}
          <div style={{ borderTop: '1px solid var(--border)', padding: '6px 0' }}>
            <button
              role="menuitem"
              onClick={handleThemeToggle}
              style={{ ...menuRow, color: 'var(--text)' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
            >
              <HatchIcon name={isDark ? 'sun' : 'moon'} size={15} color="var(--text-dim)" />
              Theme
            </button>
          </div>

          {/* Re-run Onboarding */}
          <div style={{ borderTop: '1px solid var(--border)', padding: '6px 0' }}>
            <button
              role="menuitem"
              onClick={() => { setOpen(false); router.push('/onboarding'); }}
              style={{ ...menuRow, color: 'var(--text-muted)' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
            >
              <HatchIcon name="compass" size={15} color="var(--text-muted)" />
              Re-run Onboarding
            </button>
          </div>
      </PopoverContent>
    </Popover>
  );
}
