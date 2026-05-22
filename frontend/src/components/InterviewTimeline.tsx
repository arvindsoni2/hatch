import { Phone, Code2, Users, Presentation, CheckCircle2, Clock } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import type { InterviewRound } from "@/lib/api";

const TYPE_ICONS: Record<string, React.ReactNode> = {
  phone_screen: <Phone className="h-4 w-4" />,
  technical: <Code2 className="h-4 w-4" />,
  behavioural: <Users className="h-4 w-4" />,
  panel: <Users className="h-4 w-4" />,
  presentation: <Presentation className="h-4 w-4" />,
  culture_fit: <Users className="h-4 w-4" />,
  final: <CheckCircle2 className="h-4 w-4" />,
  assessment: <Clock className="h-4 w-4" />,
};

const STATUS_STYLES: Record<string, string> = {
  scheduled: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-gray-100 text-gray-500",
  rescheduled: "bg-amber-100 text-amber-700",
};

interface InterviewTimelineProps {
  interviews: InterviewRound[];
}

export function InterviewTimeline({ interviews }: InterviewTimelineProps) {
  if (interviews.length === 0) {
    return (
      <p className="text-sm text-slate-400 py-4 text-center">
        No interview rounds scheduled yet.
      </p>
    );
  }

  const sorted = [...interviews].sort((a, b) => a.round_number - b.round_number);

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-4 top-4 bottom-4 w-0.5 bg-slate-200" />

      <div className="flex flex-col gap-4">
        {sorted.map((round) => (
          <div key={round.id} className="flex gap-4 relative">
            {/* Circle icon */}
            <div
              className={cn(
                "h-8 w-8 rounded-full flex items-center justify-center shrink-0 z-10 border-2 border-white",
                round.status === "completed"
                  ? "bg-green-100 text-green-600"
                  : round.status === "cancelled"
                    ? "bg-gray-100 text-gray-400"
                    : "bg-blue-100 text-blue-600",
              )}
            >
              {TYPE_ICONS[round.type] ?? <Clock className="h-4 w-4" />}
            </div>

            <div className="flex-1 bg-white border border-slate-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-slate-800">
                  Round {round.round_number} — {round.type.replace(/_/g, " ")}
                </span>
                <span
                  className={cn(
                    "text-xs px-2 py-0.5 rounded-full font-medium",
                    STATUS_STYLES[round.status] ?? "bg-slate-100 text-slate-500",
                  )}
                >
                  {round.status}
                </span>
              </div>

              {round.scheduled_at && (
                <p className="text-xs text-slate-500 mb-1">
                  {format(new Date(round.scheduled_at), "EEE d MMM yyyy 'at' HH:mm")}
                  {round.duration_minutes != null && ` · ${round.duration_minutes} min`}
                  {round.location && ` · ${round.location}`}
                </p>
              )}

              {round.interviewer_name && (
                <p className="text-xs text-slate-500 mb-1">
                  Interviewer: {round.interviewer_name}
                </p>
              )}

              {round.feedback && (
                <div className="mt-2 text-xs text-slate-600 bg-slate-50 rounded p-2">
                  <strong>Feedback:</strong> {round.feedback}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
