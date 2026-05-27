"use client";

import { User } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export interface CandidateData {
  name: string;
  title: string;
  years_experience: number;
  summary: string;
}

interface StepAboutYouProps {
  candidate: CandidateData;
  onChange: (candidate: CandidateData) => void;
}

export function StepAboutYou({ candidate, onChange }: StepAboutYouProps) {
  return (
    <div className="space-y-4">
      <CardHeader className="px-0 pt-0">
        <div className="flex items-center gap-2">
          <User className="w-5 h-5 text-brand-600" />
          <CardTitle>Who are you?</CardTitle>
        </div>
        <CardDescription>Used in CV and cover letter generation — never hardcoded in code.</CardDescription>
      </CardHeader>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="name">Full name *</Label>
          <Input
            id="name"
            value={candidate.name}
            onChange={(e) => onChange({ ...candidate, name: e.target.value })}
            placeholder="Alex Johnson"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="title">Current / target title *</Label>
          <Input
            id="title"
            value={candidate.title}
            onChange={(e) => onChange({ ...candidate, title: e.target.value })}
            placeholder="Senior Delivery Lead"
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="years">Years of experience</Label>
        <Input
          id="years"
          type="number"
          min={0}
          value={candidate.years_experience}
          onChange={(e) => onChange({ ...candidate, years_experience: parseInt(e.target.value) || 0 })}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="summary">Professional summary (2–3 sentences)</Label>
        <Textarea
          id="summary"
          rows={3}
          value={candidate.summary}
          onChange={(e) => onChange({ ...candidate, summary: e.target.value })}
          placeholder="Senior technology professional with 15 years leading complex transformation programmes…"
        />
      </div>
    </div>
  );
}
