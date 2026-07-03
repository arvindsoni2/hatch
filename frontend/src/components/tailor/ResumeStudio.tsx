"use client";

import type { JDAnalysisResponse, ResumeDesignSettings, ResumeTemplateResponse } from "@/lib/api";

interface Props {
  data?: ResumeTemplateResponse;
  value: ResumeDesignSettings;
  analysis: JDAnalysisResponse | null;
  generated: boolean;
  onChange: (value: ResumeDesignSettings) => void;
}

const labels: Record<string, string> = {
  one_page: "1 page", two_page: "2 pages", auto: "Auto",
  standard: "Balanced", skills_first: "Skills-first", project_led: "Project-led",
  leadership_first: "Leadership-first", career_switcher: "Career-switcher",
};

export function ResumeStudio({ data, value, analysis, generated, onChange }: Props) {
  const template = data?.templates.find((item) => item.id === value.template_id);
  const set = (key: keyof ResumeDesignSettings, next: string) =>
    onChange({ ...value, [key]: next });
  const controls: Array<[keyof ResumeDesignSettings, string, string[]]> = [
    ["page_target", "Page target", data?.controls.page_targets ?? []],
    ["density", "Density", data?.controls.densities ?? []],
    ["section_order_preset", "Section order", data?.controls.section_order_presets ?? []],
    ["accent_color", "Accent colour", data?.controls.accent_colors ?? []],
    ["font_family", "Font", data?.controls.font_families ?? []],
  ];
  return (
    <section aria-labelledby="resume-studio-title" className="space-y-4">
      <div>
        <h2 id="resume-studio-title" className="text-base font-semibold" style={{ color: "var(--text)" }}>Resume Studio</h2>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Choose an ATS-safe design for this application pack.</p>
      </div>
      {analysis ? (
        <div className="rounded-lg p-3 text-xs" style={{ background: "var(--accent-soft)", color: "var(--text)" }}>
          <strong>Recommended for this role:</strong> {analysis.analysis.seniority_level?.toLowerCase().includes("senior") ? "Executive UK 2-page" : template?.name}
          <div style={{ color: "var(--text-muted)" }}>Based on role seniority, job type, evidence density, ATS safety, and page target.</div>
        </div>
      ) : <p className="text-xs" style={{ color: "var(--text-muted)" }}>Analyse the JD to get a template recommendation.</p>}
      <div className="grid grid-cols-2 gap-2">
        {data?.templates.map((item) => (
          <button key={item.id} type="button" onClick={() => set("template_id", item.id)}
            className="rounded-lg p-3 text-left text-xs"
            style={{ border: `1px solid ${item.id === value.template_id ? "var(--accent)" : "var(--border)"}`, background: "var(--surface-2)", color: "var(--text)" }}>
            <strong>{item.name}</strong><span className="mt-1 block" style={{ color: "var(--text-muted)" }}>{item.description}</span>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {controls.map(([key, label, options]) => <label key={key} className="text-xs" style={{ color: "var(--text-muted)" }}>{label}
          <select aria-label={label} value={value[key]} onChange={(e) => set(key, e.target.value)}
            className="mt-1 w-full rounded-lg px-2 py-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}>
            {options.map((option) => <option key={option} value={option}>{labels[option] ?? option[0].toUpperCase() + option.slice(1)}</option>)}
          </select>
        </label>)}
      </div>
      <div className="mx-auto rounded-md bg-white p-5 text-slate-800 shadow-sm" style={{ aspectRatio: "210 / 297", maxHeight: 360, borderTop: "5px solid var(--accent)" }}>
        <div className="text-center text-lg font-bold">Candidate name</div>
        <div className="mt-4 text-xs font-bold uppercase">Professional summary</div>
        <div className="mt-2 h-2 rounded bg-slate-200" /><div className="mt-1 h-2 w-4/5 rounded bg-slate-200" />
        <div className="mt-5 text-xs font-bold uppercase">Core skills</div>
        <div className="mt-2 text-[10px] text-slate-500">Evidence-led skills from your profile and master CV</div>
        <div className="mt-5 text-xs font-bold uppercase">Experience</div>
        <div className="mt-2 h-2 rounded bg-slate-200" /><div className="mt-1 h-2 w-3/4 rounded bg-slate-200" />
      </div>
      <p className="text-center text-xs" style={{ color: "var(--text-muted)" }}>
        {generated ? "Generated structured content preview." : "Pre-generation style preview."} Preview is an approximation. DOCX export is the source of truth.
      </p>
    </section>
  );
}
