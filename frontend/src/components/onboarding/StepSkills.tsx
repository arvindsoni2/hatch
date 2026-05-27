"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export interface SkillsData {
  primary: string[];
  secondary: string[];
  certifications: string[];
}

export interface DomainsData {
  preferred: string[];
  excluded: string[];
}

export interface ProofPoint {
  id: string;
  summary: string;
  context: string;
  metrics: string;
  tags: string[];
}

interface TagInputProps {
  label: string;
  tags: string[];
  onAdd: (t: string) => void;
  onRemove: (i: number) => void;
  placeholder?: string;
}

function TagInput({ label, tags, onAdd, onRemove, placeholder }: TagInputProps) {
  const [input, setInput] = useState("");
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-2 p-2 border rounded-md min-h-[42px] bg-white">
        {tags.map((t, i) => (
          <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => onRemove(i)}>
            {t} ×
          </Badge>
        ))}
        <input
          className="flex-1 min-w-[120px] outline-none text-sm bg-transparent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === ",") && input.trim()) {
              e.preventDefault();
              onAdd(input.trim());
              setInput("");
            }
          }}
          placeholder={placeholder ?? "Type and press Enter"}
        />
      </div>
      <p className="text-xs text-slate-400">Press Enter or comma to add</p>
    </div>
  );
}

function ProofPointForm({ point, onChange, onRemove }: {
  point: ProofPoint;
  onChange: (p: ProofPoint) => void;
  onRemove: () => void;
}) {
  const [tagInput, setTagInput] = useState("");
  return (
    <div className="border rounded-lg p-4 space-y-3 bg-slate-50">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">Achievement</p>
        <button onClick={onRemove} className="text-xs text-red-500 hover:underline">Remove</button>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">One-line summary *</Label>
        <Input
          value={point.summary}
          onChange={(e) => onChange({ ...point, summary: e.target.value })}
          placeholder="Led migration of 3 legacy systems to AWS, cutting infra costs 40%"
        />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs">Context (Situation / Task)</Label>
          <Textarea rows={2} value={point.context} onChange={(e) => onChange({ ...point, context: e.target.value })} placeholder="Inherited a fragile on-prem estate…" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Metrics / Result</Label>
          <Textarea rows={2} value={point.metrics} onChange={(e) => onChange({ ...point, metrics: e.target.value })} placeholder="£1.2M annual saving, 99.9% uptime" />
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Tags (skills demonstrated)</Label>
        <div className="flex flex-wrap gap-1.5 p-2 border rounded-md bg-white min-h-[34px]">
          {point.tags.map((t, i) => (
            <Badge
              key={i}
              variant="secondary"
              className="text-xs cursor-pointer"
              onClick={() => onChange({ ...point, tags: point.tags.filter((_, j) => j !== i) })}
            >
              {t} ×
            </Badge>
          ))}
          <input
            className="flex-1 min-w-[80px] outline-none text-xs bg-transparent"
            value={tagInput}
            placeholder="AWS, Cloud…"
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === ",") && tagInput.trim()) {
                e.preventDefault();
                onChange({ ...point, tags: [...point.tags, tagInput.trim()] });
                setTagInput("");
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

interface StepSkillsProps {
  skills: SkillsData;
  onSkillsChange: (skills: SkillsData) => void;
  domains: DomainsData;
  onDomainsChange: (domains: DomainsData) => void;
  proofPoints: ProofPoint[];
  onProofPointsChange: (points: ProofPoint[]) => void;
}

export function StepSkills({ skills, onSkillsChange, domains, onDomainsChange, proofPoints, onProofPointsChange }: StepSkillsProps) {
  const addProofPoint = () => {
    onProofPointsChange([...proofPoints, { id: `pp_${Date.now()}`, summary: "", context: "", metrics: "", tags: [] }]);
  };

  return (
    <div className="space-y-4">
      <CardHeader className="px-0 pt-0">
        <div className="flex items-center gap-2">
          <Star className="w-5 h-5 text-brand-600" />
          <CardTitle>Skills & achievements</CardTitle>
        </div>
        <CardDescription>
          Primary skills are weighted most heavily. Achievements give the AI concrete proof points for tailoring.
        </CardDescription>
      </CardHeader>

      <TagInput
        label="Primary skills *"
        tags={skills.primary}
        onAdd={(t) => onSkillsChange({ ...skills, primary: [...skills.primary, t] })}
        onRemove={(i) => onSkillsChange({ ...skills, primary: skills.primary.filter((_, idx) => idx !== i) })}
        placeholder="Agile, AWS, Stakeholder management…"
      />
      {skills.primary.length > 0 && skills.primary.length < 3 && (
        <p className="text-xs text-amber-600">Adding ≥ 3 primary skills improves matching accuracy.</p>
      )}
      <TagInput
        label="Secondary skills"
        tags={skills.secondary}
        onAdd={(t) => onSkillsChange({ ...skills, secondary: [...skills.secondary, t] })}
        onRemove={(i) => onSkillsChange({ ...skills, secondary: skills.secondary.filter((_, idx) => idx !== i) })}
        placeholder="Python, Terraform…"
      />
      <TagInput
        label="Certifications"
        tags={skills.certifications}
        onAdd={(t) => onSkillsChange({ ...skills, certifications: [...skills.certifications, t] })}
        onRemove={(i) => onSkillsChange({ ...skills, certifications: skills.certifications.filter((_, idx) => idx !== i) })}
        placeholder="PMP, AWS SA, PSM-I…"
      />
      <TagInput
        label="Preferred domains"
        tags={domains.preferred}
        onAdd={(t) => onDomainsChange({ ...domains, preferred: [...domains.preferred, t] })}
        onRemove={(i) => onDomainsChange({ ...domains, preferred: domains.preferred.filter((_, idx) => idx !== i) })}
        placeholder="FinTech, Energy, Public Sector…"
      />

      <div className="space-y-3 pt-1">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-slate-700">Achievements (optional — improves CV tailoring)</p>
          <Button variant="outline" size="sm" onClick={addProofPoint}>+ Add achievement</Button>
        </div>
        {proofPoints.map((p, i) => (
          <ProofPointForm
            key={p.id}
            point={p}
            onChange={(updated) => onProofPointsChange(proofPoints.map((x, j) => j === i ? updated : x))}
            onRemove={() => onProofPointsChange(proofPoints.filter((_, j) => j !== i))}
          />
        ))}
        {proofPoints.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-4">No achievements added yet. You can add them later in Settings.</p>
        )}
      </div>
    </div>
  );
}
