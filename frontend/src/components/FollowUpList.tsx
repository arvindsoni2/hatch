"use client";

import { useState } from "react";
import { isPast, formatDistanceToNow, format } from "date-fns";
import { AlertCircle, CheckCircle2, Clock, Mail, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FollowUp } from "@/lib/api";
import {
  fetchEmailById,
  generateEmail,
  getAsyncJob,
  type FollowUpEmailRead,
} from "@/lib/api";
import { EmailPreviewModal } from "./EmailPreviewModal";

interface FollowUpListProps {
  followUps: FollowUp[];
  applicationId?: string;
  onComplete: (id: string) => Promise<void>;
}

const TYPE_LABELS: Record<string, string> = {
  check_in: "Check In",
  thank_you: "Thank You",
  negotiation: "Negotiation",
  general: "General",
};

const EMAIL_TYPE_MAP: Record<string, string> = {
  thank_you: "post_interview_thankyou",
  check_in: "post_application",
  general: "post_application",
};

export function FollowUpList({ followUps, applicationId, onComplete }: FollowUpListProps) {
  const [emailModal, setEmailModal] = useState<FollowUpEmailRead | null>(null);
  const [generatingFor, setGeneratingFor] = useState<string | null>(null);
  const [emailIds, setEmailIds] = useState<Record<string, string>>({});

  if (followUps.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-[var(--text-muted)]">No follow-ups scheduled.</p>
    );
  }

  const sorted = [...followUps].sort(
    (a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime(),
  );

  const handleOpenEmail = async (followUpId: string) => {
    const emailId = emailIds[followUpId];
    if (!emailId) return;
    try {
      const email = await fetchEmailById(emailId);
      setEmailModal(email);
    } catch {
      // ignore
    }
  };

  const handleGenerateEmail = async (followUp: FollowUp) => {
    if (!applicationId) return;
    setGeneratingFor(followUp.id);
    try {
      const emailType = EMAIL_TYPE_MAP[followUp.type] ?? "post_application";
      const jobRef = await generateEmail(applicationId, emailType);
      // Poll until the email generation job completes
      let email: FollowUpEmailRead | null = null;
      while (!email) {
        const job = await getAsyncJob<FollowUpEmailRead>(jobRef.job_id);
        if (job.status === "done" && job.result) { email = job.result; break; }
        if (job.status === "failed") throw new Error(job.error ?? "Email generation failed");
        await new Promise((r) => setTimeout(r, 2000));
      }
      setEmailIds((prev) => ({ ...prev, [followUp.id]: email!.id }));
      setEmailModal(email);
    } catch {
      // ignore
    } finally {
      setGeneratingFor(null);
    }
  };

  return (
    <>
      <div className="flex flex-col gap-2">
        {sorted.map((fu) => {
          const overdue = !fu.completed && isPast(new Date(fu.due_date));
          const hasEmailDraft = Boolean(emailIds[fu.id]);

          return (
            <div
              key={fu.id}
              className={cn(
                "flex items-start gap-3 p-3 rounded-lg border",
                fu.completed
                  ? "border-[var(--border)] bg-[var(--surface-2)] opacity-60"
                  : overdue
                    ? "border-[var(--danger)] bg-[var(--danger-soft)]"
                    : "border-[var(--border)] bg-[var(--surface)]",
              )}
            >
              <button
                onClick={() => !fu.completed && onComplete(fu.id)}
                disabled={fu.completed}
                className={cn(
                  "mt-0.5 shrink-0 rounded-full p-0.5 transition-colors",
                  fu.completed
                    ? "text-[var(--success)] cursor-default"
                    : overdue
                      ? "text-[var(--danger)] hover:opacity-80"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]",
                )}
              >
                {fu.completed ? (
                  <CheckCircle2 className="h-5 w-5" />
                ) : (
                  <Clock className="h-5 w-5" />
                )}
              </button>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={cn(
                      "text-xs font-medium px-2 py-0.5 rounded-full",
                      fu.type === "check_in"
                        ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                        : fu.type === "thank_you"
                          ? "bg-[var(--purple-soft)] text-[var(--purple)]"
                          : fu.type === "negotiation"
                            ? "bg-[var(--warning-soft)] text-[var(--warning)]"
                            : "bg-[var(--surface-2)] text-[var(--text-dim)]",
                    )}
                  >
                    {TYPE_LABELS[fu.type] ?? fu.type}
                  </span>
                  {overdue && (
                    <span className="flex items-center gap-1 text-xs font-medium text-[var(--danger)]">
                      <AlertCircle className="h-3 w-3" />
                      Overdue
                    </span>
                  )}
                  {/* Email badge / generate button */}
                  {!fu.completed && overdue && applicationId && (
                    hasEmailDraft ? (
                      <button
                        onClick={() => handleOpenEmail(fu.id)}
                        className="flex items-center gap-1 rounded-full bg-[var(--success-soft)] px-2 py-0.5 text-xs font-medium text-[var(--success)] transition-colors hover:opacity-80"
                      >
                        <Mail className="h-3 w-3" />
                        Email Ready
                      </button>
                    ) : (
                      <button
                        onClick={() => handleGenerateEmail(fu)}
                        disabled={generatingFor === fu.id}
                        className="flex items-center gap-1 rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-xs font-medium text-[var(--accent)] transition-colors hover:opacity-80 disabled:opacity-50"
                      >
                        {generatingFor === fu.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Mail className="h-3 w-3" />
                        )}
                        Generate Email
                      </button>
                    )
                  )}
                </div>
                {fu.note && (
                  <p className="mt-1 line-clamp-2 text-xs text-[var(--text-dim)]">{fu.note}</p>
                )}
                <p className={cn("mt-1 text-xs", overdue ? "text-[var(--danger)]" : "text-[var(--text-muted)]")}>
                  Due {format(new Date(fu.due_date), "EEE d MMM")}
                  {!fu.completed &&
                    ` · ${formatDistanceToNow(new Date(fu.due_date), { addSuffix: true })}`}
                  {fu.completed &&
                    fu.completed_at &&
                    ` · Completed ${format(new Date(fu.completed_at), "d MMM")}`}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {emailModal && (
        <EmailPreviewModal
          email={emailModal}
          onClose={() => setEmailModal(null)}
          onSent={() => {
            setEmailModal(null);
          }}
        />
      )}
    </>
  );
}
