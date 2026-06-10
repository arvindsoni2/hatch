/**
 * Currency formatting helpers driven by locale config.
 * Use `formatJobRate` everywhere instead of hardcoded `£`.
 */

/**
 * Format a min/max rate pair using the locale's currency symbol.
 * Prefers `Intl.NumberFormat` where supported.
 */
export function formatJobRate(
  min: number | null | undefined,
  max: number | null | undefined,
  currencySymbol: string = "£",
): string | null {
  if (!min && !max) return null;
  const fmt = (n: number) =>
    n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (min && max && min !== max)
    return `${currencySymbol}${fmt(min)}–${currencySymbol}${fmt(max)}`;
  if (min) return `${currencySymbol}${fmt(min)}`;
  if (max) return `${currencySymbol}${fmt(max)}`;
  return null;
}

/**
 * Return a display string for a job's rate, preferring the server-formatted
 * `rate_text` and falling back to formatJobRate.
 */
export function formatJobRateFull(
  rateText: string | null | undefined,
  min: number | null | undefined,
  max: number | null | undefined,
  currencySymbol: string = "£",
): string | null {
  if (rateText) return rateText;
  return formatJobRate(min, max, currencySymbol);
}
