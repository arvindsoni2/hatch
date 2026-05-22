"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listStories, StoryListItem } from "@/lib/api";
import { StoryBankGrid } from "@/components/coach/StoryBankGrid";
import { StoryFilters } from "@/components/coach/StoryFilters";
import { BookOpen, Plus } from "lucide-react";
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
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-indigo-400" />
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Story Bank</h1>
            <p className="text-sm text-slate-400">
              {total} canonical STAR {total === 1 ? "story" : "stories"}
            </p>
          </div>
        </div>
        <Button
          onClick={() => router.push("/coach/stories/new")}
          className="gap-2 bg-indigo-600 hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4" />
          Add Story
        </Button>
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
    </main>
  );
}
