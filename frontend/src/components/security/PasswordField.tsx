"use client";

import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

interface PasswordFieldProps {
  autoComplete: "current-password" | "new-password";
  describedBy?: string;
  disabled?: boolean;
  error?: string;
  id?: string;
  label: string;
  name: string;
  onChange: (value: string) => void;
  value: string;
  autoFocus?: boolean;
}

export function PasswordField({
  autoComplete,
  autoFocus,
  describedBy,
  disabled,
  error,
  id: providedId,
  label,
  name,
  onChange,
  value,
}: PasswordFieldProps) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const errorId = `${id}-error`;
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <label className="block text-sm font-medium text-[var(--text)]" htmlFor={id}>
        {label}
      </label>
      <div className="relative mt-2">
        <input
          aria-describedby={[describedBy, error ? errorId : undefined].filter(Boolean).join(" ") || undefined}
          aria-invalid={error ? true : undefined}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          className={cn(
            "h-11 w-full rounded-[var(--radius-control)] border bg-[var(--surface-2)] px-3 pr-12 text-base text-[var(--text)] outline-none",
            "focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)]",
            error ? "border-[var(--danger)]" : "border-[var(--border)]",
          )}
          disabled={disabled}
          id={id}
          name={name}
          onChange={(event) => onChange(event.target.value)}
          required
          type={visible ? "text" : "password"}
          value={value}
        />
        <button
          aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`}
          className="hatch-interactive absolute inset-y-0 right-0 inline-flex w-11 items-center justify-center rounded-[var(--radius-control)] text-[var(--text-muted)] hover:text-[var(--text)]"
          disabled={disabled}
          onClick={() => setVisible((current) => !current)}
          type="button"
        >
          {visible ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}
        </button>
      </div>
      {error ? <p className="mt-1.5 text-sm text-[var(--danger)]" id={errorId}>{error}</p> : null}
    </div>
  );
}
