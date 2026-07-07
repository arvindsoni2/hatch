"use client";

import { useState } from "react";
import { Info, Check } from "lucide-react";

/* ─── Field ─────────────────────────────────────────────────────────────── */
interface FieldProps {
  label?: string;
  req?: boolean;
  optional?: boolean;
  hint?: string;
  hintTone?: "err" | "ok" | "";
  children: React.ReactNode;
}

export function Field({ label, req, optional, hint, hintTone = "", children }: FieldProps) {
  return (
    <div className="mb-4">
      {label && (
        <div className="flex items-center gap-1.5 mb-1.5 text-[13px] font-[550] text-[var(--text)]">
          {label}
          {req && <span className="text-[var(--accent)]">*</span>}
          {optional && (
            <span className="ml-auto text-[11px] font-[500] text-[var(--text-muted)]">Optional</span>
          )}
        </div>
      )}
      {children}
      {hint && <Help tone={hintTone}>{hint}</Help>}
    </div>
  );
}

/* ─── Help ──────────────────────────────────────────────────────────────── */
interface HelpProps {
  children: React.ReactNode;
  tone?: "err" | "ok" | "";
}

export function Help({ children, tone = "" }: HelpProps) {
  const colorClass =
    tone === "err" ? "text-[var(--danger)]" :
    tone === "ok"  ? "text-[var(--success)]" :
    "text-[var(--text-muted)]";
  const Icon = tone === "ok" ? Check : Info;
  return (
    <div className={`flex gap-1.5 mt-1.5 text-[12px] leading-[1.45] ${colorClass}`}>
      <Icon size={13} className="flex-shrink-0 mt-[1px] opacity-80" />
      <span>{children}</span>
    </div>
  );
}

/* ─── Why callout ───────────────────────────────────────────────────────── */
export function Why({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 p-[11px_13px] mb-4 rounded-[var(--r-card,10px)] text-[12.5px] leading-[1.5] text-[var(--text-dim)]"
      style={{ background: "var(--accent-soft)", border: "1px solid var(--accent-soft-strong)" }}>
      <Info size={15} className="flex-shrink-0 mt-[1px] text-[var(--accent)]" />
      <span>{children}</span>
    </div>
  );
}

/* ─── TagInput ──────────────────────────────────────────────────────────── */
interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  invalid?: boolean;
}

export function TagInput({ tags, onChange, placeholder, suggestions = [], invalid }: TagInputProps) {
  const [input, setInput] = useState("");
  const add = (t: string) => {
    const v = t.trim();
    const duplicate = tags.some((tag) => tag.toLocaleLowerCase() === v.toLocaleLowerCase());
    if (v && !duplicate) onChange([...tags, v]);
    setInput("");
  };
  const remove = (i: number) => onChange(tags.filter((_, idx) => idx !== i));
  const avail = suggestions.filter((suggestion) => (
    !tags.some((tag) => tag.toLocaleLowerCase() === suggestion.toLocaleLowerCase())
  ));

  return (
    <div>
      <div
        className={`flex flex-wrap gap-1.5 p-2 min-h-[44px] rounded-[var(--r-field,8px)] transition-[border-color,box-shadow] ${
          invalid
            ? "border border-[var(--danger)]"
            : "border border-[var(--border)] focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-soft)]"
        }`}
        style={{ background: "var(--surface-2)" }}
      >
        {tags.map((t, i) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[var(--r-chip,6px)] text-[12.5px] font-[550] text-[var(--text)]"
            style={{ background: "var(--accent-soft)" }}
          >
            {t}
            <button
              type="button"
              aria-label={`Remove ${t}`}
              onClick={() => remove(i)}
              className="opacity-65 hover:opacity-100 text-[14px] leading-none"
            >
              ×
            </button>
          </span>
        ))}
        <input
          aria-label={placeholder ?? "Add item"}
          className="flex-1 min-w-[100px] bg-transparent border-0 outline-none text-[14px] text-[var(--text)] placeholder:text-[var(--text-muted)] px-1 py-1"
          value={input}
          placeholder={tags.length ? "" : placeholder}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === ",") && input.trim()) {
              e.preventDefault();
              add(input);
            }
            if (e.key === "Backspace" && !input && tags.length) remove(tags.length - 1);
          }}
        />
      </div>
      {avail.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {avail.slice(0, 5).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="text-[12px] font-[500] text-[var(--text-dim)] px-2.5 py-1 rounded-[var(--r-chip,6px)] border border-dashed border-[var(--border-strong)] hover:text-[var(--text)] hover:border-[var(--accent)] hover:border-solid transition-all"
              style={{ background: "var(--surface)" }}
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Choice card ───────────────────────────────────────────────────────── */
interface ChoiceProps {
  on: boolean;
  onClick: () => void;
  flag?: string;
  title: string;
  sub?: string;
}

export function Choice({ on, onClick, flag, title, sub }: ChoiceProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`choice flex items-center gap-2.5 text-left px-3 py-3 rounded-[var(--r-card,10px)] border transition-all font-inherit w-full cursor-pointer ${
        on
          ? "on border-[var(--accent)] text-[var(--text)]"
          : "border-[var(--border)] text-[var(--text)] hover:border-[var(--border-strong)]"
      }`}
      style={{
        background: on ? "var(--accent-soft)" : "var(--surface)",
      }}
    >
      {flag && <span className="text-[22px] leading-none flex-shrink-0">{flag}</span>}
      <span className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span className="block text-[14px] font-[600]">{title}</span>
        {sub && <span className="block text-[11.5px] text-[var(--text-muted)]">{sub}</span>}
      </span>
      <span className={`w-[18px] h-[18px] flex-shrink-0 text-[var(--accent)] transition-opacity ${on ? "opacity-100" : "opacity-0"}`}>
        <Check size={16} strokeWidth={2.4} />
      </span>
    </button>
  );
}

/* ─── Segmented control ─────────────────────────────────────────────────── */
interface SegOption { v: string; l: string; }

interface SegProps {
  value: string;
  onChange: (v: string) => void;
  options: SegOption[];
}

export function Seg({ value, onChange, options }: SegProps) {
  return (
    <div
      className="flex gap-1 p-1 rounded-[var(--r-field,8px)] border border-[var(--border)]"
      style={{ background: "var(--surface-2)" }}
    >
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={`flex-1 text-[12.5px] font-[550] px-2 py-2 rounded-[calc(var(--r-field,8px)-4px)] transition-all whitespace-nowrap ${
            value === o.v
              ? "on text-[var(--text)] shadow-[0_1px_3px_rgba(0,0,0,.3)]"
              : "text-[var(--text-muted)] hover:text-[var(--text)]"
          }`}
          style={value === o.v ? { background: "var(--bg-elevated, var(--bg-elev, var(--bg)))" } : { background: "transparent" }}
        >
          {o.l}
        </button>
      ))}
    </div>
  );
}

/* ─── ToggleRow ─────────────────────────────────────────────────────────── */
interface ToggleRowProps {
  on: boolean;
  onToggle: () => void;
  title: string;
  sub?: string;
}

export function ToggleRow({ on, onToggle, title, sub }: ToggleRowProps) {
  return (
    <div
      className="flex items-center gap-3 px-3 py-3 rounded-[var(--r-card,10px)] border border-[var(--border)] mb-2"
      style={{ background: "var(--surface)" }}
    >
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] font-[550] text-[var(--text)]">{title}</div>
        {sub && <div className="text-[11.5px] text-[var(--text-muted)] mt-0.5">{sub}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={onToggle}
        className={`relative w-10 h-6 rounded-full border-0 flex-shrink-0 cursor-pointer transition-colors ${
          on ? "bg-[var(--accent)]" : "bg-[var(--surface-3)]"
        }`}
      >
        <span
          className={`absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white transition-transform ${
            on ? "left-[3px] translate-x-4" : "left-[3px]"
          }`}
        />
      </button>
    </div>
  );
}

/* ─── ChipInfo: read-only info chip ─────────────────────────────────────── */
export function ChipInfo({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--r-field,8px)] border border-[var(--border)] text-[13px] font-[600] text-[var(--text)]"
      style={{ background: "var(--surface-2)" }}
    >
      {children}
    </div>
  );
}
