"use client";
import { useState } from 'react';
import { Card } from '../Card';
import { ScorePill } from '../ScorePill';
import { StageTrack } from '../StageTrack';
import { Btn } from '../Btn';
import { Dot } from '../Dot';
import { HatchIcon } from '../HatchIcon';
import type { HatchJob } from './TodayScreen';

type StreamFilter = 'all' | 'ready' | 'tailoring' | 'parked';

const STATUS_META: Record<string, { label: string; color: string }> = {
  ready:     { label: 'Ready for your approval', color: 'var(--success)' },
  tailoring: { label: 'Tailor is writing your CV…', color: 'var(--success)' },
  parked:    { label: 'Parked · just below your 75% bar', color: 'var(--warning)' },
  applied:   { label: 'Applied · awaiting reply', color: 'var(--accent)' },
  rejected:  { label: 'Dismissed', color: 'var(--text-muted)' },
};

function stageOf(job: HatchJob): number {
  if (job.state === 'ready')     return 3;
  if (job.state === 'tailoring') return 2;
  return 1;
}

interface StreamScreenProps {
  jobs: HatchJob[];
  defaultFilter?: StreamFilter;
  onReview?: (ids: string[]) => void;
  onApprove?: (id: string) => void;
}

export function StreamScreen({ jobs, defaultFilter = 'ready', onReview, onApprove }: StreamScreenProps) {
  const [filter, setFilter] = useState<StreamFilter>(defaultFilter);

  const counts = {
    all:      jobs.filter((j) => j.state !== 'applied' && j.state !== 'rejected').length,
    ready:    jobs.filter((j) => j.state === 'ready').length,
    tailoring:jobs.filter((j) => j.state === 'tailoring').length,
    parked:   jobs.filter((j) => j.state === 'parked').length,
  };

  const filtered = jobs.filter((j) => {
    if (j.state === 'applied' || j.state === 'rejected') return false;
    if (filter === 'all') return true;
    return j.state === filter;
  });

  const CHIPS: { key: StreamFilter; label: string }[] = [
    { key: 'all',      label: 'All'      },
    { key: 'ready',    label: 'Ready'    },
    { key: 'tailoring',label: 'Tailoring'},
    { key: 'parked',   label: 'Parked'   },
  ];

  return (
    <div>
      {/* Mobile header */}
      <div className="md:hidden" style={{ padding: '8px 0 14px' }}>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Stream</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>Every role · every stage</div>
      </div>

      {/* Filter chips */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto', paddingBottom: 2 }}>
        {CHIPS.map(({ key, label }) => {
          const active = key === filter;
          return (
            <button
              key={key}
              onClick={() => setFilter(key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '7px 12px', borderRadius: 999, cursor: 'pointer',
                fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap',
                background: active ? 'var(--accent-soft)' : 'var(--surface)',
                color: active ? 'var(--accent)' : 'var(--text-dim)',
                border: `1px solid ${active ? 'transparent' : 'var(--border)'}`,
              }}
            >
              {label}
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, opacity: 0.8 }}>
                {counts[key]}
              </span>
            </button>
          );
        })}
      </div>

      {/* Job list — card layout; desktop adds a table view via Tailwind override */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 11, paddingBottom: 18 }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: 13 }}>
            Nothing in this stage right now.
          </div>
        ) : (
          filtered.map((job) => {
            const ready = job.state === 'ready';
            const m = STATUS_META[job.state] ?? STATUS_META.tailoring;
            return (
              <Card key={job.id} accent={ready} style={{ padding: 14 }}>
                <button
                  onClick={() => onReview?.([job.id])}
                  style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text)' }}>{job.title}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 3 }}>
                        {job.company} · {job.loc} · <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>{job.rate}</span>
                      </div>
                    </div>
                    <ScorePill score={job.score} />
                  </div>
                  <StageTrack stage={stageOf(job)} pct={Math.round(job.score * 100)} />
                </button>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: m.color, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                    {ready && <Dot color={m.color} size={6} pulse />}{m.label}
                  </span>
                  {ready
                    ? <Btn kind="success" size="sm" icon="check" onClick={() => onApprove?.(job.id)}>Approve</Btn>
                    : <HatchIcon name="chevronR" size={16} color="var(--text-muted)" />
                  }
                </div>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
