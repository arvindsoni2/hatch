"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createStory, StoryCreate } from "@/lib/api";
import { StoryEditor } from "@/components/coach/StoryEditor";
import { ArrowLeft, BookOpen } from "lucide-react";

export default function NewStoryPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async (data: StoryCreate) => {
    setSaving(true);
    setError("");
    try {
      const story = await createStory(data);
      router.push(`/coach/stories/${story.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save story");
      setSaving(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center gap-3">
        <button onClick={() => router.back()} className="text-slate-400 hover:text-slate-200">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <BookOpen className="h-5 w-5 text-indigo-400" />
        <h1 className="text-xl font-bold text-slate-100">New Story</h1>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-6">
        <StoryEditor
          onSave={handleSave}
          onCancel={() => router.back()}
          saving={saving}
        />
      </div>
    </main>
  );
}
