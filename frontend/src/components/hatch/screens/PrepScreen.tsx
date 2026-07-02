"use client";
import { useState } from 'react';
import { AgentBadge } from '../AgentBadge';
import { Btn } from '../Btn';
import { Card } from '../Card';
import { Chip } from '../Chip';
import { HatchIcon } from '../HatchIcon';

export interface PrepQuestion {
  q: string;
  cat: 'Behavioural' | 'Technical' | 'Leadership';
  star?: string;
}

export interface PrepSession {
  id: string;
  title: string;
  company: string;
  status: 'ready' | 'progress' | 'generating' | 'stale' | 'failed';
  when?: string;
  createdAt?: string;
  startedAt?: string;
  companyResearch?: string;
  questions?: PrepQuestion[];
}

const STATUS_PILL: Record<PrepSession['status'], { label: string; color: string; soft: string }> = {
  ready:      { label: 'Prep ready',   color: 'var(--success)', soft: 'var(--success-soft)' },
  progress:   { label: 'In progress',  color: 'var(--accent)',  soft: 'var(--accent-soft)'  },
  generating: { label: 'Generating…',  color: 'var(--warning)', soft: 'var(--warning-soft)' },
  stale:      { label: 'Needs attention', color: 'var(--warning)', soft: 'var(--warning-soft)' },
  failed:     { label: 'Failed', color: 'var(--danger, #ef4444)', soft: 'rgba(239,68,68,0.14)' },
};

interface PrepScreenProps {
  sessions: PrepSession[];
  openSessionId?: string;
  onNewSession?: () => void;
  onSelectSession?: (id: string) => void;
  onCalendar?: () => void;
  onPractice?: (id: string) => void;
  onDeleteSession?: (id: string) => void;
  onRetrySession?: (id: string) => void;
  retryingIds?: Record<string, boolean>;
}

function timeAgo(value?: string): string | null {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return null;
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function DetailView({ session, onCalendar, onPractice }: { session: PrepSession; onCalendar?: () => void; onPractice?: () => void }) {
  const [openQ, setOpenQ] = useState<number | null>(null);
  const questions = session.questions ?? [];

  return (
    <div style={{ flex: 1, overflow: 'auto' }}>
      {/* Header */}
      <div className="hatch-page-header" style={{ padding: '0 0 16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <AgentBadge agent="coach" size={32} />
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>{session.title} · {session.company}</div>
            {session.when && <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{session.when} · prepped by Coach</div>}
          </div>
        </div>
        <div className="hatch-page-actions" style={{ display: 'flex', gap: 8 }}>
          <Btn kind="primary" size="sm" icon="mic" onClick={onPractice}>Start practice</Btn>
          <Btn kind="soft" size="sm" icon="calendar" onClick={onCalendar}>Add to calendar</Btn>
        </div>
      </div>

      {/* Company research */}
      {session.companyResearch && (
        <Card style={{ padding: 14, marginBottom: 16 }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Company research</h2>
          <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: 'var(--text-dim)' }}>{session.companyResearch}</p>
        </Card>
      )}

      {/* Questions */}
      <div style={{ marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>
          {questions.length} likely questions
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {questions.map((item, i) => {
          const isOpen = openQ === i;
          return (
            <Card key={i} style={{ padding: 0, overflow: 'hidden' }}>
              <button
                type="button"
                className="hatch-interactive"
                aria-expanded={isOpen}
                onClick={() => setOpenQ(isOpen ? null : i)}
                style={{ width: '100%', display: 'flex', alignItems: 'flex-start', gap: 10, padding: 13, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
              >
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', marginTop: 1 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', lineHeight: 1.4 }}>{item.q}</div>
                  <Chip color="var(--purple)" bg="var(--purple-soft)" style={{ marginTop: 7 }}>{item.cat}</Chip>
                </div>
                <HatchIcon
                  name="chevronR"
                  size={15}
                  color="var(--text-muted)"
                  style={{ transform: isOpen ? 'rotate(90deg)' : 'none', marginTop: 2 }}
                />
              </button>
              {isOpen && item.star && (
                <div style={{ padding: '0 13px 13px 39px' }}>
                  <div style={{ padding: 11, borderRadius: 10, background: 'var(--surface-2)', borderLeft: '2px solid var(--success)' }}>
                    <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.05em', color: 'var(--success)', marginBottom: 5 }}>
                      STAR answer · from your story bank
                    </div>
                    <p style={{ margin: 0, fontSize: 12, lineHeight: 1.55, color: 'var(--text-dim)' }}>{item.star}</p>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export function PrepScreen({ sessions, openSessionId, onNewSession, onSelectSession, onCalendar, onPractice, onDeleteSession, onRetrySession, retryingIds = {} }: PrepScreenProps) {
  const openSession = sessions.find((s) => s.id === openSessionId);

  return (
    <div>
      {/* Page header */}
      <div style={{ padding: '8px 0 14px' }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Interview Prep</h1>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>Research, likely questions, and practice for confirmed interviews</div>
      </div>

      {/* Unified layout: session list + optional detail pane.
          On mobile the detail replaces the list (when openSession is set).
          On desktop both panels are visible side-by-side via CSS. */}
      <div style={{ display: 'flex', gap: 24, minHeight: '60vh', alignItems: 'flex-start' }}>
        {/* Session list — hidden on mobile when a session is open; always visible on md+ */}
        <div
          className={openSession ? 'hidden md:flex md:flex-col md:gap-2 md:w-80 md:flex-shrink-0' : 'flex flex-col gap-2 w-full flex-shrink-0'}
        >
          {/* Sessions sub-header with + New button */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>Sessions</h2>
            <Btn kind="soft" size="sm" icon="plus" onClick={onNewSession}>New session</Btn>
          </div>

          {sessions.length === 0 && (
            <Card style={{ padding: 20, textAlign: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>No interview prep sessions yet</div>
              <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.5, color: 'var(--text-muted)' }}>
                Add a session when an interview is confirmed.
              </div>
            </Card>
          )}

          {sessions.map((s) => {
            const p = STATUS_PILL[s.status];
            const active = s.id === openSessionId;
            const canOpen = s.status === 'ready';
            const canRetry = s.status === 'stale' || s.status === 'failed';
            const age = timeAgo(s.startedAt ?? s.createdAt);
            return (
              <Card
                key={s.id}
                style={{ padding: 10, background: active ? 'var(--surface-2)' : 'var(--surface)' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button
                    type="button"
                    className={canOpen ? 'hatch-interactive' : undefined}
                    disabled={!canOpen}
                    aria-current={active ? 'true' : undefined}
                    onClick={() => onSelectSession?.(s.id)}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0, padding: 5, textAlign: 'left', border: 0, background: 'transparent', cursor: canOpen ? 'pointer' : 'default' }}
                  >
                    <AgentBadge agent="coach" size={34} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text)' }}>{s.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 1 }}>
                        {s.company}{s.when ? ` · ${s.when}` : age ? ` · ${age}` : ''}
                      </div>
                    </div>
                    <Chip color={p.color} bg={p.soft}>{p.label}</Chip>
                  </button>
                  {canRetry && onRetrySession && (
                    <button
                      type="button"
                      className="hatch-interactive"
                      onClick={() => onRetrySession(s.id)}
                      disabled={retryingIds[s.id]}
                      aria-label={`Retry prep for ${s.title}`}
                      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', cursor: retryingIds[s.id] ? 'wait' : 'pointer', padding: '6px 8px', borderRadius: 7, color: 'var(--text)', fontSize: 11, fontWeight: 700 }}
                    >
                      {retryingIds[s.id] ? 'Retrying' : 'Retry'}
                    </button>
                  )}
                  {onDeleteSession && (
                    <button
                      type="button"
                      className="hatch-interactive"
                      onClick={() => onDeleteSession(s.id)}
                      aria-label={`Delete ${s.title} session`}
                      style={{ width: 44, background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 6, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--danger, #ef4444)')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                    >
                      <HatchIcon name="trash" size={15} color="currentColor" />
                    </button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>

        {/* Detail pane */}
        {openSession && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <DetailView session={openSession} onCalendar={onCalendar} onPractice={openSession ? () => onPractice?.(openSession.id) : undefined} />
          </div>
        )}
      </div>
    </div>
  );
}
