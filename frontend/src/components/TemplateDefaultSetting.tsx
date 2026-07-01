"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchResumeTemplates, setDefaultResumeTemplate } from "@/lib/api";

export function TemplateDefaultSetting() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["resume-templates"],
    queryFn: fetchResumeTemplates,
  });

  if (isLoading || !data) return null;
  return (
    <div className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div>
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Default resume template</h2>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>Used for future tailoring unless you override it for a job.</p>
      </div>
      <select
        aria-label="Default resume template"
        value={data.default_template_id}
        onChange={async (event) => {
          await setDefaultResumeTemplate(event.target.value);
          await queryClient.invalidateQueries({ queryKey: ["resume-templates"] });
        }}
        className="w-full rounded-lg px-3 py-2 text-sm"
        style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
      >
        {data.templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
      </select>
    </div>
  );
}
