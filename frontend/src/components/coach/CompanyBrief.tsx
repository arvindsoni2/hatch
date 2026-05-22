"use client";

import { CompanyResearchResponse } from "@/lib/api";
import { Building2, Globe, Layers, Newspaper } from "lucide-react";

interface CompanyBriefProps {
  research: CompanyResearchResponse;
}

export function CompanyBrief({ research }: CompanyBriefProps) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 text-sm">
      <div className="mb-3 flex items-center gap-2">
        <Building2 className="h-4 w-4 text-indigo-400" />
        <h3 className="font-semibold text-slate-100">{research.company_name}</h3>
      </div>

      {research.sector && (
        <p className="mb-2 text-xs text-slate-500">{research.sector}</p>
      )}

      {research.description && (
        <p className="mb-3 text-slate-300 leading-relaxed">{research.description}</p>
      )}

      {research.website && (
        <a
          href={research.website}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-3 flex items-center gap-1 text-xs text-indigo-400 hover:underline"
        >
          <Globe className="h-3 w-3" />
          {research.website.replace(/^https?:\/\//, "")}
        </a>
      )}

      {research.tech_stack_signals.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-slate-400">
            <Layers className="h-3 w-3" /> Tech Stack
          </div>
          <div className="flex flex-wrap gap-1">
            {research.tech_stack_signals.slice(0, 6).map((signal, i) => (
              <span
                key={i}
                className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
              >
                {signal}
              </span>
            ))}
          </div>
        </div>
      )}

      {research.recent_news.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-slate-400">
            <Newspaper className="h-3 w-3" /> Recent News
          </div>
          <ul className="space-y-1">
            {research.recent_news.slice(0, 3).map((news, i) => (
              <li key={i} className="text-xs text-slate-400 before:mr-1 before:content-['·']">
                {news}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
