import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  body: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, body, action }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-xl py-14 px-6 text-center"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center justify-center w-12 h-12 rounded-xl mb-4"
        style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
      >
        {icon}
      </div>
      <h3
        className="text-base font-semibold mb-1"
        style={{ color: "var(--text)" }}
      >
        {title}
      </h3>
      <p
        className="text-sm max-w-sm"
        style={{ color: "var(--text-muted)" }}
      >
        {body}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
