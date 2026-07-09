import type { PasswordPolicy } from "@/lib/api";

export const FALLBACK_PASSWORD_POLICY: PasswordPolicy = {
  min_length: 12,
  max_length: 128,
  require_letter: true,
  require_number: true,
  require_symbol: true,
  reject_edge_whitespace: true,
};

export interface PasswordChecks {
  length: boolean;
  letter: boolean;
  number: boolean;
  symbol: boolean;
  edgeWhitespace: boolean;
}

export function checkPassword(
  password: string,
  policy: PasswordPolicy = FALLBACK_PASSWORD_POLICY,
): PasswordChecks {
  return {
    length: password.length >= policy.min_length && password.length <= policy.max_length,
    letter: !policy.require_letter || /[A-Za-z]/.test(password),
    number: !policy.require_number || /\d/.test(password),
    symbol: policy.require_symbol === false || /[^A-Za-z0-9\s]/.test(password),
    edgeWhitespace:
      password.length > 0
      && (!policy.reject_edge_whitespace || password === password.trim()),
  };
}

export function isPasswordValid(
  password: string,
  policy: PasswordPolicy = FALLBACK_PASSWORD_POLICY,
): boolean {
  return Object.values(checkPassword(password, policy)).every(Boolean);
}

export function passwordError(
  password: string,
  policy: PasswordPolicy = FALLBACK_PASSWORD_POLICY,
): string | undefined {
  const checks = checkPassword(password, policy);
  if (!checks.length) {
    return `Use ${policy.min_length}-${policy.max_length} characters.`;
  }
  if (!checks.letter) return "Include at least one letter.";
  if (!checks.number) return "Include at least one number.";
  if (!checks.symbol) return "Include at least one symbol or punctuation mark.";
  if (!checks.edgeWhitespace) return "Remove spaces from the beginning and end.";
  return undefined;
}
