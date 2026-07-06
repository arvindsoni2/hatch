import { Check, Circle } from "lucide-react";
import type { PasswordPolicy } from "@/lib/api";
import { checkPassword, FALLBACK_PASSWORD_POLICY } from "@/lib/passwordPolicy";

interface PasswordRequirementListProps {
  confirmPassword?: string;
  id: string;
  password: string;
  policy?: PasswordPolicy;
  showMatch?: boolean;
}

export function PasswordRequirementList({
  confirmPassword = "",
  id,
  password,
  policy = FALLBACK_PASSWORD_POLICY,
  showMatch = false,
}: PasswordRequirementListProps) {
  const checks = checkPassword(password, policy);
  const requirements = [
    { met: checks.length, text: `${policy.min_length}-${policy.max_length} characters` },
    { met: checks.letter, text: "Includes a letter" },
    { met: checks.number, text: "Includes a number" },
    { met: checks.edgeWhitespace, text: "No spaces at the beginning or end" },
    ...(showMatch ? [{ met: password.length > 0 && password === confirmPassword, text: "Passwords match" }] : []),
  ];

  return (
    <div aria-live="polite" className="rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3" id={id}>
      <p className="text-xs font-semibold text-[var(--text)]">Password requirements</p>
      <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
        {requirements.map(({ met, text }) => (
          <li className="flex items-center gap-2 text-xs" key={text} style={{ color: met ? "var(--success)" : "var(--text-muted)" }}>
            {met ? <Check aria-hidden="true" className="h-3.5 w-3.5" /> : <Circle aria-hidden="true" className="h-3.5 w-3.5" />}
            <span>{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
