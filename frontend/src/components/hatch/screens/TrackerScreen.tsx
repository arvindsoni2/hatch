"use client";

import { useMemo, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  closestCenter,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  updateApplicationStatus,
  type Application,
  type ApplicationListItem,
  type ApplicationStatus,
} from "@/lib/api";
import { Dot } from "../Dot";
import { HatchIcon } from "../HatchIcon";
import { ScorePill } from "../ScorePill";

type BoardStage =
  | "discovered"
  | "preparing"
  | "ready_to_apply"
  | "applied"
  | "interview"
  | "offered"
  | "accepted";

interface StageDefinition {
  key: BoardStage;
  label: string;
  description: string;
  color: string;
}

interface TrackerScreenProps {
  applications: ApplicationListItem[];
  onStatusChange?: (
    id: string,
    status: ApplicationStatus,
  ) => Promise<Application | ApplicationListItem | void>;
}

const STAGES: StageDefinition[] = [
  { key: "discovered", label: "Discovered", description: "Roles being considered", color: "var(--accent)" },
  { key: "preparing", label: "Preparing", description: "Tailoring and review", color: "var(--purple)" },
  { key: "ready_to_apply", label: "Ready to submit", description: "Package is complete", color: "var(--success)" },
  { key: "applied", label: "Applied", description: "Submission confirmed", color: "var(--purple)" },
  { key: "interview", label: "Interview", description: "Interview process", color: "var(--warning)" },
  { key: "offered", label: "Offered", description: "Offer received", color: "var(--success)" },
  { key: "accepted", label: "Accepted", description: "Offer accepted", color: "var(--success)" },
];

const STAGE_BY_STATUS: Record<ApplicationStatus, BoardStage | "closed"> = {
  discovered: "discovered",
  shortlisted: "discovered",
  parked: "discovered",
  ready: "preparing",
  approved: "preparing",
  preparing: "preparing",
  ready_to_apply: "ready_to_apply",
  applied: "applied",
  interview: "interview",
  offered: "offered",
  accepted: "accepted",
  rejected: "closed",
  withdrawn: "closed",
  declined: "closed",
};

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  discovered: "Discovered",
  shortlisted: "Shortlisted",
  parked: "Parked",
  ready: "Awaiting approval",
  approved: "Approved",
  preparing: "Tailoring",
  ready_to_apply: "Ready to submit",
  applied: "Applied",
  interview: "Interview",
  offered: "Offered",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  declined: "Declined",
};

function nextStatus(status: ApplicationStatus): ApplicationStatus | null {
  if (["discovered", "shortlisted", "parked", "ready"].includes(status)) return "applied";
  if (status === "ready_to_apply") return "applied";
  if (status === "applied") return "interview";
  if (status === "interview") return "offered";
  if (status === "offered") return "accepted";
  return null;
}

function stageTargetStatus(stage: BoardStage): ApplicationStatus {
  return stage;
}

function moveOptions(status: ApplicationStatus): ApplicationStatus[] {
  const options: ApplicationStatus[] = [];
  const next = nextStatus(status);
  if (next) options.push(next);

  if (status === "offered") {
    options.push("declined", "withdrawn");
  } else if (!["accepted", "rejected", "withdrawn", "declined"].includes(status)) {
    options.push("rejected", "withdrawn");
  }
  return options;
}

function confirmationMessage(application: ApplicationListItem, status: ApplicationStatus): string {
  const role = application.job_title ?? "this application";
  if (status === "applied") {
    return `Confirm that you submitted ${role}. This will record the application date and prepare a Coach session.`;
  }
  if (status === "interview") return `Confirm that ${role} has progressed to interview.`;
  if (status === "offered") return `Confirm that you received an offer for ${role}.`;
  if (status === "accepted") return `Confirm that you accepted the offer for ${role}.`;
  if (status === "rejected") return `Move ${role} to Rejected?`;
  if (status === "withdrawn") return `Withdraw ${role} from your active pipeline?`;
  if (status === "declined") return `Confirm that you declined the offer for ${role}.`;
  return `Move ${role} to ${STATUS_LABELS[status]}?`;
}

interface JobCardProps {
  application: ApplicationListItem;
  onMove: (application: ApplicationListItem, status: ApplicationStatus) => void;
}

function JobCard({ application, onMove }: JobCardProps) {
  const next = nextStatus(application.status);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: application.id,
    disabled: next === null,
    data: { application },
  });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Translate.toString(transform),
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 11,
        padding: 11,
        opacity: isDragging ? 0.35 : 1,
        transition: "border-color 0.12s, opacity 0.12s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {application.job_title ?? "Untitled Role"}
            </span>
            {application.job_url && (
              <a
                href={application.job_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open ${application.job_title ?? "job"} in a new tab`}
                style={{ flexShrink: 0, color: "var(--text-muted)", lineHeight: 1 }}
              >
                <HatchIcon name="externalLink" size={11} color="var(--text-muted)" />
              </a>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.4 }}>
            {application.job_company ?? "—"} · {application.job_location ?? "—"}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 5 }}>
          <ScorePill score={application.agent_score ?? 0} />
          {application.latest_cv_ats_score != null && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: "var(--success)",
                background: "var(--success-soft)",
                borderRadius: 999,
                padding: "2px 6px",
                whiteSpace: "nowrap",
              }}
            >
              CV ATS {application.latest_cv_ats_score}%
            </span>
          )}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: 10 }}>
        <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{STATUS_LABELS[application.status]}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <select
            aria-label={`Move ${application.job_title ?? "application"} to another stage`}
            value=""
            onChange={(event) => {
              const status = event.target.value as ApplicationStatus;
              if (status) onMove(application, status);
            }}
            style={{
              maxWidth: 94,
              height: 28,
              borderRadius: 7,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--text-dim)",
              fontSize: 10.5,
              padding: "0 5px",
            }}
          >
            <option value="">Move to...</option>
            {moveOptions(application.status).map((status) => (
              <option key={status} value={status}>{STATUS_LABELS[status]}</option>
            ))}
          </select>
          <button
            type="button"
            {...attributes}
            {...listeners}
            disabled={!next}
            aria-label={next ? `Drag ${application.job_title ?? "application"} forward to ${STATUS_LABELS[next]}` : "No further stage available"}
            title={next ? `Drag forward to ${STATUS_LABELS[next]}` : "No further stage available"}
            style={{
              width: 28,
              height: 28,
              borderRadius: 7,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--text-dim)",
              cursor: next ? "grab" : "not-allowed",
              opacity: next ? 1 : 0.45,
              touchAction: "none",
            }}
          >
            ::
          </button>
        </div>
      </div>
    </div>
  );
}

interface KanbanColumnProps {
  stage: StageDefinition;
  applications: ApplicationListItem[];
  onMove: (application: ApplicationListItem, status: ApplicationStatus) => void;
}

function KanbanColumn({ stage, applications, onMove }: KanbanColumnProps) {
  const { isOver, setNodeRef } = useDroppable({ id: stage.key });
  return (
    <section
      ref={setNodeRef}
      data-testid={`col-${stage.key}`}
      aria-label={`${stage.label}, ${applications.length} applications`}
      style={{
        background: isOver ? "var(--surface-2)" : "var(--bg-elevated)",
        border: `1px solid ${isOver ? stage.color : "var(--border)"}`,
        borderRadius: 16,
        padding: 10,
        minWidth: 238,
        width: 238,
        flexShrink: 0,
        transition: "background 0.12s, border-color 0.12s",
      }}
    >
      <div style={{ padding: "4px 6px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <Dot color={stage.color} size={7} />
            <h2 style={{ margin: 0, fontSize: 12.5, fontWeight: 700, color: "var(--text)" }}>{stage.label}</h2>
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)" }}>{applications.length}</span>
        </div>
        <p style={{ margin: "4px 0 0 14px", fontSize: 10.5, color: "var(--text-muted)" }}>{stage.description}</p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minHeight: 90 }}>
        {applications.map((application) => (
          <JobCard key={application.id} application={application} onMove={onMove} />
        ))}
        {applications.length === 0 && (
          <div style={{ border: "1.5px dashed var(--border)", borderRadius: 11, padding: "20px 10px", textAlign: "center", fontSize: 11.5, color: "var(--text-muted)" }}>
            Drop the next-stage card here
          </div>
        )}
      </div>
    </section>
  );
}

function CardPreview({ application }: { application: ApplicationListItem }) {
  return (
    <div style={{ width: 238, background: "var(--surface)", border: "1px solid var(--accent)", borderRadius: 11, padding: 11, boxShadow: "0 12px 32px rgba(0,0,0,0.28)" }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{application.job_title ?? "Untitled Role"}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{application.job_company ?? "—"}</div>
    </div>
  );
}

export function TrackerScreen({ applications, onStatusChange }: TrackerScreenProps) {
  const [items, setItems] = useState(applications);
  const [activeApplication, setActiveApplication] = useState<ApplicationListItem | null>(null);
  const [notice, setNotice] = useState("Drag cards forward, or use each card's Move to menu.");
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const persistStatus = onStatusChange ?? updateApplicationStatus;

  const grouped = useMemo(() => {
    const result: Record<BoardStage, ApplicationListItem[]> = {
      discovered: [],
      preparing: [],
      ready_to_apply: [],
      applied: [],
      interview: [],
      offered: [],
      accepted: [],
    };
    for (const application of items) {
      const stage = STAGE_BY_STATUS[application.status];
      if (stage !== "closed") result[stage].push(application);
    }
    return result;
  }, [items]);

  async function moveApplication(application: ApplicationListItem, status: ApplicationStatus) {
    if (!moveOptions(application.status).includes(status)) {
      setNotice("That move is not available. Applications move forward; use the close actions for rejected or withdrawn roles.");
      return;
    }
    if (!window.confirm(confirmationMessage(application, status))) return;

    const previousItems = items;
    setItems((current) => current.map((item) => item.id === application.id ? { ...item, status } : item));
    setNotice(`Moving ${application.job_title ?? "application"} to ${STATUS_LABELS[status]}...`);
    try {
      await persistStatus(application.id, status);
      setNotice(`${application.job_title ?? "Application"} moved to ${STATUS_LABELS[status]}.`);
    } catch (error) {
      setItems(previousItems);
      setNotice(error instanceof Error ? `Move failed: ${error.message}` : "Move failed. The card was restored.");
    }
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveApplication(items.find((item) => item.id === String(event.active.id)) ?? null);
  }

  function handleDragEnd(event: DragEndEvent) {
    const application = items.find((item) => item.id === String(event.active.id));
    setActiveApplication(null);
    if (!application || !event.over) return;

    const targetStage = event.over.id as BoardStage;
    const targetStatus = stageTargetStatus(targetStage);
    if (targetStatus !== nextStatus(application.status)) {
      setNotice("Only the next stage to the right is available. The card has not moved.");
      return;
    }
    void moveApplication(application, targetStatus);
  }

  return (
    <div>
      <div style={{ padding: "8px 0 14px", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.03em", color: "var(--text)" }}>Tracker</div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>Move applications forward as their real-world status changes</div>
        </div>
        <div aria-live="polite" style={{ maxWidth: 430, textAlign: "right", fontSize: 11.5, color: "var(--text-muted)" }}>{notice}</div>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd} onDragCancel={() => setActiveApplication(null)}>
        <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 18, alignItems: "flex-start", scrollSnapType: "x proximity" }}>
          {STAGES.map((stage) => (
            <KanbanColumn key={stage.key} stage={stage} applications={grouped[stage.key]} onMove={(application, status) => void moveApplication(application, status)} />
          ))}
        </div>
        <DragOverlay>{activeApplication ? <CardPreview application={activeApplication} /> : null}</DragOverlay>
      </DndContext>
    </div>
  );
}
