import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SectionCardProps extends HTMLAttributes<HTMLElement> {
  title?: string;
  description?: string;
  actions?: ReactNode;
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  ...props
}: SectionCardProps) {
  return (
    <section
      className={cn(
        "rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5",
        className,
      )}
      {...props}
    >
      {title || description || actions ? (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {title ? <h2 className="text-base font-semibold text-[var(--text)]">{title}</h2> : null}
            {description ? (
              <p className="mt-1 text-sm text-[var(--text-dim)]">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
