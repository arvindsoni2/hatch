import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageWidth = "narrow" | "default" | "wide" | "full";

const PAGE_WIDTHS: Record<PageWidth, string> = {
  narrow: "max-w-3xl",
  default: "max-w-5xl",
  wide: "max-w-7xl",
  full: "max-w-none",
};

export interface PageContainerProps extends HTMLAttributes<HTMLDivElement> {
  width?: PageWidth;
}

export function PageContainer({
  width = "default",
  className,
  ...props
}: PageContainerProps) {
  return <div className={cn("mx-auto w-full", PAGE_WIDTHS[width], className)} {...props} />;
}

export interface PageHeaderProps extends HTMLAttributes<HTMLElement> {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  description,
  actions,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "hatch-page-header mb-6 flex items-start justify-between gap-4",
        className,
      )}
      {...props}
    >
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--text)] sm:text-[28px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-1 max-w-[65ch] text-sm text-[var(--text-dim)]">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="hatch-page-actions flex shrink-0 items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}
