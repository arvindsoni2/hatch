"use client";
import React, { useEffect, useState } from 'react';
import { AgentBadge } from '../AgentBadge';
import { Btn } from '../Btn';
import { Card } from '../Card';
import { Chip } from '../Chip';
import { Dot } from '../Dot';
import { HatchIcon } from '../HatchIcon';
import { ScorePill } from '../ScorePill';
import { UserAvatar } from '../UserAvatar';
import { AGENT_DEFS, PIPELINE } from '../agents';
import { TimeGreeting } from '@/components/TimeGreeting';

export interface HatchJob {
  id: string;
  jobPostingId?: string;  // JobPosting UUID — used for the approve API call
  title: string;
  company: string;
  loc: string;
  rate: string;
  score: number;
  ats?: number;
  dims?: { Skills: number; Experience: number; Rate: number; Location: number };
  state: 'ready' | 'ready_to_apply' | 'tailoring' | 'tailoring_failed' | 'parked' | 'applied' | 'rejected' | 'interview';
  jobUrl?: string;
  failureReason?: string;
  when?: string;
}

interface FunnelCounts {
  scout: number;
  scorer: number;
  tailor: number;
  coach: number;
}

interface TransitCounts {
  scout_to_scorer: number;
  scorer_to_tailor: number;
  tailor_to_coach: number;
}

interface UpcomingInterview {
  scheduledAt: string;
  title: string;
  company: string;
  daysUntil: number;
}

interface TodayScreenProps {
  jobs: HatchJob[];
  funnel: FunnelCounts;
  transit?: TransitCounts;
  profileName: string;
  followUpCount?: number;
  upcomingInterview?: UpcomingInterview | null;
  onReview?: (ids: string[]) => void;
  onMarkApplied?: (id: string) => void;
  onRevert?: (id: string) => void;
  onOpenPrep?: () => void;
}

const OUTPUT_LABELS: Record<string, string> = {
  scout: 'Jobs stored',
  scorer: 'Jobs scored',
  tailor: 'Packages ready',
  coach: 'Sessions ready',
};

function FunnelStep({ agent, count }: { agent: string; count: number }) {
  const a = AGENT_DEFS[agent as keyof typeof AGENT_DEFS];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, flex: 1 }}>
      <AgentBadge agent={agent as never} size={34} />
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)', lineHeight: 1 }}>{count}</div>
      <div style={{ fontSize: 10, fontWeight: 600, color: a.color }}>{a.name}</div>
      <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textAlign: 'center' }}>{OUTPUT_LABELS[agent]}</div>
    </div>
  );
}

function FunnelArrow({ count }: { count: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, paddingBottom: 28, flexShrink: 0 }}>
      {count > 0 && (
        <span style={{ fontSize: 9.5, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', lineHeight: 1 }}>
          {count}
        </span>
      )}
      <HatchIcon name="arrowR" size={13} color="var(--text-dim)" strokeWidth={2} />
    </div>
  );
}

export function TodayScreen({ jobs, funnel, transit, profileName, followUpCount = 2, upcomingInterview, onReview, onMarkApplied, onRevert, onOpenPrep }: TodayScreenProps) {
  const ready = jobs.filter((j) => j.state === 'ready');
  const readyToApply = jobs.filter((j) => j.state === 'ready_to_apply');
  const initials = profileName.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  const [todayLabel, setTodayLabel] = useState('');

  useEffect(() => {
    setTodayLabel(new Date().toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    }));
  }, []);

  return (
    <div>
      {/* Mobile header */}
      <div
        className="md:hidden flex items-start justify-between"
        style={{ padding: '8px 0 14px' }}
      >
        <div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Today</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>Your application workspace at a glance</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <HatchIcon name="bell" size={20} color="var(--text-dim)" />
            <span style={{ position: 'absolute', top: -2, right: -2, width: 7, height: 7, borderRadius: 999, background: 'var(--danger)', border: '1.5px solid var(--bg)' }} />
          </div>
          <UserAvatar size={32} initials={initials} />
        </div>
      </div>

      {/* Mobile date subtitle */}
      <div className="md:hidden" style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: -8, marginBottom: 10 }}>
        {todayLabel}
      </div>

      {/* Desktop greeting */}
      <div className="hidden md:block" style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text)' }}>
          <TimeGreeting name={profileName} />
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--text-muted)', marginTop: 4 }}>
          {todayLabel ? `${todayLabel} — ` : ''}your application workspace at a glance
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Briefing card */}
        <Card style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <Dot color="var(--success)" size={8} pulse />
              <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>Agent output</span>
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>all-time totals</span>
          </div>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.55, color: 'var(--text-dim)' }}>
            <strong style={{ color: 'var(--text)' }}>{funnel.scout} roles</strong> in your workspace ·{' '}
            <strong style={{ color: 'var(--success)' }}>{ready.length} packages</strong> currently need review.
          </p>
          {/* Mini funnel */}
          {(() => {
            const transitArr = [
              transit?.scout_to_scorer ?? 0,
              transit?.scorer_to_tailor ?? 0,
              transit?.tailor_to_coach ?? 0,
            ];
            return (
              <div style={{ display: 'flex', alignItems: 'center', marginTop: 16, padding: '4px 2px 0' }}>
                {PIPELINE.map((k, i) => (
                  <React.Fragment key={k}>
                    <FunnelStep agent={k} count={funnel[k as keyof FunnelCounts]} />
                    {i < PIPELINE.length - 1 && <FunnelArrow count={transitArr[i]} />}
                  </React.Fragment>
                ))}
              </div>
            );
          })()}
        </Card>

        {/* Needs you header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', whiteSpace: 'nowrap' }}>Needs you</span>
          <Chip color="var(--accent)" bg="var(--accent-soft)">{ready.length + (followUpCount > 0 ? 1 : 0)}</Chip>
        </div>

        {/* Approve card */}
        {ready.length > 0 ? (
          <Card accent style={{ padding: 15 }}>
            <div style={{ display: 'flex', gap: 11, marginBottom: 12 }}>
              <AgentBadge agent="tailor" size={34} ring />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
                  {ready.length} application{ready.length !== 1 ? 's' : ''} ready to send
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 1 }}>CV + cover letter drafted for each</div>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 13 }}>
              {ready.map((job) => (
                <button
                  key={job.id}
                  onClick={() => onReview?.([job.id])}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 9,
                    padding: '7px 9px', borderRadius: 9,
                    background: 'var(--surface-2)', border: 'none',
                    cursor: 'pointer', textAlign: 'left',
                  }}
                >
                  <ScorePill score={job.score} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {job.title}
                    </div>
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>{job.company}</div>
                  </div>
                  {job.ats != null && (
                    <Chip color="var(--success)" bg="var(--success-soft)" icon="check">CV ATS {job.ats}%</Chip>
                  )}
                </button>
              ))}
            </div>
            <Btn kind="primary" full iconR="arrowR" onClick={() => onReview?.(ready.map((j) => j.id))}>
              Review &amp; approve
            </Btn>
          </Card>
        ) : (
          <Card style={{ padding: 20, textAlign: 'center' }}>
            <div style={{ width: 38, height: 38, borderRadius: 999, margin: '0 auto 10px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--success-soft)' }}>
              <HatchIcon name="checkCircle" size={20} color="var(--success)" />
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>Approval queue clear</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Everything you approved is on its way.</div>
          </Card>
        )}

        {/* Finish applying section */}
        {readyToApply.length > 0 && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Finish applying</span>
              <Chip color="var(--warning)" bg="var(--warning-soft)">{readyToApply.length}</Chip>
            </div>
            {readyToApply.map((job) => (
              <Card key={job.id} style={{ padding: '12px 15px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{job.title}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 1 }}>{job.company} · {job.loc}</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5 }}>
                    <ScorePill score={job.score} />
                    {job.ats != null && (
                      <Chip color="var(--success)" bg="var(--success-soft)" icon="check" style={{ fontSize: 10.5, padding: '2px 6px' }}>
                        CV ATS {job.ats}%
                      </Chip>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {job.jobUrl && (
                    <Btn kind="soft" size="sm" iconR="arrowR" onClick={() => window.open(job.jobUrl, '_blank')}>
                      Open application
                    </Btn>
                  )}
                  <Btn kind="success" size="sm" icon="check" onClick={() => onMarkApplied?.(job.id)}>
                    Mark as applied
                  </Btn>
                </div>
              </Card>
            ))}
          </>
        )}

        {/* Interview prep card — only shown when a real interview is scheduled */}
        {upcomingInterview && (
          <div onClick={onOpenPrep} style={{ cursor: 'pointer' }}>
            <Card style={{ padding: 15 }}>
              <div style={{ display: 'flex', gap: 11 }}>
                <AgentBadge agent="coach" size={34} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
                      Interview {new Date(upcomingInterview.scheduledAt).toLocaleDateString('en-GB', { weekday: 'long', hour: 'numeric', minute: '2-digit' })}
                    </span>
                    {upcomingInterview.daysUntil <= 7 && (
                      <Chip color="var(--warning)" bg="var(--warning-soft)">
                        {upcomingInterview.daysUntil === 0 ? 'today' : upcomingInterview.daysUntil === 1 ? 'tomorrow' : `in ${upcomingInterview.daysUntil} days`}
                      </Chip>
                    )}
                  </div>
                  {(upcomingInterview.title || upcomingInterview.company) && (
                    <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 3 }}>
                      {upcomingInterview.title}{upcomingInterview.company ? ` · ${upcomingInterview.company}` : ''}
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 1 }}>Coach prepped questions + STAR answers</div>
                  <div style={{ marginTop: 11 }}><Btn kind="soft" size="sm" iconR="arrowR">Review prep</Btn></div>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* Follow-ups */}
        {followUpCount > 0 && (
          <Card style={{ padding: '13px 15px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--danger-soft)' }}>
                <HatchIcon name="clock" size={17} color="var(--danger)" />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{followUpCount} follow-up{followUpCount !== 1 ? 's' : ''} overdue</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 1 }}>Sent 12 &amp; 14 days ago — no reply yet</div>
              </div>
              <Btn kind="soft" size="sm" icon="send">Nudge {followUpCount > 1 ? 'both' : 'them'}</Btn>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
