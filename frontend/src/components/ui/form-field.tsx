import * as React from "react";
import { cn } from "@/lib/utils";

interface FieldControlProps {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}

export interface FormFieldProps {
  id: string;
  label: string;
  children: React.ReactElement<FieldControlProps>;
  description?: string;
  error?: string;
  required?: boolean;
  className?: string;
}

export function FormField({
  id,
  label,
  children,
  description,
  error,
  required,
  className,
}: FormFieldProps) {
  const descriptionId = description ? `${id}-description` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [
    children.props["aria-describedby"],
    descriptionId,
    errorId,
  ].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("grid gap-2", className)} data-invalid={Boolean(error)}>
      <label className="text-sm font-medium text-[var(--text)]" htmlFor={id}>
        {label}
        {required ? (
          <>
            <span aria-hidden="true" className="text-[var(--danger)]"> *</span>
            <span className="sr-only"> (required)</span>
          </>
        ) : null}
      </label>
      {React.cloneElement(children, {
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : children.props["aria-invalid"],
      })}
      {description ? (
        <p className="text-xs text-[var(--text-muted)]" id={descriptionId}>
          {description}
        </p>
      ) : null}
      {error ? (
        <p className="text-xs font-medium text-[var(--danger)]" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
