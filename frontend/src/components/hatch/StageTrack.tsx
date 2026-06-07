"use client";
import { AGENT_DEFS, PIPELINE } from './agents';
import { HatchIcon } from './HatchIcon';

interface StageTrackProps {
  stage?: number;       // index of the current stage (0=scout, 1=scorer, 2=tailor, 3=coach)
  pct?: number;         // score % to show on Scorer node when stage=1
  compact?: boolean;    // smaller nodes, no labels by default
  labels?: boolean;     // override label visibility
}

export function StageTrack({ stage = 0, pct, compact = false, labels }: StageTrackProps) {
  const showLabels = labels ?? !compact;
  const r = compact ? 9 : 11;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {PIPELINE.map((k, i) => {
          const a = AGENT_DEFS[k];
          const reached = i <= stage;
          const done = i < stage;
          const here = i === stage;

          return (
            <div key={k} style={{ display: 'flex', alignItems: 'center', flex: i < PIPELINE.length - 1 ? 1 : undefined }}>
              <div
                data-stage-node={k}
                style={{
                  width: r * 2,
                  height: r * 2,
                  borderRadius: 999,
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: reached ? a.soft : 'var(--surface-2)',
                  boxShadow: here ? `0 0 0 3px ${a.soft}` : 'none',
                  border: reached ? `1.5px solid ${a.color}` : '1.5px solid var(--border)',
                }}
              >
                <HatchIcon
                  name={done ? 'check' : a.icon}
                  size={compact ? 10 : 12}
                  color={reached ? a.color : 'var(--text-muted)'}
                  strokeWidth={2.4}
                />
              </div>
              {i < PIPELINE.length - 1 && (
                <div
                  style={{
                    flex: 1,
                    height: 2,
                    background: i < stage ? AGENT_DEFS[PIPELINE[i + 1]].color : 'var(--border)',
                    opacity: i < stage ? 0.5 : 1,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      {showLabels && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, fontWeight: 600, letterSpacing: '0.02em' }}>
          {PIPELINE.map((k, i) => (
            <span key={k} style={{ color: i <= stage ? AGENT_DEFS[k].color : 'var(--text-muted)', width: r * 2, textAlign: 'center' }}>
              {k === 'scorer' && pct != null && i === stage ? `${pct}%` : AGENT_DEFS[k].name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
