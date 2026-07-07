"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Mail, RefreshCw, Send, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  ResponsiveDialogContent,
} from "@/components/ui/dialog";
import {
  getDigestStatus,
  sendEmail,
  skipEmail,
  regenerateEmail,
  type FollowUpEmailRead,
} from "@/lib/api";

interface EmailPreviewModalProps {
  email: FollowUpEmailRead;
  onClose: () => void;
  onSent: () => void;
}

const EMAIL_TYPE_LABELS: Record<string, string> = {
  post_application: "Post-Application Follow-Up",
  post_interview_thankyou: "Interview Thank-You",
  warm_reengagement: "Warm Re-Engagement",
  custom: "Custom Email",
};

type PendingAction = "direct-send" | "regenerate" | "skip" | "close" | null;
type SmtpReadiness = "checking" | "ready" | "unavailable" | "unknown";

export function EmailPreviewModal({ email: initialEmail, onClose, onSent }: EmailPreviewModalProps) {
  const recipientId = useId();
  const subjectId = useId();
  const bodyId = useId();
  const [email, setEmail] = useState<FollowUpEmailRead>(initialEmail);
  const [previewMode, setPreviewMode] = useState<"html" | "plain">("plain");
  const [recipientEmail, setRecipientEmail] = useState(initialEmail.recipient_email ?? "");
  const [subject, setSubject] = useState(initialEmail.subject);
  const [body, setBody] = useState(initialEmail.body_plain);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [smtpReadiness, setSmtpReadiness] = useState<SmtpReadiness>("checking");
  const recipientIsValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipientEmail.trim());

  const isDirty = useMemo(
    () =>
      recipientEmail !== (email.recipient_email ?? "") ||
      subject !== email.subject ||
      body !== email.body_plain,
    [body, email.body_plain, email.recipient_email, email.subject, recipientEmail, subject],
  );

  useEffect(() => {
    let cancelled = false;

    getDigestStatus()
      .then((status) => {
        if (!cancelled) setSmtpReadiness(status.smtp_configured ? "ready" : "unavailable");
      })
      .catch(() => {
        if (!cancelled) setSmtpReadiness("unknown");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const completeAfterSuccess = (message: string, callback: () => void) => {
    setSuccess(message);
    window.setTimeout(callback, 700);
  };

  const requestClose = () => {
    if (loading) return;
    if (isDirty) {
      setPendingAction("close");
      return;
    }
    onClose();
  };

  const handleSendMailto = async () => {
    if (!recipientIsValid) {
      setError("Enter a valid recipient email address.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await sendEmail(email.id, {
        send_via: "mailto",
        recipient_email: recipientEmail,
        subject,
        body,
      });
      if (res.mailto_link) {
        window.open(res.mailto_link, "_blank");
      }
      completeAfterSuccess("Email client opened.", onSent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setLoading(false);
    }
  };

  const handleSendSmtp = () => {
    if (!recipientIsValid) {
      setError("Enter a valid recipient email address.");
      return;
    }
    if (smtpReadiness !== "ready") return;
    setError(null);
    setSuccess(null);
    setPendingAction("direct-send");
  };

  const confirmSendSmtp = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await sendEmail(email.id, {
        send_via: "smtp",
        recipient_email: recipientEmail,
        subject,
        body,
      });
      setPendingAction(null);
      completeAfterSuccess("Email sent directly.", onSent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (isDirty) {
      setPendingAction("regenerate");
      return;
    }
    await confirmRegenerate();
  };

  const confirmRegenerate = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await regenerateEmail(email.id);
      setEmail(updated);
      setRecipientEmail(updated.recipient_email ?? "");
      setSubject(updated.subject);
      setBody(updated.body_plain);
      setPendingAction(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    if (isDirty) {
      setPendingAction("skip");
      return;
    }
    await confirmSkip();
  };

  const confirmSkip = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await skipEmail(email.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to skip");
    } finally {
      setLoading(false);
    }
  };

  const confirmDiscardAndClose = () => {
    setPendingAction(null);
    onClose();
  };

  const smtpMessage =
    smtpReadiness === "checking"
      ? "Checking SMTP readiness..."
      : smtpReadiness === "ready"
        ? "SMTP is configured for direct send."
        : smtpReadiness === "unavailable"
          ? "Direct send is unavailable until SMTP is configured."
          : "Direct send is disabled because SMTP status could not be checked.";

  return (
    <Dialog onOpenChange={(open) => { if (!open) requestClose(); }} open>
      <ResponsiveDialogContent preventClose={loading}>
        {/* Header */}
        <DialogHeader className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <Mail aria-hidden="true" className="h-5 w-5 text-[var(--accent)]" />
            <div>
              <DialogTitle className="text-sm">
                {EMAIL_TYPE_LABELS[email.email_type] ?? email.email_type}
              </DialogTitle>
              <DialogDescription className="sr-only">
                Review the recipient, subject, and message before sending.
              </DialogDescription>
              {(email.job_title || email.company) && (
                <p className="text-xs text-[var(--text-muted)]">
                  {email.job_title}{email.company ? `, ${email.company}` : ""}
                </p>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Scrollable body */}
        <DialogBody className="space-y-4">
          {/* Recipient */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1" htmlFor={recipientId}>To</label>
            <input
              id={recipientId}
              type="email"
              autoComplete="email"
              name="recipient_email"
              aria-invalid={error && !recipientIsValid ? true : undefined}
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="recruiter@example.com…"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Subject */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1" htmlFor={subjectId}>Subject</label>
            <input
              id={subjectId}
              type="text"
              autoComplete="off"
              name="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Body preview toggle */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-medium text-slate-700" htmlFor={bodyId}>Body</label>
              <div className="flex text-xs rounded-lg border border-slate-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setPreviewMode("plain")}
                  className={`px-3 py-1 ${previewMode === "plain" ? "bg-slate-100 font-medium" : "text-slate-500 hover:bg-slate-50"}`}
                >
                  Plain
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode("html")}
                  className={`px-3 py-1 ${previewMode === "html" ? "bg-slate-100 font-medium" : "text-slate-500 hover:bg-slate-50"}`}
                >
                  Preview
                </button>
              </div>
            </div>
            {previewMode === "plain" ? (
              <textarea
                id={bodyId}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={10}
                className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono resize-none"
              />
            ) : (
              <div className="space-y-2">
                <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  HTML preview is sandboxed. Switch back to Plain to edit the fallback text.
                </p>
                <div className="border border-slate-200 rounded-lg overflow-hidden h-64">
                  <iframe
                    srcDoc={email.body_html}
                    className="w-full h-full"
                    sandbox=""
                    title="Sandboxed email HTML preview"
                  />
                </div>
              </div>
            )}
          </div>

          <p
            className={`rounded-lg border px-3 py-2 text-xs ${
              smtpReadiness === "ready"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-amber-200 bg-amber-50 text-amber-800"
            }`}
          >
            {smtpMessage}
          </p>

          {pendingAction === "direct-send" && (
            <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="flex items-start gap-2">
                <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 text-amber-700" />
                <div>
                  <h3 className="text-sm font-semibold text-amber-950">Review before direct send</h3>
                  <p className="mt-1 text-xs text-amber-900">
                    Hatch will send this email through the configured SMTP server.
                  </p>
                </div>
              </div>
              <dl className="grid gap-2 text-xs text-amber-950 sm:grid-cols-[5rem_1fr]">
                <dt className="font-medium">To</dt>
                <dd>{recipientEmail}</dd>
                <dt className="font-medium">Subject</dt>
                <dd>{subject}</dd>
                <dt className="font-medium">Body</dt>
                <dd className="max-h-24 overflow-y-auto whitespace-pre-wrap rounded border border-amber-200 bg-white/70 p-2">
                  {body}
                </dd>
              </dl>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button type="button" variant="outline" size="sm" onClick={() => setPendingAction(null)} disabled={loading}>
                  Cancel
                </Button>
                <Button type="button" size="sm" onClick={confirmSendSmtp} disabled={loading}>
                  Confirm direct send
                </Button>
              </div>
            </div>
          )}

          {(pendingAction === "regenerate" || pendingAction === "skip" || pendingAction === "close") && (
            <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="flex items-start gap-2">
                <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 text-amber-700" />
                <div>
                  <h3 className="text-sm font-semibold text-amber-950">Discard unsaved email edits?</h3>
                  <p className="mt-1 text-xs text-amber-900">
                    Your current recipient, subject, or body edits have not been sent yet.
                  </p>
                </div>
              </div>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button type="button" variant="outline" size="sm" onClick={() => setPendingAction(null)} disabled={loading}>
                  Keep editing
                </Button>
                {pendingAction === "regenerate" && (
                  <Button type="button" size="sm" onClick={confirmRegenerate} disabled={loading}>
                    Discard edits and regenerate
                  </Button>
                )}
                {pendingAction === "skip" && (
                  <Button type="button" size="sm" onClick={confirmSkip} disabled={loading}>
                    Discard edits and skip
                  </Button>
                )}
                {pendingAction === "close" && (
                  <Button type="button" size="sm" onClick={confirmDiscardAndClose} disabled={loading}>
                    Discard edits and close
                  </Button>
                )}
              </div>
            </div>
          )}

          {success && (
            <p
              className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
              role="status"
            >
              <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
              {success}
            </p>
          )}

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2" role="alert">
              {error}
            </p>
          )}
        </DialogBody>

        {/* Footer actions */}
        <DialogFooter className="items-stretch justify-between sm:items-center">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRegenerate}
              disabled={loading}
              className="text-slate-600"
              type="button"
            >
              <RefreshCw className="h-4 w-4 mr-1.5" />
              Regenerate
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSkip}
              disabled={loading}
              className="text-slate-400"
              type="button"
            >
              <SkipForward className="h-4 w-4 mr-1.5" />
              Skip
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleSendMailto}
              disabled={loading}
              type="button"
            >
              <ExternalLink className="h-4 w-4 mr-1.5" />
              Open in Email Client
            </Button>
            <Button
              size="sm"
              onClick={handleSendSmtp}
              disabled={loading || smtpReadiness !== "ready"}
              className={smtpReadiness === "ready" ? "bg-brand-600 hover:bg-brand-700 text-white" : undefined}
              type="button"
            >
              <Send className="h-4 w-4 mr-1.5" />
              Send Directly
            </Button>
          </div>
        </DialogFooter>
      </ResponsiveDialogContent>
    </Dialog>
  );
}
