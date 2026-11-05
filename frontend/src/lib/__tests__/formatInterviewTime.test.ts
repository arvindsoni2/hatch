import { describe, expect, it } from "vitest";
import {
  browserTimeZone,
  formatInterviewTime,
  localDateTimeToUtcIso,
  parseInterviewTime,
} from "../formatInterviewTime";

describe("formatInterviewTime", () => {
  it("uses the configured display timezone and shows its abbreviation", () => {
    const formatted = formatInterviewTime("2026-11-10T12:00:00Z", "Europe/London");

    expect(formatted).toContain("12:00");
    expect(formatted).toMatch(/GMT|UTC/);
  });

  it("falls back to the browser timezone when the configured zone is null", () => {
    const zone = browserTimeZone();
    const formatted = formatInterviewTime("2026-11-10T12:00:00Z", zone);
    const abbreviation = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      timeZoneName: "short",
    })
      .formatToParts(new Date("2026-11-10T12:00:00Z"))
      .find((part) => part.type === "timeZoneName")?.value;

    expect(abbreviation).toBeTruthy();
    expect(formatted).toContain(abbreviation!);
  });

  it("treats an offset-less API time as UTC", () => {
    expect(parseInterviewTime("2026-11-20T04:30:00").toISOString()).toBe(
      "2026-11-20T04:30:00.000Z",
    );
    const formatted = formatInterviewTime("2026-11-20T04:30:00", "Asia/Kolkata");
    expect(formatted).toContain("10:00");
    expect(formatted).toMatch(/GMT\+5:30|IST/);
  });

  it("converts a datetime-local value to a UTC ISO string", () => {
    const local = "2026-11-10T14:30";
    const iso = localDateTimeToUtcIso(local);

    expect(iso.endsWith("Z")).toBe(true);
    expect(new Date(iso).getTime()).toBe(new Date(local).getTime());
  });
});
