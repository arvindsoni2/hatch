"use client";

import { useState } from "react";
import { Mail, RefreshCw, X, ExternalLink, Send, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
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

  const handleSendMailto = async () => {
    if (!recipientEmail.trim()) {
      setError("Recipient email is required");
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
    if (!recipientEmail.trim()) {
      setError("Recipient email is required");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-brand-600" />
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                {EMAIL_TYPE_LABELS[email.email_type] ?? email.email_type}
              </h2>
              {(email.job_title || email.company) && (
                <p className="text-xs text-slate-500">
                  {email.job_title}{email.company ? ` · ${email.company}` : ""}
                </p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Recipient */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">To</label>
            <input
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="recruiter@agency.co.uk"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Subject */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Subject</label>
            <input
              type="text"
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
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between gap-2 px-6 py-4 border-t border-slate-200 bg-slate-50 rounded-b-xl">
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
        </div>
      </div>
    </div>
  );
}
