"use client";
import { AgentBadge } from './AgentBadge';
import { Btn } from './Btn';
import { Card } from './Card';
import { HatchIcon } from './HatchIcon';
import { ScorePill } from './ScorePill';
import type { HatchJob } from './screens/TodayScreen';
import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogTitle,
  ResponsiveDialogContent,
} from '@/components/ui/dialog';

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
  const job = queue[idx];
  if (!job) return null;

  const verdict = job.score >= 0.9 ? 'Excellent match' : 'Strong match for you';

  return (
    <Dialog onOpenChange={(open) => { if (!open && !isLoading) onClose(); }} open>
      <ResponsiveDialogContent
        className="p-0 sm:max-w-2xl"
        hideClose
        preventClose={isLoading}
      >
        <DialogTitle className="sr-only">Review Application</DialogTitle>
        <DialogDescription className="sr-only">
          Review match evidence before generating an application pack.
        </DialogDescription>
        {/* Top bar */}
        <div style={{ height: 56, flexShrink: 0 }} className="md:hidden" />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px 12px' }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)', border: '1px solid var(--border)' }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
            Application {idx + 1} of {queue.length}
          </span>
          <DialogClose asChild>
            <button
              type="button"
              className="hatch-interactive"
              aria-label="Close review"
              disabled={isLoading}
              style={{ width: 44, height: 44, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)', border: '1px solid var(--border)', cursor: 'pointer' }}
            >
              <HatchIcon name="x" size={16} color="var(--text-dim)" />
            </button>
          </DialogClose>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '0 18px' }}>
          <h2 id="review-title" style={{ margin: '4px 0 0', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>{job.title}</h2>
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

          {/* Generation decision */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '18px 0 10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AgentBadge agent="tailor" size={26} />
              <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>Generate with Tailor</span>
            </div>
          </div>

          {/* Documents do not exist until the user confirms generation. */}
          <div style={{ background: 'var(--surface-2)', borderRadius: 12, padding: 16, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ width: 34, height: 34, borderRadius: 9, background: 'var(--accent-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <HatchIcon name="fileText" size={18} color="var(--accent)" />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>No documents generated yet</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Review the match evidence above. If you continue, Tailor will prepare a CV and cover letter for this role.
              </div>
            </div>
          </div>

          {/* Info strip */}
          <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', margin: '16px 0 18px', padding: 12, borderRadius: 12, background: 'var(--accent-soft)' }}>
            <HatchIcon name="arrowR" size={16} color="var(--accent)" style={{ marginTop: 1 }} />
            <span style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
              Generating a CV pack does not submit an application. You will review the completed documents before applying on the company&apos;s site.
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
          <Btn kind="ghost" icon="x" disabled={isLoading} onClick={() => onAction('reject')}>Dismiss role</Btn>
          <Btn kind="primary" full iconR={isLoading ? undefined : "arrowR"} disabled={isLoading} onClick={() => onAction('approve')}>
            {isLoading ? 'Preparing CV pack…' : 'Generate CV pack'}
          </Btn>
        </div>
        <div style={{ height: 30, flexShrink: 0 }} className="md:hidden" />
      </ResponsiveDialogContent>
    </Dialog>
  );
}
