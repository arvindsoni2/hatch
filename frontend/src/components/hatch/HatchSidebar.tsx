"use client";
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { HatchIcon } from './HatchIcon';
import { AGENT_DEFS, PIPELINE } from './agents';
import { Dot } from './Dot';
import type { HatchTab } from './HatchNav';
import {
  fetchPendingApprovals,
  fetchPipelineStats,
  listSessions,
} from '@/lib/api';

const NAV_ITEMS: { key: HatchTab; label: string; icon: string; href: string }[] = [
  { key: 'today',   label: 'Today',          icon: 'home',      href: '/today'   },
  { key: 'stream',  label: 'Pipeline',       icon: 'layers',    href: '/stream'  },
  { key: 'tracker', label: 'Applications',   icon: 'briefcase', href: '/tracker' },
  { key: 'prep',    label: 'Interview Prep', icon: 'mic',       href: '/prep'    },
];

interface HatchSidebarProps {
  activeTab: HatchTab;
  readyCount?: number;
}

interface BadgeCounts {
  today: number;
  stream: number;
  prep: number;
}

export function HatchSidebar({ activeTab }: HatchSidebarProps) {
  const [badges, setBadges] = useState<BadgeCounts>({ today: 0, stream: 0, prep: 0 });

  useEffect(() => {
    async function load() {
      const [approvals, pipeline, sessions] = await Promise.allSettled([
        fetchPendingApprovals(),
        fetchPipelineStats(),
        listSessions(20),
      ]);

      const todayBadge = approvals.status === 'fulfilled' ? approvals.value.length : 0;
      const streamBadge = pipeline.status === 'fulfilled'
        ? (pipeline.value.discovered ?? 0)
        : 0;
      const prepBadge = sessions.status === 'fulfilled'
        ? sessions.value.filter((s) => s.status === 'completed' || s.status === 'active').length
        : 0;

      setBadges({ today: todayBadge, stream: streamBadge, prep: prepBadge });
    }
    load();
  }, []);

  const badgeFor = (key: HatchTab): number => {
    if (key === 'today') return badges.today;
    if (key === 'stream') return badges.stream;
    if (key === 'prep') return badges.prep;
    return 0;
  };

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
      {/* Brand — Hatch layers icon */}
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <HatchIcon name="layers" size={15} color="#fff" strokeWidth={2} />
        </div>
        <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em', color: 'var(--text)' }}>
          Hatch
        </span>
      </div>

      {/* Nav items */}
      <div className="flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ key, label, icon, href }) => {
          const active = key === activeTab;
          const badge = badgeFor(key);
          return (
            <Link
              key={key}
              href={href}
              aria-current={active ? 'page' : undefined}
              className="hatch-interactive flex items-center gap-2.5 w-full font-medium"
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
              {false && badge > 0 && (
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

      {/* Agent capability card — do not imply live activity without runtime state. */}
      <div
        className="mt-4 rounded-xl"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          padding: '12px 14px',
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Dot color="var(--text-muted)" size={7} />
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', letterSpacing: '0.02em' }}>
            Your agents
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

      <div className="mt-auto" />
    </aside>
  );
}
