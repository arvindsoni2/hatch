"use client";

import { useState } from "react";
import { Copy, Check, Mail, Phone, Building2 } from "lucide-react";

interface RecruiterContactProps {
  recruiterName: string | null;
  recruiterEmail: string | null;
  recruiterPhone: string | null;
  agencyName: string | null;
}

export function RecruiterContact({
  recruiterName,
  recruiterEmail,
  recruiterPhone,
  agencyName,
}: RecruiterContactProps) {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  if (!recruiterName && !recruiterEmail && !recruiterPhone && !agencyName) {
    return (
      <p className="text-sm text-slate-400">No recruiter information recorded.</p>
    );
  }

  return (
    <div className="space-y-2">
      {agencyName && (
        <div className="flex items-center gap-2 text-sm">
          <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-slate-700">{agencyName}</span>
        </div>
      )}
      {recruiterName && (
        <div className="text-sm font-medium text-slate-800">{recruiterName}</div>
      )}
      {recruiterEmail && (
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-sm text-slate-600">{recruiterEmail}</span>
          <button
            onClick={() => void copy(recruiterEmail, "email")}
            className="ml-auto text-slate-400 hover:text-slate-600 transition-colors"
          >
            {copied === "email" ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </button>
        </div>
      )}
      {recruiterPhone && (
        <div className="flex items-center gap-2">
          <Phone className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-sm text-slate-600">{recruiterPhone}</span>
          <button
            onClick={() => void copy(recruiterPhone, "phone")}
            className="ml-auto text-slate-400 hover:text-slate-600 transition-colors"
          >
            {copied === "phone" ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </button>
        </div>
      )}
    </div>
  );
}
