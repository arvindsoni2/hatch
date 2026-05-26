"use client";

import { StoryListItem } from "@/lib/api";
import { BookOpen, Star, TrendingUp, Tag } from "lucide-react";

interface Props {
  story: StoryListItem;
  onClick?: () => void;
}

const STRENGTH_COLOR = (score: number) =>
  score >= 8 ? "text-emerald-600" : score >= 5 ? "text-amber-600" : "text-slate-400";

export function StoryCard({ story, onClick }: Props) {
  const stars = story.manual_rating ?? 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl border border-slate-200 bg-white p-4 hover:border-indigo-300 hover:shadow-md transition-all shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-900 truncate text-sm leading-snug">
            {story.title}
          </h3>
          {story.summary && (
            <p className="mt-1 text-xs text-slate-500 line-clamp-2">{story.summary}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`text-lg font-bold ${STRENGTH_COLOR(story.strength_score)}`}>
            {story.strength_score.toFixed(1)}
          </span>
          <div className="flex">
            {[1, 2, 3, 4, 5].map((i) => (
              <Star
                key={i}
                className={`h-3 w-3 ${i <= stars ? "text-amber-400 fill-amber-400" : "text-slate-300"}`}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {(story.tags ?? []).slice(0, 4).map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
          >
            <Tag className="h-2.5 w-2.5" />
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <TrendingUp className="h-3 w-3" />
          {story.times_used} uses
        </span>
        <span className="flex items-center gap-1">
          <BookOpen className="h-3 w-3" />
          v{story.version}
        </span>
        {(story.archetype_fit ?? []).length > 0 && (
          <span className="text-indigo-600">{story.archetype_fit![0].replace(/_/g, " ")}</span>
        )}
      </div>
    </button>
  );
}
