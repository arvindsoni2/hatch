import { formatDistanceToNow } from "date-fns";
import { GitBranch, StickyNote, Calendar, Bell, Pencil } from "lucide-react";
import type { ActivityLogEntry } from "@/lib/api";

interface ActionConfig {
  icon: React.ReactNode;
  label: string;
  color: string;
}

const ACTION_CONFIG: Record<string, ActionConfig> = {
  status_change: {
    icon: <GitBranch className="h-4 w-4" />,
    label: "Status changed",
    color: "bg-indigo-100 text-indigo-600",
  },
  note_added: {
    icon: <StickyNote className="h-4 w-4" />,
    label: "Note added",
    color: "bg-amber-100 text-amber-600",
  },
  interview_scheduled: {
    icon: <Calendar className="h-4 w-4" />,
    label: "Interview scheduled",
    color: "bg-blue-100 text-blue-600",
  },
  follow_up_created: {
    icon: <Bell className="h-4 w-4" />,
    label: "Follow-up created",
    color: "bg-purple-100 text-purple-600",
  },
  created: {
    icon: <Pencil className="h-4 w-4" />,
    label: "Application created",
    color: "bg-green-100 text-green-600",
  },
  field_updated: {
    icon: <Pencil className="h-4 w-4" />,
    label: "Updated",
    color: "bg-slate-100 text-slate-600",
  },
};

interface ActivityFeedProps {
  activity: ActivityLogEntry[];
}

export function ActivityFeed({ activity }: ActivityFeedProps) {
  if (activity.length === 0) {
    return <p className="text-sm text-slate-400 py-4 text-center">No activity yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {activity.map((entry) => {
        const config: ActionConfig = ACTION_CONFIG[entry.action] ?? {
          icon: <Pencil className="h-4 w-4" />,
          label: entry.action.replace(/_/g, " "),
          color: "bg-slate-100 text-slate-600",
        };

        return (
          <div key={entry.id} className="flex gap-3 items-start">
            <div
              className={`shrink-0 h-7 w-7 rounded-full flex items-center justify-center ${config.color}`}
            >
              {config.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm text-slate-700">{config.label}</span>
                {entry.old_value && entry.new_value && (
                  <span className="text-xs text-slate-400">
                    {entry.old_value} →{" "}
                    <strong>{entry.new_value}</strong>
                  </span>
                )}
              </div>
              {entry.detail && (
                <p className="text-xs text-slate-500 line-clamp-2 mt-0.5">{entry.detail}</p>
              )}
              <p className="text-xs text-slate-400 mt-0.5">
                {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
