"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { listStories, StoryListItem } from "@/lib/api";
import { StoryBankGrid } from "@/components/coach/StoryBankGrid";
import { StoryFilters } from "@/components/coach/StoryFilters";
import { Brain, BookOpen, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function StoryBankPage() {
  const router = useRouter();
  const [stories, setStories] = useState<StoryListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [archetype, setArchetype] = useState("");
  const [tag, setTag] = useState("");
  const [minStrength, setMinStrength] = useState("");

  const load = () => {
    setLoading(true);
    listStories({
      archetype: archetype || undefined,
      tag: tag || undefined,
      min_strength: minStrength ? Number(minStrength) : undefined,
      limit: 100,
    })
      .then((r) => {
        setStories(r.items);
        setTotal(r.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [archetype, tag, minStrength]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-indigo-600" />
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Story Bank</h1>
            <p className="text-sm text-slate-500">
              {total} canonical STAR {total === 1 ? "story" : "stories"}
            </p>
          </div>
        </div>
        <Button
          onClick={() => router.push("/coach/stories/new")}
          className="gap-2 bg-indigo-600 hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" />
          Add Story
        </Button>
      </div>

      {/* Sub-navigation */}
      <div className="mb-6 flex gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1">
        <Link
          href="/coach"
          className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium text-slate-500 hover:bg-white hover:text-slate-900 transition-colors"
        >
          <Brain className="h-3.5 w-3.5" /> Sessions
        </Link>
        <span className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white">
          <BookOpen className="h-3.5 w-3.5" /> Story Bank
        </span>
      </div>

      <div className="mb-5">
        <StoryFilters
          archetype={archetype}
          tag={tag}
          minStrength={minStrength}
          onArchetypeChange={setArchetype}
          onTagChange={setTag}
          onMinStrengthChange={setMinStrength}
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-20 text-slate-500 text-sm">Loading stories…</div>
      ) : (
        <StoryBankGrid stories={stories} onSelect={(id) => router.push(`/coach/stories/${id}`)} />
      )}
    </div>
  );
}
