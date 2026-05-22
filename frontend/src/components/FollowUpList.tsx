"use client";

import { useState } from "react";
import { isPast, formatDistanceToNow, format } from "date-fns";
import { AlertCircle, CheckCircle2, Clock, Mail, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FollowUp } from "@/lib/api";
import {
  fetchEmailById,
  generateEmail,
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
      <p className="text-sm text-slate-400 py-4 text-center">No follow-ups scheduled.</p>
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
      const email = await generateEmail(applicationId, emailType);
      setEmailIds((prev) => ({ ...prev, [followUp.id]: email.id }));
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
                  ? "bg-slate-50 border-slate-200 opacity-60"
                  : overdue
                    ? "bg-red-50 border-red-200"
                    : "bg-white border-slate-200",
              )}
            >
              <button
                onClick={() => !fu.completed && onComplete(fu.id)}
                disabled={fu.completed}
                className={cn(
                  "mt-0.5 shrink-0 rounded-full p-0.5 transition-colors",
                  fu.completed
                    ? "text-green-500 cursor-default"
                    : overdue
                      ? "text-red-400 hover:text-red-600"
                      : "text-slate-300 hover:text-slate-500",
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
                        ? "bg-blue-100 text-blue-700"
                        : fu.type === "thank_you"
                          ? "bg-purple-100 text-purple-700"
                          : fu.type === "negotiation"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-slate-100 text-slate-600",
                    )}
                  >
                    {TYPE_LABELS[fu.type] ?? fu.type}
                  </span>
                  {overdue && (
                    <span className="flex items-center gap-1 text-xs text-red-600 font-medium">
                      <AlertCircle className="h-3 w-3" />
                      Overdue
                    </span>
                  )}
                  {/* Email badge / generate button */}
                  {!fu.completed && overdue && applicationId && (
                    hasEmailDraft ? (
                      <button
                        onClick={() => handleOpenEmail(fu.id)}
                        className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700 hover:bg-green-200 transition-colors"
                      >
                        <Mail className="h-3 w-3" />
                        Email Ready
                      </button>
                    ) : (
                      <button
                        onClick={() => handleGenerateEmail(fu)}
                        disabled={generatingFor === fu.id}
                        className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors disabled:opacity-50"
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
                  <p className="text-xs text-slate-600 mt-1 line-clamp-2">{fu.note}</p>
                )}
                <p className={cn("text-xs mt-1", overdue ? "text-red-500" : "text-slate-400")}>
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
