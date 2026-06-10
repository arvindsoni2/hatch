import { describe, it, expect } from "vitest";
import { formatJobRate, formatJobRateFull } from "@/lib/currency";

describe("formatJobRate", () => {
  it("renders GBP range", () => {
    expect(formatJobRate(550, 700, "£")).toBe("£550–£700");
  });

  it("renders INR single value", () => {
    expect(formatJobRate(2000000, null, "₹")).toBe("₹2,000,000");
  });

  it("renders AED single min", () => {
    expect(formatJobRate(3000, undefined, "AED ")).toBe("AED 3,000");
  });

  it("renders EUR range", () => {
    expect(formatJobRate(80000, 100000, "€")).toBe("€80,000–€100,000");
  });

  it("returns null when both min and max are null", () => {
    expect(formatJobRate(null, null, "£")).toBeNull();
  });

  it("defaults to £ when no currency symbol given", () => {
    expect(formatJobRate(500, 700)).toBe("£500–£700");
  });
});

describe("formatJobRateFull", () => {
  it("prefers rate_text when provided", () => {
    expect(formatJobRateFull("£650/day", 550, 700, "£")).toBe("£650/day");
  });

  it("falls back to formatJobRate when rate_text is null", () => {
    expect(formatJobRateFull(null, 550, 700, "₹")).toBe("₹550–₹700");
  });

  it("returns null when no rate data", () => {
    expect(formatJobRateFull(null, null, null, "£")).toBeNull();
  });
});
