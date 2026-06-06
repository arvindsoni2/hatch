"use client";
import Link from 'next/link';
import { HatchIcon } from './HatchIcon';
import { AGENT_DEFS, PIPELINE } from './agents';
import { Dot } from './Dot';
import type { HatchTab } from './HatchNav';

const NAV_ITEMS: { key: HatchTab; label: string; icon: string; href: string }[] = [
  { key: 'today',   label: 'Today',   icon: 'home',      href: '/today'   },
  { key: 'stream',  label: 'Stream',  icon: 'layers',    href: '/stream'  },
  { key: 'tracker', label: 'Tracker', icon: 'briefcase', href: '/tracker' },
  { key: 'prep',    label: 'Prep',    icon: 'mic',       href: '/prep'    },
];

interface HatchSidebarProps {
  activeTab: HatchTab;
  readyCount?: number;
}

export function HatchSidebar({ activeTab, readyCount = 0 }: HatchSidebarProps) {
  return (
    <aside
      className="hidden md:flex flex-col sticky top-0 h-screen overflow-y-auto"
      style={{
        width: 'var(--sidebar-width)',
        background: 'var(--bg)',
        borderRight: '1px solid var(--border)',
        padding: '20px 14px',
        gap: 2,
      }}
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <div
          className="flex items-center justify-center font-bold text-sm rounded-lg"
          style={{
            width: 28,
            height: 28,
            background: 'var(--text)',
            color: 'var(--bg)',
            borderRadius: 8,
            fontSize: 15,
          }}
        >
          H
        </div>
        <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em', color: 'var(--text)' }}>
          Hatch
        </span>
      </div>

      {/* Nav items */}
      <div className="flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ key, label, icon, href }) => {
          const active = key === activeTab;
          const badge = key === 'today' && readyCount > 0 ? readyCount : 0;
          return (
            <Link
              key={key}
              href={href}
              className="flex items-center gap-2.5 w-full font-medium transition-colors"
              style={{
                padding: '10px 12px',
                fontSize: 13.5,
                borderRadius: 10,
                color: active ? 'var(--accent)' : 'var(--text-dim)',
                background: active ? 'var(--accent-soft)' : 'transparent',
                textDecoration: 'none',
              }}
            >
              <HatchIcon
                name={icon}
                size={16}
                color={active ? 'var(--accent)' : 'var(--text-dim)'}
                strokeWidth={active ? 2.3 : 2}
              />
              <span>{label}</span>
              {badge > 0 && (
                <span
                  className="ml-auto font-mono"
                  style={{
                    fontSize: 11,
                    padding: '1px 7px',
                    borderRadius: 999,
                    background: 'var(--accent-soft)',
                    color: 'var(--accent)',
                    fontWeight: 600,
                  }}
                >
                  {badge > 99 ? '99+' : badge}
                </span>
              )}
            </Link>
          );
        })}
      </div>

      {/* Agents running card */}
      <div
        className="mt-4 rounded-xl"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          padding: '12px 14px',
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Dot color="var(--success)" size={7} pulse />
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', letterSpacing: '0.02em' }}>
            Agents running
          </span>
        </div>
        <div className="flex flex-col gap-2.5">
          {PIPELINE.map((k) => {
            const a = AGENT_DEFS[k];
            return (
              <div key={k} className="flex items-center gap-2.5">
                <span
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 22 * 0.3,
                    background: a.soft,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <HatchIcon name={a.icon} size={11} color={a.color} strokeWidth={2.2} />
                </span>
                <div className="flex-1 min-w-0">
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{a.name}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 5 }}>{a.role}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Spacer + settings */}
      <div className="mt-auto pt-4" style={{ borderTop: '1px solid var(--border)' }}>
        <Link
          href="/settings"
          className="flex items-center gap-2.5 rounded-lg p-2 transition-colors"
          style={{ color: 'var(--text-dim)', textDecoration: 'none' }}
        >
          <HatchIcon name="settings" size={15} color="var(--text-muted)" />
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Settings</span>
        </Link>
      </div>
    </aside>
  );
}
