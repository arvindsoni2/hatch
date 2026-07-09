"use client";
import { useState } from 'react';
import { Btn } from './Btn';
import { Card } from './Card';
import { Chip } from './Chip';
import { HatchIcon } from './HatchIcon';
import type { HatchJob } from './screens/TodayScreen';
import {
  DocumentQualityAcknowledgementRequiredError,
  downloadDocumentAsset,
  downloadDocument,
  exportPackagePdf,
  type ApplicationPackage,
  type GeneratedDocumentAsset,
} from '@/lib/api';

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
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null);
  const [pdfNotice, setPdfNotice] = useState<string | null>(null);
  const [pdfAssets, setPdfAssets] = useState<Partial<Record<'cv' | 'cover_letter', GeneratedDocumentAsset>>>({});
  const [acknowledgementDocumentId, setAcknowledgementDocumentId] = useState<string | null>(null);

  const handleDownload = async (documentId: string, acknowledgeQualityWarnings = false) => {
    try {
      setDownloadNotice(null);
      setAcknowledgementDocumentId(null);
      await downloadDocument(documentId, { acknowledgeQualityWarnings });
    } catch (error) {
      if (error instanceof DocumentQualityAcknowledgementRequiredError) {
        setDownloadNotice(error.message);
        setAcknowledgementDocumentId(documentId);
        return;
      }
      setDownloadNotice(error instanceof Error ? error.message : 'Could not download this document.');
    }
  };

  const pdfFilename = (kind: 'cv' | 'cover_letter') => {
    const title = job.title.replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '') || 'application';
    return `${title}-${kind === 'cv' ? 'cv' : 'cover-letter'}.pdf`;
  };

  const ensurePdfAsset = async (kind: 'cv' | 'cover_letter') => {
    const existing = pdfAssets[kind];
    if (existing) return existing;
    const asset = await exportPackagePdf(job.id, kind);
    setPdfAssets((current) => ({ ...current, [kind]: asset }));
    return asset;
  };

  const handlePdfPreview = async (kind: 'cv' | 'cover_letter') => {
    try {
      setPdfNotice(null);
      const asset = await ensurePdfAsset(kind);
      window.open(`/api/documents/assets/${asset.id}`, '_blank', 'noopener,noreferrer');
    } catch (error) {
      setPdfNotice(error instanceof Error ? error.message : 'Could not preview this PDF.');
    }
  };

  const handlePdfDownload = async (kind: 'cv' | 'cover_letter') => {
    try {
      setPdfNotice(null);
      const asset = await ensurePdfAsset(kind);
      await downloadDocumentAsset(asset.id, pdfFilename(kind));
    } catch (error) {
      setPdfNotice(error instanceof Error ? error.message : 'Could not download this PDF.');
    }
  };

  const renderDocumentActions = (
    kind: 'cv' | 'cover_letter',
    documentId: string,
    label: string,
  ) => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
      <Btn kind="soft" size="sm" icon="arrowR" onClick={() => void handleDownload(documentId)}>
        Download {label} DOCX
      </Btn>
      <Btn kind="soft" size="sm" icon="arrowR" onClick={() => void handlePdfPreview(kind)}>
        Preview {label} PDF
      </Btn>
      <Btn kind="soft" size="sm" icon="arrowR" onClick={() => void handlePdfDownload(kind)}>
        Download {label} PDF
      </Btn>
    </div>
  );

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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {pkg.cv_document_id && renderDocumentActions('cv', pkg.cv_document_id, 'CV')}
          {pkg.cl_document_id && renderDocumentActions('cover_letter', pkg.cl_document_id, 'Cover Letter')}
        </div>
      )}
      {pdfNotice && (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--danger)', margin: '-4px 0 12px' }}>
          {pdfNotice}
        </div>
      )}
      {downloadNotice && (
        <div role="status" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', margin: '-4px 0 12px' }}>
          <span style={{ fontSize: 11.5, color: 'var(--danger)' }}>{downloadNotice}</span>
          {acknowledgementDocumentId && (
            <Btn kind="soft" size="sm" icon="arrowR" onClick={() => void handleDownload(acknowledgementDocumentId, true)}>
              Download anyway
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
