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
  status: 'ready' | 'progress' | 'generating';
  when?: string;
  companyResearch?: string;
  questions?: PrepQuestion[];
}

const STATUS_PILL: Record<PrepSession['status'], { label: string; color: string; soft: string }> = {
  ready:      { label: 'Prep ready',   color: 'var(--success)', soft: 'var(--success-soft)' },
  progress:   { label: 'In progress',  color: 'var(--accent)',  soft: 'var(--accent-soft)'  },
  generating: { label: 'Generating…',  color: 'var(--warning)', soft: 'var(--warning-soft)' },
};

interface PrepScreenProps {
  sessions: PrepSession[];
  openSessionId?: string;
  onNewSession?: () => void;
  onSelectSession?: (id: string) => void;
  onCalendar?: () => void;
  onPractice?: (id: string) => void;
  onDeleteSession?: (id: string) => void;
}

function DetailView({ session, onCalendar, onPractice }: { session: PrepSession; onCalendar?: () => void; onPractice?: () => void }) {
  const [openQ, setOpenQ] = useState<number | null>(null);
  const questions = session.questions ?? [];

  return (
    <div style={{ flex: 1, overflow: 'auto' }}>
      {/* Header */}
      <div style={{ padding: '0 0 16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <AgentBadge agent="coach" size={32} />
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>{session.title} · {session.company}</div>
            {session.when && <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{session.when} · prepped by Coach</div>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn kind="primary" size="sm" icon="mic" onClick={onPractice}>Practice</Btn>
          <Btn kind="soft" size="sm" icon="calendar" onClick={onCalendar}>Add to calendar</Btn>
        </div>
      </div>

      {/* Company research */}
      {session.companyResearch && (
        <Card style={{ padding: 14, marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 8 }}>COMPANY RESEARCH</div>
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
                      STAR ANSWER · from your story bank
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

export function PrepScreen({ sessions, openSessionId, onNewSession, onSelectSession, onCalendar, onPractice, onDeleteSession }: PrepScreenProps) {
  const openSession = sessions.find((s) => s.id === openSessionId);

  return (
    <div>
      {/* Page header */}
      <div style={{ padding: '8px 0 14px' }}>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Prep</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>AI mock-interview coaching by Coach</div>
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
            <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>SESSIONS</span>
            <Btn kind="soft" size="sm" icon="plus" onClick={onNewSession}>New</Btn>
          </div>

          {sessions.map((s) => {
            const p = STATUS_PILL[s.status];
            const active = s.id === openSessionId;
            return (
              <Card
                key={s.id}
                onClick={() => s.status === 'ready' && onSelectSession?.(s.id)}
                style={{ padding: 15, cursor: s.status === 'ready' ? 'pointer' : 'default', background: active ? 'var(--surface-2)' : 'var(--surface)' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <AgentBadge agent="coach" size={34} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text)' }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 1 }}>
                      {s.company}{s.when ? ` · ${s.when}` : ''}
                    </div>
                  </div>
                  <Chip color={p.color} bg={p.soft}>{p.label}</Chip>
                  {onDeleteSession && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
                      title="Delete session"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 6, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}
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
