"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchResumeTemplates, setDefaultResumeTemplate, type ResumeDesignSettings } from "@/lib/api";
import { useEffect, useState } from "react";

export function TemplateDefaultSetting() {
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState<ResumeDesignSettings | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["resume-templates"],
    queryFn: fetchResumeTemplates,
  });
  useEffect(() => { if (data) setSettings(data.default_design_settings); }, [data]);

  if (isLoading || !data || !settings) return null;
  const save = async (next: ResumeDesignSettings) => {
    setSettings(next);
    await setDefaultResumeTemplate(next.template_id, next);
    await queryClient.invalidateQueries({ queryKey: ["resume-templates"] });
  };
  return (
    <div className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div>
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Default resume design</h2>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>Used for future tailoring unless you override it for a job.</p>
      </div>
      <select
        aria-label="Default resume template"
        value={settings.template_id}
        onChange={async (event) => {
          await save({ ...settings, template_id: event.target.value });
        }}
        className="w-full rounded-lg px-3 py-2 text-sm"
        style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
      >
        {data.templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
      </select>
      <div className="grid grid-cols-2 gap-2">
        {([
          ["page_target", "Page target", data.controls.page_targets],
          ["density", "Density", data.controls.densities],
          ["section_order_preset", "Section order", data.controls.section_order_presets],
          ["accent_color", "Accent colour", data.controls.accent_colors],
          ["font_family", "Font", data.controls.font_families],
        ] as const).map(([key, label, values]) => (
          <label key={key} className="text-xs" style={{ color: "var(--text-muted)" }}>{label}
            <select value={settings[key]} onChange={(event) => void save({ ...settings, [key]: event.target.value })}
              className="mt-1 w-full rounded-lg px-2 py-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}>
              {values.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
            </select>
          </label>
        ))}
      </div>
    </div>
  );
}
