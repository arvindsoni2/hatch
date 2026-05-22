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
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
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
        <h2 className="text-lg font-semibold text-slate-800">
          {format(currentMonth, "MMMM yyyy")}
        </h2>
        <div className="flex gap-1">
          <button
            onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => setCurrentMonth(new Date())}
            className="px-3 py-1.5 text-sm rounded-lg hover:bg-slate-100 transition-colors text-slate-600"
          >
            Today
          </button>
          <button
            onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
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
            className="text-xs font-medium text-slate-400 text-center py-1"
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
                "relative h-10 rounded-lg flex flex-col items-center justify-center text-sm transition-colors",
                isToday(day) && "font-bold text-indigo-600",
                !isSameMonth(day, currentMonth) && "text-slate-300",
                isSelected ? "bg-indigo-500 text-white" : "hover:bg-slate-100",
                hasEvents && !isSelected && "bg-slate-50",
              )}
            >
              {format(day, "d")}
              {hasEvents && (
                <div className="absolute bottom-1 flex gap-0.5">
                  {dayInterviews.length > 0 && (
                    <div
                      className={cn(
                        "h-1 w-1 rounded-full",
                        isSelected ? "bg-white" : "bg-blue-500",
                      )}
                    />
                  )}
                  {dayFollowUps.length > 0 && (
                    <div
                      className={cn(
                        "h-1 w-1 rounded-full",
                        isSelected
                          ? "bg-white"
                          : dayFollowUps.some((f) => !f.completed)
                            ? "bg-amber-400"
                            : "bg-green-400",
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
          <div className="mt-4 border-t border-slate-200 pt-4">
            <h3 className="text-sm font-medium text-slate-700 mb-3">
              {format(selectedDay, "EEEE d MMMM")}
            </h3>
            {selectedInterviews.map((i) => (
              <div key={i.id} className="flex items-center gap-2 text-sm py-1">
                <div className="h-2 w-2 rounded-full bg-blue-500 shrink-0" />
                <span className="text-slate-700">
                  {i.type.replace(/_/g, " ")} interview
                </span>
                {i.scheduled_at && (
                  <span className="text-slate-400 ml-auto">
                    {format(new Date(i.scheduled_at), "HH:mm")}
                  </span>
                )}
              </div>
            ))}
            {selectedFollowUps.map((f) => (
              <div key={f.id} className="flex items-center gap-2 text-sm py-1">
                <div
                  className={cn(
                    "h-2 w-2 rounded-full shrink-0",
                    f.completed ? "bg-green-400" : "bg-amber-400",
                  )}
                />
                <span
                  className={cn(
                    "text-slate-700",
                    f.completed && "line-through text-slate-400",
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
