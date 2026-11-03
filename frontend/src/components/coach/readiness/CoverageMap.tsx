import Link from "next/link";
import type { CompetencyCoverage, CoverageMap as CoverageMapData } from "@/lib/coachReadinessApi";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Icon } from "@/components/ui/icon";

const STATUS_COPY: Record<
  CompetencyCoverage["status"],
  { label: string; tone: "success" | "warning" | "neutral"; icon: string }
> = {
  covered: { label: "Ready story", tone: "success", icon: "checkCircle" },
  thin: { label: "Could be stronger", tone: "warning", icon: "target" },
  gap: { label: "No story yet", tone: "neutral", icon: "target" },
};

function storyHref(item: CompetencyCoverage): string | null {
  if (item.status === "gap" || item.stories.length === 0) {
    return `/coach/stories/new?competency=${encodeURIComponent(item.competency)}`;
  }
  return `/coach/stories/${item.stories[0].story_id}`;
}

function actionLabel(item: CompetencyCoverage): string {
  if (item.status === "covered") return "Use this story";
  if (item.status === "thin") return "Strengthen this story";
  return "Draft a story";
}

export interface CoverageMapProps {
  coverage: CoverageMapData;
}

export function CoverageMap({ coverage }: CoverageMapProps) {
  return (
    <SectionCard
      title="Story coverage"
      description={`${coverage.covered_count} ready · ${coverage.thin_count} could be stronger · ${coverage.gap_count} with no story yet`}
    >
      {coverage.competencies.length === 0 ? (
        <p className="text-sm text-[var(--text-dim)]">
          No competencies found for this application yet.
        </p>
      ) : (
        <ul className="space-y-3">
          {coverage.competencies.map((item) => {
            const status = STATUS_COPY[item.status];
            const href = storyHref(item);
            return (
              <li
                key={item.competency}
                className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={status.tone} icon={<Icon name={status.icon} size={14} />}>
                    {status.label}
                  </StatusBadge>
                  <span className="text-sm font-medium text-[var(--text)]">{item.competency}</span>
                </div>
                {item.stories.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-sm text-[var(--text-dim)]">
                    {item.stories.map((story) => (
                      <li key={story.story_id}>
                        {story.title}
                        {story.has_metric ? " · has a metric" : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {href ? (
                  <Link
                    href={href}
                    className="mt-2 inline-flex min-h-9 items-center text-sm font-medium text-[var(--accent)] underline-offset-4 hover:underline"
                  >
                    {actionLabel(item)}
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
