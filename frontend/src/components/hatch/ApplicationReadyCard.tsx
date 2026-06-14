"use client";
import { Btn } from './Btn';
import { Card } from './Card';
import { Chip } from './Chip';
import { HatchIcon } from './HatchIcon';
import type { HatchJob } from './screens/TodayScreen';
import type { ApplicationPackage } from '@/lib/api';

interface ApplicationReadyCardProps {
  job: HatchJob;
  pkg: ApplicationPackage;
  onMarkApplied: (id: string) => void;
  onRevert: (id: string) => void;
  onRetry?: (job: HatchJob) => void;
}

export function ApplicationReadyCard({ job, pkg, onMarkApplied, onRevert, onRetry }: ApplicationReadyCardProps) {
  const hasScreeningAnswers = Object.keys(pkg.screening_answers ?? {}).length > 0;
  const hasPasteMap = Object.keys(pkg.paste_map ?? {}).length > 0;
  const hasCompletePackage = Boolean(pkg.cv_document_id && pkg.cl_document_id);

  return (
    <Card accent style={{ padding: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{job.title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {job.company} · {job.loc} · <span style={{ fontWeight: 600, color: 'var(--text-dim)' }}>{job.rate}</span>
          </div>
        </div>
        <Chip color={hasCompletePackage ? "var(--accent)" : "var(--warning)"} bg={hasCompletePackage ? "var(--accent-soft)" : "var(--warning-soft)"}>
          {hasCompletePackage ? "Ready to apply" : "Documents incomplete"}
        </Chip>
      </div>

      {/* Screening answers */}
      {hasScreeningAnswers && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 7 }}>
            SCREENING ANSWERS — copy &amp; paste
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(pkg.screening_answers).map(([q, a]) => (
              <div key={q} style={{ padding: '8px 10px', borderRadius: 9, background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginBottom: 2 }}>{q.replace(/_/g, ' ')}</div>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>{a}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Paste map */}
      {hasPasteMap && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 7 }}>
            FORM FIELDS — what to paste where
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {Object.entries(pkg.paste_map).map(([field, value]) => (
              <div key={field} style={{ display: 'flex', gap: 8, fontSize: 12, alignItems: 'baseline' }}>
                <span style={{ color: 'var(--text-muted)', minWidth: 120, flexShrink: 0 }}>{field}</span>
                <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reassurance */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', margin: '12px 0', padding: 10, borderRadius: 10, background: 'var(--accent-soft)' }}>
        <HatchIcon name="arrowR" size={14} color="var(--accent)" style={{ marginTop: 1 }} />
        <span style={{ fontSize: 11.5, color: 'var(--text-dim)', lineHeight: 1.5 }}>
          {hasCompletePackage
            ? "Hatch prepared everything. Review, then submit on the company's site — you're always in control of the final click."
            : "Your application documents were not fully generated. Retry preparation before applying."}
        </span>
      </div>

      {/* Document downloads */}
      {(pkg.cv_document_id || pkg.cl_document_id) && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {pkg.cv_document_id && (
            <Btn kind="soft" size="sm" icon="arrowR"
              onClick={() => window.open(`/api/tailor/document/${pkg.cv_document_id}/download`, '_blank')}>
              Download CV
            </Btn>
          )}
          {pkg.cl_document_id && (
            <Btn kind="soft" size="sm" icon="arrowR"
              onClick={() => window.open(`/api/tailor/document/${pkg.cl_document_id}/download`, '_blank')}>
              Download Cover Letter
            </Btn>
          )}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        {pkg.job_url && (
          <Btn kind="primary" full iconR="arrowR" onClick={() => window.open(pkg.job_url, '_blank')}>
            Open application
          </Btn>
        )}
        {hasCompletePackage ? (
          <Btn kind="success" full icon="check" onClick={() => onMarkApplied(job.id)}>
            Mark as applied
          </Btn>
        ) : onRetry ? (
          <Btn kind="success" full icon="arrowR" onClick={() => onRetry(job)}>
            Retry documents
          </Btn>
        ) : null}
      </div>
      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <button
          onClick={() => onRevert(job.id)}
          style={{ fontSize: 11.5, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
        >
          Undo
        </button>
      </div>
    </Card>
  );
}
