"use client";

const ARCHETYPES = [
  "solutions_architect",
  "ai_engineer",
  "ai_product_manager",
  "ai_project_manager",
  "product_owner",
  "business_analyst",
  "project_manager",
  "senior_project_manager",
  "scrum_master",
];

interface Props {
  archetype: string;
  tag: string;
  minStrength: string;
  onArchetypeChange: (v: string) => void;
  onTagChange: (v: string) => void;
  onMinStrengthChange: (v: string) => void;
}

export function StoryFilters({
  archetype,
  tag,
  minStrength,
  onArchetypeChange,
  onTagChange,
  onMinStrengthChange,
}: Props) {
  return (
    <div className="flex flex-wrap gap-3">
      <select
        value={archetype}
        onChange={(e) => onArchetypeChange(e.target.value)}
        className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
      >
        <option value="">All archetypes</option>
        {ARCHETYPES.map((a) => (
          <option key={a} value={a}>
            {a.replace(/_/g, " ")}
          </option>
        ))}
      </select>

      <input
        type="text"
        placeholder="Filter by tag..."
        value={tag}
        onChange={(e) => onTagChange(e.target.value)}
        className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none w-36"
      />

      <select
        value={minStrength}
        onChange={(e) => onMinStrengthChange(e.target.value)}
        className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
      >
        <option value="">Any strength</option>
        <option value="7">Strong (7+)</option>
        <option value="5">Average (5+)</option>
        <option value="3">Weak (3+)</option>
      </select>
    </div>
  );
}
