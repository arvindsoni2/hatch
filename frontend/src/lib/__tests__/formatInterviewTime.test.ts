import { afterEach, describe, expect, it } from "vitest";
import {
  formatInterviewTime,
  localDateTimeToUtcIso,
  resolveDisplayTimeZone,
} from "../formatInterviewTime";

const OLD_TIMEZONE = process.env.HATCH_DISPLAY_TIMEZONE;

describe("formatInterviewTime", () => {
  afterEach(() => {
    if (OLD_TIMEZONE === undefined) {
      delete process.env.HATCH_DISPLAY_TIMEZONE;
    } else {
      process.env.HATCH_DISPLAY_TIMEZONE = OLD_TIMEZONE;
    }
  });

  it("uses the configured display timezone and shows its abbreviation", () => {
    process.env.HATCH_DISPLAY_TIMEZONE = "Europe/London";

    const formatted = formatInterviewTime("2026-11-10T12:00:00Z");

    expect(resolveDisplayTimeZone()).toBe("Europe/London");
    expect(formatted).toContain("12:00");
    expect(formatted).toMatch(/GMT|UTC/);
  });

  it("falls back to the browser timezone when no display timezone is set", () => {
    delete process.env.HATCH_DISPLAY_TIMEZONE;

    expect(formatInterviewTime("2026-11-10T12:00:00Z")).toContain("2026");
  });

  it("converts a datetime-local value to a UTC ISO string", () => {
    const local = "2026-11-10T14:30";
    const iso = localDateTimeToUtcIso(local);

    expect(iso.endsWith("Z")).toBe(true);
    expect(new Date(iso).getTime()).toBe(new Date(local).getTime());
  });
});
