"use client";

import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import type { FocusArea } from "@/lib/coachReadinessApi";

function groupLabel(area: FocusArea): string {
  if (!area.group) return "Any role";
  return `${area.group.role_family} · ${area.group.interview_type.replaceAll("_", " ")}`;
}

export function FocusAreas({
  areas,
  activeCount,
  onAdd,
  onMarkAchieved,
  onStatusChange,
  onEdit,
}: {
  areas: FocusArea[];
  activeCount: number;
  onAdd: () => void;
  onMarkAchieved: (area: FocusArea) => void;
  onStatusChange: (area: FocusArea, status: FocusArea["status"]) => void;
  onEdit: (area: FocusArea) => void;
}) {
  return (
    <SectionCard
      title="Focus areas"
      description={`${activeCount} of 3 in use`}
      actions={
        <Button type="button" variant="outline" size="sm" onClick={onAdd}>
          Add
        </Button>
      }
    >
      {areas.length === 0 ? (
        <p className="text-sm text-[var(--text-dim)]">
          Pick up to three things to work on. Hatch suggests them from your patterns.
        </p>
      ) : (
        <div className="space-y-3">
          {areas.map((area) => (
            <article
              key={area.id}
              className="rounded-[var(--radius-card)] bg-[var(--surface-2)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-[var(--text)]">{area.title}</h3>
                  <p className="mt-1 text-xs text-[var(--text-dim)]">
                    {area.dimension.replaceAll("_", " ")} · {groupLabel(area)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  {area.status === "active" ? (
                    <>
                      <Button type="button" variant="outline" size="sm" onClick={() => onStatusChange(area, "paused")}>
                        Pause
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={() => onStatusChange(area, "archived")}>
                        Archive
                      </Button>
                    </>
                  ) : null}
                  {area.status === "paused" ? (
                    <>
                      <Button type="button" variant="outline" size="sm" onClick={() => onStatusChange(area, "active")}>
                        Resume
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={() => onStatusChange(area, "archived")}>
                        Archive
                      </Button>
                    </>
                  ) : null}
                  {area.status === "achieved" ? (
                    <Button type="button" variant="outline" size="sm" onClick={() => onStatusChange(area, "active")}>
                      Reopen
                    </Button>
                  ) : null}
                  <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(area)}>
                    Edit
                  </Button>
                </div>
              </div>
              <ul className="mt-3 space-y-2">
                {area.criteria.map((criterion) => {
                  const percent = criterion.target
                    ? Math.min(100, Math.round((criterion.completed / criterion.target) * 100))
                    : 0;
                  return (
                    <li key={`${area.id}-${criterion.kind}`} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-[var(--text-dim)]">{criterion.label}</span>
                        <span className="font-mono text-[var(--text)]">
                          {criterion.completed} of {criterion.target}
                        </span>
                      </div>
                      <div
                        className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]"
                        role="progressbar"
                        aria-label={criterion.label}
                        aria-valuemin={0}
                        aria-valuemax={criterion.target}
                        aria-valuenow={criterion.completed}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${percent}%`,
                            backgroundColor: criterion.status === "met"
                              ? "var(--success)"
                              : "var(--accent)",
                          }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
              {area.every_criterion_met && area.status === "active" ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm text-[var(--text-dim)]">Every criterion is met.</p>
                  <Button type="button" variant="success" size="sm" onClick={() => onMarkAchieved(area)}>
                    Mark achieved
                  </Button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
