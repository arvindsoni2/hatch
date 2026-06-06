"use client";
import Link from 'next/link';
import { HatchIcon } from './HatchIcon';

export type HatchTab = 'today' | 'stream' | 'tracker' | 'prep';

const TABS: { key: HatchTab; label: string; icon: string; href: string }[] = [
  { key: 'today',   label: 'Today',   icon: 'home',      href: '/today'   },
  { key: 'stream',  label: 'Stream',  icon: 'layers',    href: '/stream'  },
  { key: 'tracker', label: 'Tracker', icon: 'briefcase', href: '/tracker' },
  { key: 'prep',    label: 'Prep',    icon: 'mic',       href: '/prep'    },
];

interface HatchNavProps {
  activeTab: HatchTab;
}

export function HatchNav({ activeTab }: HatchNavProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 md:hidden"
      style={{
        background: 'var(--bg-elevated)',
        borderTop: '1px solid var(--border)',
        display: 'flex',
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
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 3,
              padding: '4px 0',
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
            <span style={{ fontSize: 10.5, fontWeight: active ? 700 : 500, lineHeight: 1 }}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
