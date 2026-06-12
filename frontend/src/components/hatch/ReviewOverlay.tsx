"use client";
import { useState } from 'react';
import { AgentBadge } from './AgentBadge';
import { Btn } from './Btn';
import { Card } from './Card';
import { Chip } from './Chip';
import { HatchIcon } from './HatchIcon';
import { ScorePill } from './ScorePill';
import type { HatchJob } from './screens/TodayScreen';

interface DimBarProps {
  label: string;
  val: number;
}

function DimBar({ label, val }: DimBarProps) {
  const color = val >= 0.85 ? 'var(--success)' : val >= 0.7 ? 'var(--accent)' : 'var(--warning)';
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
          {Math.round(val * 100)}
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 999, background: 'var(--surface-2)', overflow: 'hidden' }}>
        <div style={{ width: `${val * 100}%`, height: '100%', background: color }} />
      </div>
    </div>
  );
}

const DEFAULT_DIMS: Record<string, number> = { Skills: 0.80, Experience: 0.75, Rate: 0.80, Location: 0.75 };

interface ReviewOverlayProps {
  queue: HatchJob[];
  idx: number;
  onAction: (action: 'approve' | 'reject') => void;
  onClose: () => void;
  isLoading?: boolean;
  loadingMessage?: string;
}

export function ReviewOverlay({ queue, idx, onAction, onClose, isLoading = false, loadingMessage }: ReviewOverlayProps) {
  const [tab, setTab] = useState<'cv' | 'cl'>('cv');
  const job = queue[idx];
  if (!job) return null;

  const verdict = job.score >= 0.9 ? 'Excellent match' : 'Strong match for you';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 70,
        background: 'var(--bg)',
        color: 'var(--text)',
        display: 'flex',
        flexDirection: 'column',
        animation: 'hatchOverlayRise .2s ease-out',
        // Desktop: center as modal
      }}
      className="md:flex md:items-start md:justify-center"
    >
      {/* Desktop backdrop blur (md+) */}
      <div
        className="hidden md:block fixed inset-0 -z-10"
        style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
      />

      {/* Modal container */}
      <div
        className="md:relative md:rounded-2xl md:overflow-hidden md:shadow-2xl md:mt-12"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '100%',
          // Desktop max width
        }}
      >
        {/* Top bar */}
        <div style={{ height: 56, flexShrink: 0 }} className="md:hidden" />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px 12px' }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)', border: '1px solid var(--border)' }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
            Application {idx + 1} of {queue.length}
          </span>
          <button
            aria-label="Close review"
            onClick={onClose}
            style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)', border: '1px solid var(--border)', cursor: 'pointer' }}
          >
            <HatchIcon name="x" size={16} color="var(--text-dim)" />
          </button>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '0 18px' }}>
          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginTop: 4 }}>{job.title}</div>
          <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 4 }}>
            {job.company} · {job.loc} · <span style={{ color: 'var(--text)', fontWeight: 600 }}>{job.rate}</span>
          </div>

          {/* Score card */}
          <Card style={{ padding: 15, marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 14 }}>
              <ScorePill score={job.score} size="lg" />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text)' }}>{verdict}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Scored by Scorer across 4 dimensions</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              {Object.entries(job.dims ?? DEFAULT_DIMS).map(([k, v]) => <DimBar key={k} label={k} val={v} />)}
            </div>
          </Card>

          {/* Tailored docs header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '18px 0 10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AgentBadge agent="tailor" size={26} />
              <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>Tailored by Tailor</span>
            </div>
            {job.ats && <Chip color="var(--success)" bg="var(--success-soft)" icon="checkCircle">ATS {job.ats}%</Chip>}
          </div>

          {/* CV / CL tab toggle */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            {([['cv', 'CV'], ['cl', 'Cover letter']] as const).map(([k, l]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                style={{
                  flex: 1, padding: 8, borderRadius: 9, cursor: 'pointer',
                  fontSize: 12.5, fontWeight: tab === k ? 700 : 600,
                  background: tab === k ? 'var(--accent-soft)' : 'var(--surface)',
                  color: tab === k ? 'var(--accent)' : 'var(--text-dim)',
                  border: `1px solid ${tab === k ? 'transparent' : 'var(--border)'}`,
                }}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Document drafted confirmation */}
          <div style={{ background: 'var(--surface-2)', borderRadius: 12, padding: 16, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ width: 34, height: 34, borderRadius: 9, background: 'var(--success-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <HatchIcon name="checkCircle" size={18} color="var(--success)" />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>
                {tab === 'cv' ? 'CV drafted and ready' : 'Cover letter drafted and ready'}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                {tab === 'cv'
                  ? 'Tailored to this job description and optimised for ATS keyword matching.'
                  : 'Personalised to your experience and written specifically for this role.'}
              </div>
            </div>
          </div>

          {/* Info strip */}
          <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', margin: '16px 0 18px', padding: 12, borderRadius: 12, background: 'var(--accent-soft)' }}>
            <HatchIcon name="arrowR" size={16} color="var(--accent)" style={{ marginTop: 1 }} />
            <span style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
              Approve and Hatch will prepare your application package. You&apos;ll submit on the company&apos;s site — you&apos;re always in control of the final click.
            </span>
          </div>
        </div>

        {/* Sticky action bar */}
        {isLoading && loadingMessage && (
          <div style={{
            padding: '8px 18px',
            borderTop: '1px solid var(--border)',
            background: 'var(--bg-elevated)',
            fontSize: 13,
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.5s ease-in-out infinite' }} />
            {loadingMessage}
          </div>
        )}
        <div style={{
          flexShrink: 0,
          display: 'flex',
          gap: 10,
          padding: '12px 18px',
          borderTop: isLoading && loadingMessage ? 'none' : '1px solid var(--border)',
          background: 'var(--bg-elevated)',
        }}>
          <Btn kind="ghost" icon="x" disabled={isLoading} onClick={() => onAction('reject')}>Reject</Btn>
          <Btn kind="primary" full iconR={isLoading ? undefined : "arrowR"} disabled={isLoading} onClick={() => onAction('approve')}>
            {isLoading ? 'Preparing…' : 'Approve & prepare'}
          </Btn>
        </div>
        <div style={{ height: 30, flexShrink: 0 }} className="md:hidden" />
      </div>
    </div>
  );
}
