"use client";

import { useState } from "react";
import { Zap, Download, ExternalLink, RefreshCw, CheckCircle2 } from "lucide-react";
import {
  prepareApplication,
  updateApplicationStatus,
  type PendingApproval,
  type ApplicationPackage,
} from "@/lib/api";

interface AssistedApplyCardProps {
  application: PendingApproval;
  onStatusChange: () => void;
}

type PrepareState = "idle" | "preparing" | "ready" | "error";

export function AssistedApplyCard({
  application,
  onStatusChange,
}: AssistedApplyCardProps) {
  const [state, setState] = useState<PrepareState>(
    application.status === "ready_to_apply" ? "ready" : "idle"
  );
  const [pkg, setPkg] = useState<ApplicationPackage | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);

  const handlePrepare = async () => {
    setState("preparing");
    setErrorMsg(null);
    try {
      const result = await prepareApplication(application.application_id);
      setPkg(result);
      setState("ready");
      onStatusChange();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Preparation failed.");
      setState("error");
    }
  };

  const handleMarkApplied = async () => {
    setMarking(true);
    try {
      await updateApplicationStatus(application.application_id, "applied");
      onStatusChange();
    } finally {
      setMarking(false);
    }
  };

  const handleOpenApplication = () => {
    const url = pkg?.job_url ?? application.job_url;
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      alert("No application URL available for this job.");
    }
  };

  // ── idle state ──────────────────────────────────────────────
  if (state === "idle") {
    return (
      <button
        onClick={handlePrepare}
        className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0 transition-colors"
        style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--border)" }}
      >
        <Zap className="h-4 w-4" />
        Prepare application
      </button>
    );
  }

  // ── preparing state ─────────────────────────────────────────
  if (state === "preparing") {
    return (
      <div
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
        style={{ background: "var(--surface-2)", color: "var(--text-dim)", border: "1px solid var(--border)" }}
      >
        <RefreshCw className="h-4 w-4 animate-spin shrink-0" />
        <span>Preparing your tailored CV and cover letter…</span>
      </div>
    );
  }

  // ── error state ─────────────────────────────────────────────
  if (state === "error") {
    return (
      <div className="space-y-2">
        <p className="text-xs" style={{ color: "var(--danger)" }}>
          {errorMsg ?? "Something went wrong."}
        </p>
        <button
          onClick={handlePrepare}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0"
          style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--border)" }}
        >
          <Zap className="h-4 w-4" />
          Retry
        </button>
      </div>
    );
  }

  // ── ready state ─────────────────────────────────────────────
  return (
    <div
      className="rounded-xl p-4 space-y-4"
      style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 shrink-0" style={{ color: "var(--success)" }} />
        <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Application ready
        </span>
      </div>

      {/* Document links */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm" style={{ color: "var(--text-dim)" }}>
            ✓ Tailored CV ready
          </span>
          {pkg?.cv_path && (
            <a
              href={`/api/tailor/document/download?path=${encodeURIComponent(pkg.cv_path)}`}
              download
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium"
              style={{ background: "var(--surface)", color: "var(--accent)", border: "1px solid var(--border)" }}
            >
              <Download className="h-3 w-3" /> Download
            </a>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm" style={{ color: "var(--text-dim)" }}>
            ✓ Cover letter ready
          </span>
          {pkg?.cover_letter_path && (
            <a
              href={`/api/tailor/document/download?path=${encodeURIComponent(pkg.cover_letter_path)}`}
              download
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium"
              style={{ background: "var(--surface)", color: "var(--accent)", border: "1px solid var(--border)" }}
            >
              <Download className="h-3 w-3" /> Download
            </a>
          )}
        </div>
      </div>

      {/* Pre-fill line */}
      {pkg && Object.keys(pkg.prefill_map).length > 0 && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {"We'll pre-fill: "}
          {Object.keys(pkg.prefill_map).join(", ")} from your profile
        </p>
      )}

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-2">
        <button
          onClick={handleOpenApplication}
          className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0 flex-1"
          style={{ background: "var(--accent)", color: "var(--on-accent)" }}
        >
          Open application <ExternalLink className="h-4 w-4" />
        </button>
        <button
          onClick={handleMarkApplied}
          disabled={marking}
          className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0"
          style={{ background: "var(--surface)", color: "var(--text-dim)", border: "1px solid var(--border)" }}
        >
          {marking ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
          Mark as applied
        </button>
      </div>

      {/* Reassurance text */}
      <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
        Hatch prepared everything. Review, then submit on the company&apos;s site — you&apos;re always in control of the final click.
      </p>
    </div>
  );
}
