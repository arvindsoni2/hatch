"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { exportConversationalReport, type ConversationalReportRead } from "@/lib/api";

export function ReportExportControls({ report }: { report: ConversationalReportRead }) {
  const [pending, setPending] = useState<"json" | "markdown" | null>(null);
  const [error, setError] = useState(false);

  async function exportFormat(format: "json" | "markdown") {
    setPending(format);
    setError(false);
    try {
      const response = await exportConversationalReport(report.session_id, {
        format,
        expected_activity_version: report.activity_version,
        expected_retention_version: report.retention_version,
        include_candidate_reflection: true,
        contract_version: "coach_report_export_v1",
      });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? `coach-report.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(true);
    } finally {
      setPending(null);
    }
  }

  return (
    <section aria-labelledby="report-export-title" className="space-y-3">
      <h2 id="report-export-title" className="text-lg font-semibold text-[var(--text)]">Export report</h2>
      <div className="flex flex-wrap gap-3">
        <Button type="button" variant="outline" loading={pending === "json"} disabled={pending !== null} onClick={() => void exportFormat("json")}>JSON</Button>
        <Button type="button" variant="outline" loading={pending === "markdown"} disabled={pending !== null} onClick={() => void exportFormat("markdown")}>Markdown</Button>
      </div>
      {error ? <p role="alert" className="text-sm text-[var(--danger)]">The report changed before it could be exported. Refresh and try again.</p> : null}
    </section>
  );
}
