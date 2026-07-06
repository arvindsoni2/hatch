"use client";

import { useState } from "react";
import { Mail, RefreshCw, ExternalLink, Send, SkipForward } from "lucide-react";
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
  generateEmail,
  updateEmail,
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

export function EmailPreviewModal({ email: initialEmail, onClose, onSent }: EmailPreviewModalProps) {
  const [email, setEmail] = useState<FollowUpEmailRead>(initialEmail);
  const [previewMode, setPreviewMode] = useState<"html" | "plain">("plain");
  const [recipientEmail, setRecipientEmail] = useState(initialEmail.recipient_email ?? "");
  const [subject, setSubject] = useState(initialEmail.subject);
  const [body, setBody] = useState(initialEmail.body_plain);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recipientIsValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipientEmail.trim());

  const handleSendMailto = async () => {
    if (!recipientIsValid) {
      setError("Enter a valid recipient email address.");
      return;
    }
    setLoading(true);
    setError(null);
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
      onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setLoading(false);
    }
  };

  const handleSendSmtp = async () => {
    if (!recipientIsValid) {
      setError("Enter a valid recipient email address.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await sendEmail(email.id, {
        send_via: "smtp",
        recipient_email: recipientEmail,
        subject,
        body,
      });
      onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const updated = await regenerateEmail(email.id);
      setEmail(updated);
      setSubject(updated.subject);
      setBody(updated.body_plain);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setLoading(true);
    try {
      await skipEmail(email.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to skip");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog onOpenChange={(open) => { if (!open && !loading) onClose(); }} open>
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
            <label className="block text-xs font-medium text-slate-700 mb-1">To</label>
            <input
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
            <label className="block text-xs font-medium text-slate-700 mb-1">Subject</label>
            <input
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
              <label className="block text-xs font-medium text-slate-700">Body</label>
              <div className="flex text-xs rounded-lg border border-slate-200 overflow-hidden">
                <button
                  onClick={() => setPreviewMode("plain")}
                  className={`px-3 py-1 ${previewMode === "plain" ? "bg-slate-100 font-medium" : "text-slate-500 hover:bg-slate-50"}`}
                >
                  Plain
                </button>
                <button
                  onClick={() => setPreviewMode("html")}
                  className={`px-3 py-1 ${previewMode === "html" ? "bg-slate-100 font-medium" : "text-slate-500 hover:bg-slate-50"}`}
                >
                  Preview
                </button>
              </div>
            </div>
            {previewMode === "plain" ? (
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={10}
                className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono resize-none"
              />
            ) : (
              <div className="border border-slate-200 rounded-lg overflow-hidden h-64">
                <iframe
                  srcDoc={email.body_html}
                  className="w-full h-full"
                  sandbox="allow-same-origin"
                  title="Email HTML preview"
                />
              </div>
            )}
          </div>

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
            >
              <ExternalLink className="h-4 w-4 mr-1.5" />
              Open in Email Client
            </Button>
            <Button
              size="sm"
              onClick={handleSendSmtp}
              disabled={loading}
              className="bg-brand-600 hover:bg-brand-700 text-white"
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
