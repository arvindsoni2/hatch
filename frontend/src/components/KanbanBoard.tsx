"use client";

import { useState, useCallback } from "react";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { KanbanCard } from "./KanbanCard";
import type { ApplicationListItem, ApplicationStatus, KanbanStats } from "@/lib/api";

const ACTIVE_COLUMNS: ApplicationStatus[] = [
  "discovered",
  "shortlisted",
  "applied",
  "interview",
  "offered",
];

const ARCHIVE_STATUSES: ApplicationStatus[] = [
  "accepted",
  "rejected",
  "withdrawn",
  "declined",
];

const COLUMN_LABELS: Record<string, string> = {
  discovered: "Discovered",
  shortlisted: "Shortlisted",
  applied: "Applied",
  interview: "Interview",
  offered: "Offered",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  declined: "Declined",
};

const COLUMN_COLORS: Record<string, string> = {
  discovered: "border-slate-300",
  shortlisted: "border-purple-300",
  applied: "border-blue-300",
  interview: "border-amber-300",
  offered: "border-emerald-300",
  accepted: "border-green-300",
  rejected: "border-red-300",
  withdrawn: "border-gray-300",
  declined: "border-orange-300",
};

// ─── Sortable Card Wrapper ───────────────────────────────────────

interface SortableCardProps {
  application: ApplicationListItem;
  onCardClick: (id: string) => void;
  isOverdue?: boolean;
}

function SortableCard({ application, onCardClick, isOverdue }: SortableCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: application.id, data: { status: application.status } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <KanbanCard
        application={application}
        isDragging={isDragging}
        isOverdue={isOverdue}
        onClick={() => onCardClick(application.id)}
      />
    </div>
  );
}

// ─── Column Component ────────────────────────────────────────────

interface ColumnProps {
  status: ApplicationStatus;
  items: ApplicationListItem[];
  onCardClick: (id: string) => void;
  overdueIds?: Set<string>;
}

function KanbanColumn({ status, items, onCardClick, overdueIds }: ColumnProps) {
  return (
    <div className={cn("flex flex-col min-w-[280px] w-[280px] [scroll-snap-align:start] flex-shrink-0 rounded-xl border-t-4 bg-slate-50", COLUMN_COLORS[status])}>
      <div className="px-3 py-2 flex items-center justify-between border-b border-slate-200">
        <span className="text-sm font-semibold text-slate-700">{COLUMN_LABELS[status]}</span>
        <span className="text-xs bg-white border border-slate-200 rounded-full px-2 py-0.5 text-slate-500">
          {items.length}
        </span>
      </div>
      <SortableContext items={items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
        <div className="flex flex-col gap-2 p-2 min-h-[100px]" data-column-id={status}>
          {items.map((app) => (
            <SortableCard key={app.id} application={app} onCardClick={onCardClick} isOverdue={overdueIds?.has(app.id)} />
          ))}
          {items.length === 0 && (
            <div className="text-center text-xs text-slate-400 py-6 border-2 border-dashed border-slate-200 rounded-lg">
              Drop here
            </div>
          )}
        </div>
      </SortableContext>
    </div>
  );
}

// ─── Stats Ribbon ────────────────────────────────────────────────

function StatsRibbon({ stats }: { stats: KanbanStats }) {
  return (
    <div className="flex flex-wrap gap-3 mb-4">
      {[
        { label: "Active Applications", value: stats.active_count, color: "text-indigo-600" },
        { label: "Applied", value: stats.applied_count, color: "text-blue-600" },
        { label: "Response Rate", value: `${stats.response_rate.toFixed(1)}%`, color: "text-emerald-600" },
        {
          label: "Overdue Follow-ups",
          value: stats.overdue_count,
          color: stats.overdue_count > 0 ? "text-red-600" : "text-slate-500",
        },
      ].map(({ label, value, color }) => (
        <div key={label} className="bg-white border border-slate-200 rounded-lg px-4 py-2 text-center">
          <div className={cn("text-xl font-bold", color)}>{value}</div>
          <div className="text-xs text-slate-500">{label}</div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Board ──────────────────────────────────────────────────

interface KanbanBoardProps {
  initialData: Record<string, ApplicationListItem[]>;
  stats: KanbanStats;
  overdueIds?: Set<string>;
  onStatusChange: (id: string, newStatus: ApplicationStatus) => Promise<void>;
  onCardClick: (id: string) => void;
}

export function KanbanBoard({ initialData, stats, overdueIds, onStatusChange, onCardClick }: KanbanBoardProps) {
  const [columns, setColumns] = useState<Record<string, ApplicationListItem[]>>(initialData);
  const [activeItem, setActiveItem] = useState<ApplicationListItem | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const allItems = Object.values(columns).flat();
      const item = allItems.find((i) => i.id === event.active.id);
      setActiveItem(item ?? null);
    },
    [columns],
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      setActiveItem(null);
      const { active, over } = event;
      if (!over) return;

      const allItems = Object.values(columns).flat();
      const overId = String(over.id);

      // Determine target column
      let targetStatus: ApplicationStatus | null = null;
      if (
        (ACTIVE_COLUMNS as string[]).includes(overId) ||
        (ARCHIVE_STATUSES as string[]).includes(overId)
      ) {
        targetStatus = overId as ApplicationStatus;
      } else {
        const overItem = allItems.find((i) => i.id === overId);
        if (overItem) targetStatus = overItem.status;
      }

      if (!targetStatus) return;

      const draggedItem = allItems.find((i) => i.id === String(active.id));
      if (!draggedItem || draggedItem.status === targetStatus) return;

      // Optimistic update
      setColumns((prev) => {
        const next = { ...prev };
        next[draggedItem.status] = (next[draggedItem.status] ?? []).filter(
          (i) => i.id !== draggedItem.id,
        );
        next[targetStatus!] = [
          { ...draggedItem, status: targetStatus! },
          ...(next[targetStatus!] ?? []),
        ];
        return next;
      });

      try {
        await onStatusChange(draggedItem.id, targetStatus);
      } catch {
        // Revert on error
        setColumns(initialData);
      }
    },
    [columns, initialData, onStatusChange],
  );

  const archiveItems = ARCHIVE_STATUSES.flatMap((s) => columns[s] ?? []);

  return (
    <div>
      <StatsRibbon stats={stats} />

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        {/* Active columns — horizontal scroll with snap on mobile */}
        <div className="flex gap-3 overflow-x-auto pb-4 [scroll-snap-type:x_mandatory] [-webkit-overflow-scrolling:touch]">
          {ACTIVE_COLUMNS.map((status) => (
            <KanbanColumn
              key={status}
              status={status}
              items={columns[status] ?? []}
              onCardClick={onCardClick}
              overdueIds={overdueIds}
            />
          ))}
        </div>

        <DragOverlay>
          {activeItem && <KanbanCard application={activeItem} isDragging />}
        </DragOverlay>
      </DndContext>

      {/* Archive accordion */}
      <div className="mt-4 border border-slate-200 rounded-lg overflow-hidden">
        <button
          onClick={() => setArchiveOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-600"
        >
          <span>Archive ({archiveItems.length})</span>
          {archiveOpen ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>
        {archiveOpen && (
          <div className="flex gap-4 p-4 overflow-x-auto">
            {ARCHIVE_STATUSES.map((status) => (
              <KanbanColumn
                key={status}
                status={status}
                items={columns[status] ?? []}
                onCardClick={onCardClick}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
