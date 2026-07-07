"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { X } from "lucide-react";

interface SettingsTagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  label: string;
  placeholder?: string;
  invalid?: boolean;
}

export interface SettingsTagInputHandle {
  focus: () => void;
}

export const SettingsTagInput = forwardRef<SettingsTagInputHandle, SettingsTagInputProps>(
  ({ tags, onChange, label, placeholder = "Type and press Enter", invalid = false }, ref) => {
    const [input, setInput] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => inputRef.current?.focus(),
    }));

    const add = (value: string) => {
      const trimmed = value.trim();
      const duplicate = tags.some((tag) => tag.toLocaleLowerCase() === trimmed.toLocaleLowerCase());
      if (trimmed && !duplicate) onChange([...tags, trimmed]);
      setInput("");
    };

    return (
      <div
        className="flex min-h-11 flex-wrap gap-1.5 rounded-[var(--radius-control)] border bg-[var(--surface-2)] p-2"
        style={{ borderColor: invalid ? "var(--danger)" : "var(--border)" }}
      >
        {tags.map((tag) => (
          <span
            className="inline-flex items-center gap-1 rounded-[var(--radius-compact)] bg-[var(--accent-soft)] px-2 py-1 text-xs font-semibold text-[var(--accent)]"
            key={tag}
          >
            {tag}
            <button
              aria-label={`Remove ${tag}`}
              className="rounded-sm opacity-70 hover:opacity-100"
              onClick={() => onChange(tags.filter((item) => item !== tag))}
              type="button"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}
        <input
          aria-label={label}
          className="min-w-[140px] flex-1 bg-transparent px-1 py-1 text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === ",") && input.trim()) {
              event.preventDefault();
              add(input);
            }
          }}
          placeholder={tags.length ? "" : placeholder}
          ref={inputRef}
          value={input}
        />
      </div>
    );
  },
);

SettingsTagInput.displayName = "SettingsTagInput";
