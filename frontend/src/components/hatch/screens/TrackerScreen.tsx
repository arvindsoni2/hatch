"use client";
import { Card } from '../Card';
import { Chip } from '../Chip';
import { Dot } from '../Dot';
import { ScorePill } from '../ScorePill';
import type { HatchJob } from './TodayScreen';

interface KanbanJob {
  id: string;
  title: string;
  company: string;
  loc: string;
  rate: string;
  score: number;
  when?: string;
}

interface TrackerScreenProps {
  jobs: HatchJob[];
  appliedJobs: KanbanJob[];
  interviewJobs: KanbanJob[];
}

interface ColDef {
  key: string;
  label: string;
  color: string;
  list: KanbanJob[];
}

function KanbanCol({ col }: { col: ColDef }) {
  return (
    <div
      data-testid={`col-${col.key}`}
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: 10,
        minWidth: 230,
        flex: 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 6px 10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <Dot color={col.color} size={7} />
          <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text)' }}>{col.label}</span>
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-muted)' }}>{col.list.length}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {col.list.length > 0 ? col.list.map((job) => (
          <div
            key={job.id}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 11,
              padding: 11,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{job.title}</span>
              <ScorePill score={job.score} />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{job.company} · {job.loc}</div>
            {job.when && (
              <div style={{ marginTop: 8 }}>
                <Chip color="var(--warning)" bg="var(--warning-soft)" icon="calendar">{job.when}</Chip>
              </div>
            )}
          </div>
        )) : (
          <div style={{ border: '1.5px dashed var(--border)', borderRadius: 11, padding: '20px 10px', textAlign: 'center', fontSize: 11.5, color: 'var(--text-muted)' }}>
            Nothing here yet
          </div>
        )}
      </div>
    </div>
  );
}

export function TrackerScreen({ jobs, appliedJobs, interviewJobs }: TrackerScreenProps) {
  const discovered = jobs.filter((j) => ['ready', 'tailoring', 'parked'].includes(j.state));

  const cols: ColDef[] = [
    { key: 'discovered', label: 'Discovered', color: 'var(--accent)',   list: discovered },
    { key: 'applied',    label: 'Applied',    color: 'var(--purple)',   list: appliedJobs },
    { key: 'interview',  label: 'Interview',  color: 'var(--warning)',  list: interviewJobs },
    { key: 'offered',    label: 'Offered',    color: 'var(--success)',  list: [] },
  ];

  return (
    <div>
      <div style={{ padding: '8px 0 14px' }}>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text)' }}>Tracker</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>Your pipeline, every stage</div>
      </div>
      {/* Single column list — responsive via CSS; mobile scrolls horizontally, desktop uses grid */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          overflowX: 'auto',
          paddingBottom: 18,
          alignItems: 'flex-start',
        }}
      >
        {cols.map((col) => <KanbanCol key={col.key} col={col} />)}
      </div>
    </div>
  );
}
