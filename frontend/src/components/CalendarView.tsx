"use client";

import { useState } from "react";
import {
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  getDay,
  isSameDay,
  isSameMonth,
  format,
  addMonths,
  subMonths,
  isToday,
} from "date-fns";
import { ChevronLeft, ChevronRight, CalendarPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import { downloadInterviewIcs } from "@/lib/api";
import type { InterviewRound, FollowUp } from "@/lib/api";

interface CalendarViewProps {
  interviews: InterviewRound[];
  followUps: FollowUp[];
}

export function CalendarView({ interviews, followUps }: CalendarViewProps) {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDay, setSelectedDay] = useState<Date | null>(null);

  const days = eachDayOfInterval({
    start: startOfMonth(currentMonth),
    end: endOfMonth(currentMonth),
  });

  // Pad start: Monday-first (Mon=0, Sun=6)
  const firstDayOfWeek = (getDay(days[0]) + 6) % 7;
  const paddingDays = Array.from({ length: firstDayOfWeek });

  const getInterviewsForDay = (day: Date) =>
    interviews.filter(
      (i) => i.scheduled_at && isSameDay(new Date(i.scheduled_at), day),
    );

  const getFollowUpsForDay = (day: Date) =>
    followUps.filter((f) => isSameDay(new Date(f.due_date), day));

  const selectedInterviews = selectedDay ? getInterviewsForDay(selectedDay) : [];
  const selectedFollowUps = selectedDay ? getFollowUpsForDay(selectedDay) : [];

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">
          {format(currentMonth, "MMMM yyyy")}
        </h2>
        <div className="flex gap-1">
          <button
            onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
            className="rounded-lg p-2 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => setCurrentMonth(new Date())}
            className="rounded-lg px-3 py-1.5 text-sm text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            Today
          </button>
          <button
            onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
            className="rounded-lg p-2 text-[var(--text-dim)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Day labels */}
      <div className="grid grid-cols-7 mb-2">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div
            key={d}
            className="py-1 text-center text-xs font-medium text-[var(--text-muted)]"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-1">
        {paddingDays.map((_, i) => (
          <div key={`pad-${i}`} />
        ))}
        {days.map((day) => {
          const dayInterviews = getInterviewsForDay(day);
          const dayFollowUps = getFollowUpsForDay(day);
          const hasEvents = dayInterviews.length > 0 || dayFollowUps.length > 0;
          const isSelected = selectedDay !== null && isSameDay(day, selectedDay);

          return (
            <button
              key={day.toISOString()}
              onClick={() =>
                setSelectedDay(
                  selectedDay !== null && isSameDay(day, selectedDay) ? null : day,
                )
              }
              className={cn(
                "relative flex h-10 flex-col items-center justify-center rounded-lg text-sm text-[var(--text)] transition-colors",
                isToday(day) && "font-bold text-[var(--accent)]",
                !isSameMonth(day, currentMonth) && "text-[var(--text-muted)]",
                isSelected ? "bg-[var(--accent)] text-[var(--on-accent)]" : "hover:bg-[var(--surface-2)]",
                hasEvents && !isSelected && "bg-[var(--surface-2)]",
              )}
            >
              {format(day, "d")}
              {hasEvents && (
                <div className="absolute bottom-1 flex gap-0.5">
                  {dayInterviews.length > 0 && (
                    <div
                      className={cn(
                        "h-1 w-1 rounded-full",
                        isSelected ? "bg-[var(--on-accent)]" : "bg-[var(--accent)]",
                      )}
                    />
                  )}
                  {dayFollowUps.length > 0 && (
                    <div
                      className={cn(
                        "h-1 w-1 rounded-full",
                        isSelected
                          ? "bg-[var(--on-accent)]"
                          : dayFollowUps.some((f) => !f.completed)
                            ? "bg-[var(--warning)]"
                            : "bg-[var(--success)]",
                      )}
                    />
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Selected day detail */}
      {selectedDay !== null &&
        (selectedInterviews.length > 0 || selectedFollowUps.length > 0) && (
          <div className="mt-4 border-t border-[var(--border)] pt-4">
            <h3 className="mb-3 text-sm font-medium text-[var(--text)]">
              {format(selectedDay, "EEEE d MMMM")}
            </h3>
            {selectedInterviews.map((i) => (
              <div key={i.id} className="flex items-center gap-2 text-sm py-1">
                <div className="h-2 w-2 shrink-0 rounded-full bg-[var(--accent)]" />
                <span className="text-[var(--text)]">
                  {i.type.replace(/_/g, " ")} interview
                </span>
                {i.scheduled_at && (
                  <span className="text-[var(--text-muted)]">
                    {format(new Date(i.scheduled_at), "HH:mm")}
                  </span>
                )}
                <button
                  onClick={() => void downloadInterviewIcs(i.id)}
                  title="Export to calendar"
                  className="ml-auto text-[var(--accent)] hover:opacity-80"
                >
                  <CalendarPlus className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {selectedFollowUps.map((f) => (
              <div key={f.id} className="flex items-center gap-2 text-sm py-1">
                <div
                  className={cn(
                    "h-2 w-2 shrink-0 rounded-full",
                    f.completed ? "bg-[var(--success)]" : "bg-[var(--warning)]",
                  )}
                />
                <span
                  className={cn(
                    "text-[var(--text)]",
                    f.completed && "line-through text-[var(--text-muted)]",
                  )}
                >
                  Follow-up: {f.type.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}
