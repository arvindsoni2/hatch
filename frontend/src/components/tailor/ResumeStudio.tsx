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
  const selectedSummary = [
    template?.name,
    labels[value.page_target] ?? value.page_target,
    labels[value.density] ?? value.density,
  ].filter(Boolean).join(" / ");

  return (
    <section aria-labelledby="cv-design-title" className="space-y-4">
      <div>
        <h3 id="cv-design-title" className="text-sm font-semibold" style={{ color: "var(--text)" }}>CV design</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Choose an ATS-safe layout for this application.</p>
      </div>
      {analysis ? (
        <div className="rounded-lg p-3 text-xs" style={{ background: "var(--accent-soft)", color: "var(--text)" }}>
          <strong>Recommended for this role:</strong> {analysis.analysis.seniority_level?.toLowerCase().includes("senior") ? "Executive UK 2-page" : template?.name}
          <div style={{ color: "var(--text-muted)" }}>Based on role seniority, job type, evidence density, ATS safety, and page target.</div>
        </div>
      ) : <p className="text-xs" style={{ color: "var(--text-muted)" }}>Analyse the JD to get a template recommendation.</p>}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {data?.templates.map((item) => (
          <button key={item.id} type="button" onClick={() => set("template_id", item.id)}
            className="rounded-lg p-3 text-left text-xs"
            style={{ border: `1px solid ${item.id === value.template_id ? "var(--accent)" : "var(--border)"}`, background: "var(--surface-2)", color: "var(--text)" }}>
            <strong>{item.name}</strong><span className="mt-1 block" style={{ color: "var(--text-muted)" }}>{item.description}</span>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {controls.map(([key, label, options]) => <label key={key} className="text-xs" style={{ color: "var(--text-muted)" }}>{label}
          <select aria-label={label} value={value[key]} onChange={(e) => set(key, e.target.value)}
            className="mt-1 w-full rounded-lg px-2 py-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}>
            {options.map((option) => <option key={option} value={option}>{labels[option] ?? option[0].toUpperCase() + option.slice(1)}</option>)}
          </select>
        </label>)}
      </div>
      <div className="rounded-lg p-3" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
        <p className="text-xs font-medium" style={{ color: "var(--text)" }}>Current selection</p>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>{selectedSummary || "Loading CV options..."}</p>
      </div>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        {generated ? "Your generated DOCX uses these settings." : "The generated DOCX is the final layout."}
      </p>
    </section>
  );
}
