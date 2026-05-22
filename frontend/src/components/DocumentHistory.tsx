"use client";

import { GeneratedDocument, downloadDocument } from "@/lib/api";
import { Download, FileText, FileCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

interface DocumentHistoryProps {
  documents: GeneratedDocument[];
}

const STATUS_COLORS: Record<string, string> = {
  generated: "bg-emerald-900/40 text-emerald-300",
  generating: "bg-blue-900/40 text-blue-300",
  failed: "bg-red-900/40 text-red-300",
};

export function DocumentHistory({ documents }: DocumentHistoryProps) {
  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-6 text-center">
        <p className="text-sm text-slate-500">No documents generated yet.</p>
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
        <div key={docType} className="rounded-xl border border-slate-700 bg-slate-800 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
            {docType === "cv" ? (
              <FileText className="h-4 w-4 text-indigo-400" />
            ) : (
              <FileCheck className="h-4 w-4 text-emerald-400" />
            )}
            {docType === "cv" ? "CV" : "Cover Letter"} Versions
          </h3>

          <div className="space-y-2">
            {docs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between rounded-lg bg-slate-700/50 px-3 py-2"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-400">v{doc.version}</span>
                  {doc.variant_label && (
                    <span className="rounded bg-slate-600 px-1.5 py-0.5 text-xs text-slate-300">
                      Variant {doc.variant_label}
                    </span>
                  )}
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[doc.status] ?? "bg-slate-600 text-slate-300"}`}
                  >
                    {doc.status}
                  </span>
                  {doc.ats_score != null && (
                    <span
                      className={`text-xs font-semibold ${doc.ats_score >= 80 ? "text-emerald-400" : doc.ats_score >= 60 ? "text-amber-400" : "text-red-400"}`}
                    >
                      ATS: {doc.ats_score}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">
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
                    className="h-7 w-7 p-0 text-slate-400 hover:text-white"
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
