"use client";

import { useState } from "react";
import { StoryCreate, StoryRead } from "@/lib/api";
import { Plus, X, Save, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const ARCHETYPES = [
  "solutions_architect", "ai_engineer", "ai_product_manager", "ai_project_manager",
  "product_owner", "business_analyst", "project_manager", "senior_project_manager", "scrum_master",
];

interface Props {
  initialData?: Partial<StoryRead>;
  onSave: (data: StoryCreate) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}

function TagInput({ label, values, onChange }: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("");

  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) {
      onChange([...values, v]);
      setInput("");
    }
  };

  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map((v) => (
          <span key={v} className="flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">
            {v}
            <button onClick={() => onChange(values.filter((x) => x !== v))} className="hover:text-red-500">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder="Type and press Enter"
          className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button onClick={add} className="rounded-md border border-slate-300 bg-white px-2 hover:bg-slate-50 transition-colors">
          <Plus className="h-4 w-4 text-slate-500" />
        </button>
      </div>
    </div>
  );
}

function Textarea({ label, value, onChange, placeholder, rows = 4 }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <textarea
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
      />
    </div>
  );
}

export function StoryEditor({ initialData, onSave, onCancel, saving }: Props) {
  const [title, setTitle] = useState(initialData?.title ?? "");
  const [summary, setSummary] = useState(initialData?.summary ?? "");
  const [situation, setSituation] = useState(initialData?.situation ?? "");
  const [task, setTask] = useState(initialData?.task ?? "");
  const [action, setAction] = useState(initialData?.action ?? "");
  const [result, setResult] = useState(initialData?.result ?? "");
  const [reflection, setReflection] = useState(initialData?.reflection ?? "");
  const [tags, setTags] = useState<string[]>(initialData?.tags ?? []);
  const [skills, setSkills] = useState<string[]>(initialData?.skills ?? []);
  const [archetypefit, setArchetypeFit] = useState<string[]>(initialData?.archetype_fit ?? []);

  const handleSave = async () => {
    if (!title.trim()) return;
    await onSave({
      title: title.trim(),
      summary: summary.trim() || undefined,
      situation: situation.trim() || undefined,
      task: task.trim() || undefined,
      action: action.trim() || undefined,
      result: result.trim() || undefined,
      reflection: reflection.trim() || undefined,
      tags: tags.length ? tags : undefined,
      skills: skills.length ? skills : undefined,
      archetype_fit: archetypefit.length ? archetypefit : undefined,
    });
  };

  const toggleArchetype = (a: string) => {
    setArchetypeFit((prev) =>
      prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]
    );
  };

  return (
    <div className="space-y-5">
      {/* Title */}
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">Title *</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. £500K Mobile Platform at Northern Powergrid"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      {/* Summary */}
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          One-line summary <span className="text-slate-400 font-normal">(≤200 chars)</span>
        </label>
        <input
          type="text"
          value={summary}
          onChange={(e) => setSummary(e.target.value.slice(0, 200))}
          placeholder="Delivered £500K savings by modernising a legacy mobile platform"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <p className="text-right text-xs text-slate-400 mt-0.5">{summary.length}/200</p>
      </div>

      {/* STAR+R sections */}
      <div className="border-t border-slate-200 pt-4">
        <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-4">STAR + R</p>
        <div className="space-y-4">
          <Textarea label="Situation" value={situation} onChange={setSituation}
            placeholder="What was the context? Timeframe, team size, organisation..." rows={3} />
          <Textarea label="Task" value={task} onChange={setTask}
            placeholder="What were you specifically responsible for?" rows={3} />
          <Textarea label="Action" value={action} onChange={setAction}
            placeholder="What did you do? Be specific about YOUR actions..." rows={5} />
          <Textarea label="Result" value={result} onChange={setResult}
            placeholder="What was the outcome? Quantify where possible (£, %, time)..." rows={3} />
          <Textarea label="Reflection" value={reflection} onChange={setReflection}
            placeholder="What did you learn? What would you do differently?" rows={2} />
        </div>
      </div>

      {/* Classification */}
      <div className="border-t border-slate-200 pt-4">
        <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-4">Classification</p>
        <div className="space-y-4">
          <TagInput label="Tags (themes)" values={tags} onChange={setTags} />
          <TagInput label="Skills demonstrated" values={skills} onChange={setSkills} />

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-2">Archetype fit</label>
            <div className="flex flex-wrap gap-2">
              {ARCHETYPES.map((a) => (
                <button
                  key={a}
                  onClick={() => toggleArchetype(a)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    archetypefit.includes(a)
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {a.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
        <Button variant="ghost" onClick={onCancel} disabled={saving} className="text-slate-500 hover:text-slate-700">
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          disabled={!title.trim() || saving}
          className="gap-2 bg-indigo-600 hover:bg-indigo-700"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving…" : "Save Story"}
        </Button>
      </div>
    </div>
  );
}
