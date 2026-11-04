/**
 * Display and submit real-interview times in UTC storage + display timezone.
 */

export function resolveDisplayTimeZone(): string {
  const configured =
    process.env.NEXT_PUBLIC_HATCH_DISPLAY_TIMEZONE ||
    process.env.HATCH_DISPLAY_TIMEZONE;
  if (configured) {
    try {
      new Intl.DateTimeFormat("en-GB", { timeZone: configured }).format();
      return configured;
    } catch {
      // Fall through to the browser zone.
    }
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Convert a datetime-local value (browser local) to an ISO UTC string. */
export function localDateTimeToUtcIso(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error("invalid local datetime");
  }
  return date.toISOString();
}

/** Show a stored UTC time in the display timezone, including its abbreviation. */
export function formatInterviewTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolveDisplayTimeZone(),
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}
