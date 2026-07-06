"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  getStory, updateStory, deleteStory, rateStory,
  StoryRead, StoryUpdate,
} from "@/lib/api";
import { StoryEditor } from "@/components/coach/StoryEditor";
import {
  ArrowLeft, BookOpen, Edit2, Trash2, Star, TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const STRENGTH_COLOR = (s: number) =>
  s >= 8 ? "text-emerald-600" : s >= 5 ? "text-amber-600" : "text-slate-400";

function StarRating({ rating, onRate }: { rating: number; onRate: (r: number) => void }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <button key={i} onClick={() => onRate(i)}>
          <Star
            className={`h-5 w-5 transition-colors ${
              i <= rating ? "text-amber-400 fill-amber-400" : "text-slate-300 hover:text-amber-400"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

function STARSection({ label, content }: { label: string; content: string | null }) {
  if (!content) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-600 mb-1">{label}</h3>
      <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{content}</p>
    </div>
  );
}

export default function StoryDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [story, setStory] = useState<StoryRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (params.id) {
      getStory(params.id)
        .then(setStory)
        .catch(() => setError("Story not found"))
        .finally(() => setLoading(false));
    }
  }, [params.id]);

  const handleUpdate = async (data: StoryUpdate) => {
    if (!story) return;
    setSaving(true);
    try {
      const updated = await updateStory(story.id, data);
      setStory(updated);
      setEditing(false);
    } catch {
      setError("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!story || !confirm("Delete this story? This cannot be undone.")) return;
    await deleteStory(story.id);
    router.push("/coach/stories");
  };

  const handleRate = async (r: number) => {
    if (!story) return;
    const updated = await rateStory(story.id, r);
    setStory(updated);
  };

  if (loading) {
    return <div className="flex justify-center py-20 text-slate-400 text-sm">Loading…</div>;
  }
  if (error || !story) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-red-600">{error || "Story not found"}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => router.back()} className="text-slate-400 hover:text-slate-700 transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <BookOpen className="h-5 w-5 text-indigo-600 shrink-0" />
          <div>
            <h1 className="text-xl font-bold text-slate-900">{story.title}</h1>
            {story.summary && <p className="text-sm text-slate-500 mt-0.5">{story.summary}</p>}
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          {!editing && (
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)} className="gap-1.5 text-slate-500 hover:text-slate-700">
                <Edit2 className="h-3.5 w-3.5" />
                Edit
              </Button>
              <Button variant="ghost" size="sm" onClick={handleDelete} className="gap-1.5 text-red-500 hover:text-red-700">
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {!editing && (
        <div className="mb-6 flex flex-wrap items-center gap-6 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4">
          <div className="flex flex-col items-center">
            <span className={`text-2xl font-bold ${STRENGTH_COLOR(story.strength_score)}`}>
              {story.strength_score.toFixed(1)}
            </span>
            <span className="text-xs text-slate-500">Strength</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-2xl font-bold text-slate-800">{story.times_used}</span>
            <span className="text-xs text-slate-500">Uses</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-2xl font-bold text-slate-800">v{story.version}</span>
            <span className="text-xs text-slate-500">Version</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Your rating</span>
            <StarRating rating={story.manual_rating ?? 0} onRate={handleRate} />
          </div>
        </div>
      )}

      {/* Edit mode */}
      {editing ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <StoryEditor
            initialData={story}
            onSave={handleUpdate}
            onCancel={() => setEditing(false)}
            saving={saving}
          />
        </div>
      ) : (
        <div className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <STARSection label="Situation" content={story.situation} />
          <STARSection label="Task" content={story.task} />
          <STARSection label="Action" content={story.action} />
          <STARSection label="Result" content={story.result} />
          <STARSection label="Reflection" content={story.reflection} />

          {/* Metadata */}
          <div className="border-t border-slate-200 pt-4 space-y-3">
            {(story.tags ?? []).length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1.5">Tags</p>
                <div className="flex flex-wrap gap-1.5">
                  {story.tags!.map((t) => (
                    <span key={t} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">{t}</span>
                  ))}
                </div>
              </div>
            )}
            {(story.skills ?? []).length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1.5">Skills</p>
                <div className="flex flex-wrap gap-1.5">
                  {story.skills!.map((s) => (
                    <span key={s} className="rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-xs text-indigo-700">{s}</span>
                  ))}
                </div>
              </div>
            )}
            {(story.archetype_fit ?? []).length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1.5">Best for</p>
                <div className="flex flex-wrap gap-1.5">
                  {story.archetype_fit!.map((a) => (
                    <span key={a} className="rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs text-emerald-700">{a.replace(/_/g, " ")}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
