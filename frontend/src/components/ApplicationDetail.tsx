"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, ExternalLink, FileText, Download, Sparkles } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { StatusBadge } from "./ui/status-badge";
import { InterviewTimeline } from "./InterviewTimeline";
import { FollowUpList } from "./FollowUpList";
import { ActivityFeed } from "./ActivityFeed";
import { RecruiterContact } from "./RecruiterContact";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  fetchApplication,
  getDocumentHistory,
  updateApplicationStatus,
  addApplicationNote,
  completeFollowUp,
  createInterview,
  DocumentQualityAcknowledgementRequiredError,
  downloadDocument,
  type Application,
  type ApplicationStatus,
  type GeneratedDocument,
} from "@/lib/api";

const TABS = ["Overview", "Interviews", "Follow-ups", "Activity"] as const;
type Tab = (typeof TABS)[number];

const STATUS_OPTIONS: ApplicationStatus[] = [
  "discovered",
  "shortlisted",
  "applied",
  "interview",
  "offered",
  "accepted",
  "rejected",
  "withdrawn",
  "declined",
];

const INTERVIEW_TYPES = [
  "phone_screen",
  "technical",
  "behavioural",
  "panel",
  "presentation",
  "culture_fit",
  "final",
  "assessment",
];

interface ApplicationDetailProps {
  applicationId: string;
  onClose: () => void;
  onStatusChange?: () => void;
}

export function ApplicationDetail({
  applicationId,
  onClose,
  onStatusChange,
}: ApplicationDetailProps) {
  const [app, setApp] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [noteText, setNoteText] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  const [newInterviewType, setNewInterviewType] = useState("phone_screen");
  const [newInterviewDate, setNewInterviewDate] = useState("");
  const [addingInterview, setAddingInterview] = useState(false);
  const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
  const [documentDownloadNotice, setDocumentDownloadNotice] = useState<string | null>(null);
  const [acknowledgementDocumentId, setAcknowledgementDocumentId] = useState<string | null>(null);

  const loadApp = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchApplication(applicationId);
      setApp(data);
      // Load generated documents in parallel
      const docs = await getDocumentHistory(applicationId).catch(() => []);
      setDocuments(docs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load application");
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    void loadApp();
  }, [loadApp]);

  const handleStatusChange = async (newStatus: ApplicationStatus) => {
    if (!app) return;
    try {
      await updateApplicationStatus(app.id, newStatus);
      onStatusChange?.();
      await loadApp();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  };

  const handleAddNote = async () => {
    if (!noteText.trim() || !app) return;
    setAddingNote(true);
    try {
      await addApplicationNote(app.id, noteText);
      setNoteText("");
      await loadApp();
    } finally {
      setAddingNote(false);
    }
  };

  const handleDocumentDownload = async (documentId: string, acknowledgeQualityWarnings = false) => {
    try {
      setDocumentDownloadNotice(null);
      setAcknowledgementDocumentId(null);
      await downloadDocument(documentId, { acknowledgeQualityWarnings });
    } catch (e) {
      if (e instanceof DocumentQualityAcknowledgementRequiredError) {
        setDocumentDownloadNotice(e.message);
        setAcknowledgementDocumentId(documentId);
        return;
      }
      setDocumentDownloadNotice(e instanceof Error ? e.message : "Could not download this document.");
    }
  };

  const handleCompleteFollowUp = async (id: string) => {
    await completeFollowUp(id);
    await loadApp();
  };

  const handleAddInterview = async () => {
    if (!app) return;
    setAddingInterview(true);
    try {
      await createInterview({
        application_id: app.id,
        type: newInterviewType,
        round_number: (app.interviews?.length ?? 0) + 1,
        scheduled_at: newInterviewDate || undefined,
      });
      setNewInterviewDate("");
      await loadApp();
    } finally {
      setAddingInterview(false);
    }
  };

  const pendingFollowUps = app?.follow_ups?.filter((f) => !f.completed).length ?? 0;
  const title = app?.job?.title ?? app?.agency_name ?? "Manual Application";
  const sheetTitle = app ? `${title} application details` : "Application details";

  return (
    <Sheet onOpenChange={(open) => { if (!open) onClose(); }} open>
      <SheetContent className="max-w-2xl">
        <SheetTitle className="sr-only">{sheetTitle}</SheetTitle>
        <SheetDescription className="sr-only">
          Review the application, interviews, follow-ups, and activity.
        </SheetDescription>
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-start gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-6 py-4 pr-16">
          <button
            type="button"
            onClick={onClose}
            className="hatch-interactive mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-[var(--text-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
            aria-label="Back to Applications"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0 pr-4">
            {app ? (
              <>
                <div className="flex items-center gap-2 min-w-0">
                  <h2 className="truncate text-lg font-semibold text-[var(--text)]">
                    {title}
                  </h2>
                  {app.job?.url && (
                    <a
                      href={app.job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-[var(--text-muted)] transition-colors hover:text-[var(--accent)]"
                      title="View original job posting"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
                {app.job?.company && (
                  <p className="truncate text-sm text-[var(--text-dim)]">{app.job.company}</p>
                )}
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <StatusBadge tone="warning">{app.status}</StatusBadge>
                  <StatusBadge tone={app.priority === "urgent" || app.priority === "high" ? "warning" : "neutral"}>
                    {app.priority}
                  </StatusBadge>
                  {app.applied_date && (
                    <span className="text-xs text-[var(--text-dim)]">
                      Applied {format(new Date(app.applied_date), "d MMM yyyy")}
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div className="h-6 w-48 animate-pulse rounded bg-[var(--surface-2)]" />
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-[var(--border)] px-6">
          <div className="flex gap-0">
            {TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === tab
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "border-transparent text-[var(--text-dim)] hover:text-[var(--text)]",
                )}
              >
                {tab}
                {tab === "Follow-ups" && pendingFollowUps > 0 && (
                  <span className="ml-1 rounded-full bg-[var(--danger-soft)] px-1.5 py-0.5 text-xs text-[var(--danger)]">
                    {pendingFollowUps}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 px-6 py-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-[var(--accent)]" />
            </div>
          ) : error ? (
            <div className="py-12 text-center text-[var(--danger)]">{error}</div>
          ) : app ? (
            <>
              {activeTab === "Overview" && (
                <div className="space-y-6">
                  {/* Agent banner */}
                  {app.agent_created && (
                    <div className="flex items-start gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
                      <Sparkles className="h-4 w-4 text-indigo-500 mt-0.5 shrink-0" />
                      <div className="text-sm text-indigo-800">
                        <span className="font-medium">Hatch prepared tailored documents for this role.</span>{" "}
                        {app.job?.url ? (
                          <>
                            Review the CV and cover letter below, then{" "}
                            <a
                              href={app.job.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="underline font-medium hover:text-indigo-600"
                            >
                              apply at the original posting
                            </a>
                            {" "}manually.
                          </>
                        ) : (
                          "Review the CV and cover letter below before applying manually."
                        )}
                      </div>
                    </div>
                  )}

                  <div className="flex justify-end">
                    <Link
                      href={app.job?.url ? `/tailor?jobUrl=${encodeURIComponent(app.job.url)}` : "/tailor"}
                      className="hatch-interactive inline-flex min-h-10 items-center justify-center rounded-lg border px-3 text-sm font-medium"
                      style={{ borderColor: "var(--border)", color: "var(--text)", textDecoration: "none" }}
                    >
                      <FileText className="mr-2 h-4 w-4" /> Open in CV Studio
                    </Link>
                  </div>

                  {/* Generated documents */}
                  {documents.length > 0 && (
                    <div>
                      <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                        Generated Documents
                      </h3>
                      {documentDownloadNotice && (
                        <div className="mb-2 flex flex-wrap items-center gap-2" role="status">
                          <p className="text-xs text-rose-600">
                            {documentDownloadNotice}
                          </p>
                          {acknowledgementDocumentId && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={() => void handleDocumentDownload(acknowledgementDocumentId, true)}
                            >
                              Download anyway
                            </Button>
                          )}
                        </div>
                      )}
                      <div className="space-y-2">
                        {documents.map((doc) => (
                          <div
                            key={doc.id}
                            className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-slate-700 capitalize">
                                  {doc.document_type.replace(/_/g, " ")}
                                  {doc.version > 1 && (
                                    <span className="ml-1 text-xs text-slate-400">v{doc.version}</span>
                                  )}
                                </p>
                                <p className="text-xs text-slate-400">
                                  {format(new Date(doc.created_at), "d MMM yyyy, HH:mm")}
                                  {doc.ats_score != null && (
                                    <span className="ml-2 text-indigo-500 font-medium">ATS {Math.round(doc.ats_score)}%</span>
                                  )}
                                </p>
                              </div>
                            </div>
                            <button
                              onClick={() => void handleDocumentDownload(doc.id)}
                              className="shrink-0 ml-3 text-slate-400 hover:text-indigo-500 transition-colors"
                              title="Download"
                            >
                              <Download className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Status */}
                  <div>
                    <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                      Move to Status
                    </label>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {STATUS_OPTIONS.map((s) => (
                        <button
                          key={s}
                          onClick={() => s !== app.status && void handleStatusChange(s)}
                          className={cn(
                            "text-xs px-3 py-1.5 rounded-full border transition-colors",
                            s === app.status
                              ? "bg-indigo-500 text-white border-indigo-500"
                              : "border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-600",
                          )}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Recruiter */}
                  <div>
                    <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                      Recruiter / Agency
                    </h3>
                    <RecruiterContact
                      recruiterName={app.recruiter_name}
                      recruiterEmail={app.recruiter_email}
                      recruiterPhone={app.recruiter_phone}
                      agencyName={app.agency_name}
                    />
                  </div>

                  {/* Key Dates */}
                  <div>
                    <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                      Key Dates
                    </h3>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-slate-400">Tracked: </span>
                        <span>{format(new Date(app.created_at), "d MMM yyyy")}</span>
                      </div>
                      {app.applied_date && (
                        <div>
                          <span className="text-slate-400">Applied: </span>
                          <span>{format(new Date(app.applied_date), "d MMM yyyy")}</span>
                        </div>
                      )}
                      {app.salary_offered != null && (
                        <div>
                          <span className="text-slate-400">Offered: </span>
                          <span>£{app.salary_offered.toLocaleString()}/day</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Notes */}
                  <div>
                    <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                      Notes
                    </h3>
                    {app.notes && (
                      <div className="text-sm text-slate-700 whitespace-pre-wrap bg-slate-50 rounded-lg p-3 mb-3 border border-slate-200">
                        {app.notes}
                      </div>
                    )}
                    <textarea
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      placeholder="Add a note..."
                      className="w-full text-sm border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      rows={3}
                    />
                    <Button
                      onClick={() => void handleAddNote()}
                      disabled={!noteText.trim() || addingNote}
                      size="sm"
                      className="mt-2"
                    >
                      {addingNote ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                      ) : null}
                      Add Note
                    </Button>
                  </div>
                </div>
              )}

              {activeTab === "Interviews" && (
                <div className="space-y-6">
                  <InterviewTimeline interviews={app.interviews ?? []} />

                  {/* Add interview form */}
                  <div className="border-t border-slate-200 pt-4">
                    <h4 className="text-sm font-medium text-slate-700 mb-3">
                      Schedule Interview Round
                    </h4>
                    <div className="flex gap-2 flex-wrap">
                      <select
                        value={newInterviewType}
                        onChange={(e) => setNewInterviewType(e.target.value)}
                        className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      >
                        {INTERVIEW_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t.replace(/_/g, " ")}
                          </option>
                        ))}
                      </select>
                      <input
                        type="datetime-local"
                        value={newInterviewDate}
                        onChange={(e) => setNewInterviewDate(e.target.value)}
                        className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                      <Button
                        onClick={() => void handleAddInterview()}
                        disabled={addingInterview}
                        size="sm"
                      >
                        {addingInterview ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : null}
                        Schedule
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "Follow-ups" && (
                <FollowUpList
                  followUps={app.follow_ups ?? []}
                  applicationId={app.id}
                  onComplete={handleCompleteFollowUp}
                />
              )}

              {activeTab === "Activity" && (
                <ActivityFeed activity={app.activity ?? []} />
              )}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
