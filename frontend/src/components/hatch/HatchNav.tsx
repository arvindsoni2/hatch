"use client";
import Link from 'next/link';
import { HatchIcon } from './HatchIcon';

export type HatchTab = 'today' | 'stream' | 'tracker' | 'tailor' | 'prep';

const TABS: { key: HatchTab; label: string; icon: string; href: string }[] = [
  { key: 'today',   label: 'Today',          icon: 'home',      href: '/today'   },
  { key: 'stream',  label: 'Pipeline',       icon: 'layers',    href: '/stream'  },
  { key: 'tracker', label: 'Applications',   icon: 'briefcase', href: '/tracker' },
  { key: 'tailor',  label: 'CV Studio',      icon: 'fileText',  href: '/tailor'  },
  { key: 'prep',    label: 'Interview Prep', icon: 'mic',       href: '/prep'    },
];

interface HatchNavProps {
  activeTab: HatchTab | null;
}

export function HatchNav({ activeTab }: HatchNavProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden"
      style={{
        background: 'var(--bg-elevated)',
        borderTop: '1px solid var(--border)',
        padding: '8px 8px 4px',
        paddingBottom: 'calc(8px + env(safe-area-inset-bottom, 0px))',
      }}
    >
      {TABS.map(({ key, label, icon, href }) => {
        const active = key === activeTab;
        return (
          <Link
            key={key}
            href={href}
            data-active={active}
            aria-current={active ? 'page' : undefined}
            className="hatch-interactive"
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 3,
              padding: '4px 2px',
              textDecoration: 'none',
              color: active ? 'var(--accent)' : 'var(--text-muted)',
            }}
          >
            <HatchIcon
              name={icon}
              size={21}
              color={active ? 'var(--accent)' : 'var(--text-muted)'}
              strokeWidth={active ? 2.3 : 2}
            />
            <span style={{ fontSize: 10, fontWeight: active ? 700 : 500, lineHeight: 1, whiteSpace: 'nowrap' }}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
