"use client";

import { GeneratedDocument, downloadDocument } from "@/lib/api";
import { Download, FileText, FileCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

interface DocumentHistoryProps {
  documents: GeneratedDocument[];
}

function atsColor(score: number): string {
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--warning)";
  return "var(--danger)";
}

function statusStyle(status: string): { background: string; color: string } {
  switch (status) {
    case "generated": return { background: "var(--success-soft)", color: "var(--success)" };
    case "generating": return { background: "var(--accent-soft)", color: "var(--accent)" };
    case "failed":    return { background: "var(--danger-soft)", color: "var(--danger)" };
    default:          return { background: "var(--surface-2)", color: "var(--text-muted)" };
  }
}

export function DocumentHistory({ documents }: DocumentHistoryProps) {
  if (documents.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>No documents generated yet.</p>
      </div>
    );
  }

  const grouped = documents.reduce<Record<string, GeneratedDocument[]>>((acc, doc) => {
    const key = doc.document_type;
    acc[key] = acc[key] ?? [];
    acc[key].push(doc);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([docType, docs]) => (
        <div key={docType} className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text)" }}>
            {docType === "cv" ? (
              <FileText className="h-4 w-4" style={{ color: "var(--accent)" }} />
            ) : (
              <FileCheck className="h-4 w-4" style={{ color: "var(--success)" }} />
            )}
            {docType === "cv" ? "CV" : "Cover Letter"} Versions
          </h3>

          <div className="space-y-2">
            {docs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between rounded-lg px-3 py-2"
                style={{ background: "var(--surface-2)" }}
              >
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>v{doc.version}</span>
                  {doc.variant_label && (
                    <span className="rounded px-1.5 py-0.5 text-xs" style={{ background: "var(--surface-3)", color: "var(--text-dim)" }}>
                      Variant {doc.variant_label}
                    </span>
                  )}
                  <span
                    className="rounded-full px-2 py-0.5 text-xs font-medium"
                    style={statusStyle(doc.status)}
                  >
                    {doc.status}
                  </span>
                  {doc.ats_score != null && (
                    <span className="text-xs font-semibold" style={{ color: atsColor(doc.ats_score) }}>
                      ATS: {doc.ats_score}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {new Date(doc.created_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    style={{ color: "var(--text-dim)" }}
                    onClick={() => downloadDocument(doc.id)}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
