"use client";
import { useRouter } from "next/navigation";
import { HatchIcon } from "./HatchIcon";

interface BackButtonProps {
  label?: string;
  href?: string;
}

export function BackButton({ label = "Back", href }: BackButtonProps) {
  const router = useRouter();
  const handleClick = () => (href ? router.push(href) : router.back());

  return (
    <button
      onClick={handleClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 12px 6px 8px",
        borderRadius: 8,
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        color: "var(--text-dim)",
        fontSize: 13,
        fontWeight: 500,
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.background = "var(--surface)";
        (e.currentTarget as HTMLElement).style.color = "var(--text)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.background = "var(--surface-2)";
        (e.currentTarget as HTMLElement).style.color = "var(--text-dim)";
      }}
    >
      <HatchIcon name="chevronL" size={14} color="currentColor" strokeWidth={2.5} />
      {label}
    </button>
  );
}
