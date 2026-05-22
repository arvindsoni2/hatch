"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Loader2 } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { InterviewTimeline } from "./InterviewTimeline";
import { FollowUpList } from "./FollowUpList";
import { ActivityFeed } from "./ActivityFeed";
import { RecruiterContact } from "./RecruiterContact";
import {
  fetchApplication,
  updateApplicationStatus,
  addApplicationNote,
  completeFollowUp,
  createInterview,
  type Application,
  type ApplicationStatus,
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

  const loadApp = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchApplication(applicationId);
      setApp(data);
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
      alert(e instanceof Error ? e.message : "Failed to update status");
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

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div
        className="relative w-full max-w-2xl h-full bg-white shadow-2xl overflow-y-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-start justify-between z-10">
          <div className="flex-1 min-w-0 pr-4">
            {app ? (
              <>
                <h2 className="text-lg font-semibold text-slate-800 truncate">
                  {app.job_id
                    ? "Tracked Application"
                    : app.agency_name ?? "Manual Application"}
                </h2>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <Badge variant={`status-${app.status}` as Parameters<typeof Badge>[0]["variant"]}>
                    {app.status}
                  </Badge>
                  <Badge variant={`priority-${app.priority}` as Parameters<typeof Badge>[0]["variant"]}>
                    {app.priority}
                  </Badge>
                  {app.applied_date && (
                    <span className="text-xs text-slate-500">
                      Applied {format(new Date(app.applied_date), "d MMM yyyy")}
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div className="h-6 bg-slate-200 rounded w-48 animate-pulse" />
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-slate-200 px-6">
          <div className="flex gap-0">
            {TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === tab
                    ? "border-indigo-500 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-700",
                )}
              >
                {tab}
                {tab === "Follow-ups" && pendingFollowUps > 0 && (
                  <span className="ml-1 text-xs bg-red-100 text-red-600 rounded-full px-1.5 py-0.5">
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
              <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-500">{error}</div>
          ) : app ? (
            <>
              {activeTab === "Overview" && (
                <div className="space-y-6">
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
      </div>
    </div>
  );
}
