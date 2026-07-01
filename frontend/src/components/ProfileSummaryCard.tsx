"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileCheck2 } from "lucide-react";
import { fetchProfileSummary } from "@/lib/api";

function Chips({ values, limit }: { values: string[]; limit?: number }) {
  const visible = limit ? values.slice(0, limit) : values;
  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map((value) => (
        <span key={value} className="rounded-full px-2 py-1 text-xs" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
          {value}
        </span>
      ))}
      {limit && values.length > limit ? <span className="text-xs" style={{ color: "var(--text-muted)" }}>+{values.length - limit} more</span> : null}
    </div>
  );
}

export function ProfileSummaryCard({ compact = false }: { compact?: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ["profile-summary"],
    queryFn: fetchProfileSummary,
  });
  if (isLoading || !data) return null;

  return (
    <section className="rounded-xl p-5 space-y-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold" style={{ color: "var(--text)" }}>{data.identity.name || "Profile summary"}</h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>{data.identity.title || "No professional title configured"}</p>
        </div>
        <div className="flex items-center gap-1 text-xs" style={{ color: data.master_cv.status === "present" ? "var(--success)" : "var(--warning)" }}>
          <FileCheck2 className="h-4 w-4" /> CV {data.master_cv.status}
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Target roles</p>
        <Chips values={data.target_roles} limit={compact ? 3 : undefined} />
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Evidence Hatch will use</p>
        <Chips values={data.skills} limit={compact ? 8 : 20} />
      </div>
      {!compact ? (
        <>
          <div><p className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Domains</p><Chips values={data.domains} /></div>
          <div><p className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Certifications</p><Chips values={data.certifications} /></div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Master CV: {data.master_cv.path}</p>
        </>
      ) : null}
      {data.warnings.length ? (
        <div className="space-y-1 rounded-lg p-3" style={{ background: "var(--warning-soft)" }}>
          {data.warnings.slice(0, compact ? 2 : undefined).map((warning) => (
            <p key={warning.code} className="flex gap-2 text-xs" style={{ color: "var(--warning)" }}><AlertTriangle className="h-3.5 w-3.5 shrink-0" />{warning.message}</p>
          ))}
        </div>
      ) : null}
      {compact && data.master_cv.status !== "present" ? <Link href="/settings/resume" className="text-xs underline" style={{ color: "var(--accent)" }}>Upload master CV</Link> : null}
    </section>
  );
}
