/**
 * Display and submit real-interview times in UTC storage + display timezone.
 */

const OFFSET_SUFFIX = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Parse an API time; offset-less strings are UTC (spec §7.5). */
export function parseInterviewTime(value: string | Date): Date {
  if (value instanceof Date) return value;
  const normalized = OFFSET_SUFFIX.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}

export function formatInterviewTime(value: string | Date, timeZone: string): string {
  const date = parseInterviewTime(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone,
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function formatInterviewClock(value: string | Date, timeZone: string): string {
  const date = parseInterviewTime(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

/** Convert a datetime-local value (browser local) to an ISO UTC string. */
export function localDateTimeToUtcIso(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error("invalid local datetime");
  }
  return date.toISOString();
}
