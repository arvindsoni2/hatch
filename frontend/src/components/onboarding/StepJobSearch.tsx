"use client";

import { Globe, Loader2 } from "lucide-react";
import { CheckCircle2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useState } from "react";
import type { LocaleSummary, LocaleLegalField } from "@/lib/api";

export interface SearchData {
  target_roles: string[];
  contract_type: string;
}

export interface LocationData {
  city: string;
  country: string;
  radius_miles: number;
  remote_preference: string;
}

export interface CompensationData {
  min_rate: number;
  max_rate: number;
  rate_type: string;
  currency: string;
  legal_preferences: Record<string, string>;
}

interface StepJobSearchProps {
  selectedLocale: string;
  locales: LocaleSummary[];
  loadingLocales: boolean;
  onLocaleChange: (locale: string) => void;
  search: SearchData;
  onSearchChange: (search: SearchData) => void;
  locations: LocationData[];
  onLocationsChange: (locations: LocationData[]) => void;
  compensation: CompensationData;
  onCompensationChange: (compensation: CompensationData) => void;
  legalFields: LocaleLegalField[];
  localeName: string;
}

function TagInput({ label, tags, onAdd, onRemove, placeholder }: {
  label: string; tags: string[]; onAdd: (t: string) => void;
  onRemove: (i: number) => void; placeholder?: string;
}) {
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

export function StepJobSearch({
  selectedLocale, locales, loadingLocales, onLocaleChange,
  search, onSearchChange,
  locations, onLocationsChange,
  compensation, onCompensationChange,
  legalFields, localeName,
}: StepJobSearchProps) {
  const loc = locations[0];
  return (
    <div className="space-y-5">
      <CardHeader className="px-0 pt-0">
        <div className="flex items-center gap-2">
          <Globe className="w-5 h-5 text-brand-600" />
          <CardTitle>Your market</CardTitle>
        </div>
        <CardDescription>
          Pick your job market — this controls which job boards are scraped and how compliance fields are shown.
        </CardDescription>
      </CardHeader>

      {loadingLocales ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading markets…
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {locales.map((l) => (
            <button
              key={l.id}
              onClick={() => onLocaleChange(l.id)}
              className={`p-4 border-2 rounded-lg text-left transition-colors flex items-center gap-3 ${
                selectedLocale === l.id ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <span className="text-2xl">{l.flag}</span>
              <span className="font-medium text-sm">{l.name}</span>
              {selectedLocale === l.id && <CheckCircle2 className="h-4 w-4 text-brand-600 ml-auto" />}
            </button>
          ))}
        </div>
      )}

      <TagInput
        label="Target job titles *"
        tags={search.target_roles}
        onAdd={(t) => onSearchChange({ ...search, target_roles: [...search.target_roles, t] })}
        onRemove={(i) => onSearchChange({ ...search, target_roles: search.target_roles.filter((_, idx) => idx !== i) })}
        placeholder="Delivery Lead, Product Manager…"
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <Label>City *</Label>
          <Input
            value={loc.city}
            onChange={(e) => onLocationsChange([{ ...loc, city: e.target.value }])}
            placeholder="City"
          />
        </div>
        <div className="space-y-1">
          <Label>Country *</Label>
          <Input
            value={loc.country}
            onChange={(e) => onLocationsChange([{ ...loc, country: e.target.value }])}
            placeholder="Country"
          />
        </div>
        <div className="space-y-1">
          <Label>Remote preference</Label>
          <select
            className="w-full border rounded-md p-2 text-sm"
            value={loc.remote_preference}
            onChange={(e) => onLocationsChange([{ ...loc, remote_preference: e.target.value }])}
          >
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
            <option value="any">Any</option>
          </select>
        </div>
      </div>

      <div className="space-y-1 w-full sm:w-1/2">
        <Label>Job type</Label>
        <select
          className="w-full border rounded-md p-2 text-sm"
          value={search.contract_type}
          onChange={(e) => onSearchChange({ ...search, contract_type: e.target.value })}
        >
          <option value="permanent">Permanent</option>
          <option value="temporary">Temporary</option>
          <option value="hybrid">Hybrid</option>
          <option value="remote">Remote</option>
          <option value="any">Any</option>
        </select>
      </div>

      {/* Compensation */}
      <div className="space-y-4 pt-2 border-t">
        <p className="text-sm font-medium text-slate-700">
          Compensation — {localeName} market
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1">
            <Label>Min rate *</Label>
            <Input
              type="number"
              value={compensation.min_rate}
              onChange={(e) => onCompensationChange({ ...compensation, min_rate: parseFloat(e.target.value) || 0 })}
            />
          </div>
          <div className="space-y-1">
            <Label>Max rate</Label>
            <Input
              type="number"
              value={compensation.max_rate}
              onChange={(e) => onCompensationChange({ ...compensation, max_rate: parseFloat(e.target.value) || 0 })}
            />
          </div>
          <div className="space-y-1">
            <Label>Rate type</Label>
            <select
              className="w-full border rounded-md p-2 text-sm"
              value={compensation.rate_type}
              onChange={(e) => onCompensationChange({ ...compensation, rate_type: e.target.value })}
            >
              <option value="daily">Daily</option>
              <option value="hourly">Hourly</option>
              <option value="annual">Annual</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
        </div>
        <div className="space-y-1 w-full sm:w-1/3">
          <Label>Currency</Label>
          <Input
            value={compensation.currency}
            onChange={(e) => onCompensationChange({ ...compensation, currency: e.target.value })}
            placeholder="Currency (e.g. GBP, USD, INR)"
          />
        </div>

        {legalFields.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-700">Eligibility & compliance</p>
            {legalFields.map((field) => (
              <div key={field.id} className="space-y-1">
                <Label>{field.label}</Label>
                {field.type === "select" && field.options ? (
                  <select
                    className="w-full border rounded-md p-2 text-sm"
                    value={compensation.legal_preferences[field.id] ?? field.default}
                    onChange={(e) => onCompensationChange({
                      ...compensation,
                      legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value },
                    })}
                  >
                    {field.options.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={compensation.legal_preferences[field.id] ?? ""}
                    onChange={(e) => onCompensationChange({
                      ...compensation,
                      legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value },
                    })}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
