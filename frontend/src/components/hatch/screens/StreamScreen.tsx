"use client";
import { useState } from 'react';
import { Card } from '../Card';
import { ScorePill } from '../ScorePill';
import { StageTrack } from '../StageTrack';
import { Btn } from '../Btn';
import { Dot } from '../Dot';
import { HatchIcon } from '../HatchIcon';
import { useIsMobile } from '@/hooks/useMediaQuery';
import type { HatchJob } from './TodayScreen';

type StreamFilter = 'all' | 'ready' | 'tailoring' | 'apply' | 'parked';

const STATUS_META: Record<string, { label: string; color: string; dot: boolean }> = {
  ready:          { label: 'Ready to send',   color: 'var(--success)',    dot: true  },
  tailoring:      { label: 'Tailoring…',      color: 'var(--success)',    dot: false },
  ready_to_apply: { label: 'Ready to apply',  color: 'var(--warning)',    dot: true  },
  parked:         { label: 'Below match bar', color: 'var(--warning)',    dot: false },
  applied:        { label: 'Applied',         color: 'var(--accent)',     dot: false },
  rejected:       { label: 'Dismissed',       color: 'var(--text-muted)', dot: false },
};

function stageOf(job: HatchJob): number {
  if (job.state === 'ready_to_apply') return 4;
  if (job.state === 'ready')          return 3;
  if (job.state === 'tailoring')      return 2;
  return 1;
}

interface StreamScreenProps {
  jobs: HatchJob[];
  defaultFilter?: StreamFilter;
  onReview?: (ids: string[]) => void;
  onApprove?: (id: string, jobPostingId?: string) => void;
  approvingId?: string | null;
}

export function StreamScreen({ jobs, defaultFilter = 'all', onReview, onApprove, approvingId }: StreamScreenProps) {
  const [filter, setFilter] = useState<StreamFilter>(defaultFilter);
  const isMobile = useIsMobile();

  const counts = {
    all:      jobs.filter((j) => j.state !== 'applied' && j.state !== 'rejected').length,
    ready:    jobs.filter((j) => j.state === 'ready').length,
    tailoring:jobs.filter((j) => j.state === 'tailoring').length,
    apply:    jobs.filter((j) => j.state === 'ready_to_apply').length,
    parked:   jobs.filter((j) => j.state === 'parked').length,
  };

  const filtered = jobs.filter((j) => {
    if (j.state === 'applied' || j.state === 'rejected') return false;
    if (filter === 'all') return true;
    if (filter === 'apply') return j.state === 'ready_to_apply';
    return j.state === filter;
  });

  const CHIPS: { key: StreamFilter; label: string }[] = [
    { key: 'all',      label: 'All'      },
    { key: 'ready',    label: 'Ready'    },
    { key: 'tailoring',label: 'Tailoring'},
    { key: 'apply',    label: 'Apply'    },
    { key: 'parked',   label: 'Parked'   },
  ];

  const emptyState = (
    <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: 13 }}>
      Nothing in this stage right now.
    </div>
  );

  return (
    <div>
      {/* Mobile header */}
      {isMobile && <div style={{ padding: '8px 0 14px' }}>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Stream</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>Every role · every stage</div>
      </div>}

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

      {/* ── Desktop table (md+) ── */}
      {!isMobile && <div>
        {filtered.length === 0 ? emptyState : (
          <div>
            {/* Table header */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 72px 210px 148px 110px',
                gap: '0 12px',
                padding: '0 14px 8px',
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: '0.07em',
                color: 'var(--text-muted)',
              }}
            >
              <span>ROLE</span>
              <span>MATCH</span>
              <span>PIPELINE STAGE</span>
              <span>STATUS</span>
              <span style={{ textAlign: 'right' }}>ACTION</span>
            </div>

            {/* Table rows */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 18 }}>
              {filtered.map((job) => {
                const ready = job.state === 'ready';
                const reviewable = job.state === 'ready' || job.state === 'parked';
                const m = STATUS_META[job.state] ?? STATUS_META.tailoring;
                return (
                  <div
                    key={job.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 72px 210px 148px 110px',
                      gap: '0 12px',
                      alignItems: 'center',
                      padding: '12px 14px',
                      borderRadius: 12,
                      background: ready ? 'color-mix(in srgb, var(--accent) 6%, var(--surface))' : 'var(--surface)',
                      border: `1px solid ${ready ? 'var(--accent-soft)' : 'var(--border)'}`,
                    }}
                  >
                    {/* ROLE */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {job.title}
                        </span>
                        {job.jobUrl && (
                          <a
                            href={job.jobUrl}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={`Open ${job.title} job posting`}
                            style={{ flexShrink: 0, color: 'var(--text-muted)', lineHeight: 1 }}
                          >
                            <HatchIcon name="externalLink" size={12} color="var(--text-muted)" />
                          </a>
                        )}
                      </div>
                      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                        {job.company} · {job.loc}
                        {job.rate && job.rate !== '—' ? <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}> · {job.rate}</span> : null}
                      </div>
                    </div>

                    {/* MATCH */}
                    <div><ScorePill score={job.score} /></div>

                    {/* PIPELINE STAGE */}
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <StageTrack stage={stageOf(job)} pct={Math.round(job.score * 100)} compact />
                    </div>

                    {/* STATUS */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600, color: m.color }}>
                      {m.dot && <Dot color={m.color} size={6} pulse />}
                      {m.label}
                    </div>

                    {/* ACTION */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      {ready ? (
                        <Btn
                          kind="success"
                          size="sm"
                          icon="check"
                          disabled={approvingId === job.id}
                          onClick={(e) => { e.stopPropagation(); onApprove?.(job.id, job.jobPostingId); }}
                        >
                          {approvingId === job.id ? 'Preparing…' : 'Approve'}
                        </Btn>
                      ) : reviewable ? (
                        <Btn kind="soft" size="sm" iconR="chevronR" onClick={() => onReview?.([job.id])}>
                          Review
                        </Btn>
                      ) : (
                        <Btn kind="soft" size="sm" disabled>
                          {job.state === 'tailoring' ? 'In progress' : 'Package ready'}
                        </Btn>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>}

      {/* ── Mobile cards ── */}
      {isMobile && <div style={{ display: 'flex', flexDirection: 'column', gap: 11, paddingBottom: 18 }}>
        {filtered.length === 0 ? emptyState : filtered.map((job) => {
          const ready = job.state === 'ready';
          const reviewable = job.state === 'ready' || job.state === 'parked';
          const m = STATUS_META[job.state] ?? STATUS_META.tailoring;
          return (
            <Card key={job.id} accent={ready} style={{ padding: 14 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text)' }}>{job.title}</span>
                      {job.jobUrl && (
                        <a
                          href={job.jobUrl}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open ${job.title} job posting`}
                        >
                          <HatchIcon name="externalLink" size={13} color="var(--text-muted)" />
                        </a>
                      )}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 3 }}>
                      {job.company} · {job.loc} · <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>{job.rate}</span>
                    </div>
                  </div>
                  <ScorePill score={job.score} />
                </div>
                <StageTrack stage={stageOf(job)} pct={Math.round(job.score * 100)} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: m.color, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  {m.dot && <Dot color={m.color} size={6} pulse />}{m.label}
                </span>
                {ready
                  ? <Btn kind="success" size="sm" icon="check" disabled={approvingId === job.id} onClick={() => onApprove?.(job.id, job.jobPostingId)}>{approvingId === job.id ? 'Preparing…' : 'Approve'}</Btn>
                  : reviewable
                    ? <Btn kind="soft" size="sm" iconR="chevronR" onClick={() => onReview?.([job.id])}>Review</Btn>
                    : <span style={{ fontSize: 11.5, color: 'var(--text-muted)', fontWeight: 600 }}>
                        {job.state === 'tailoring' ? 'Tailor is working' : 'Package ready'}
                      </span>
                }
              </div>
            </Card>
          );
        })}
      </div>}
    </div>
  );
}
