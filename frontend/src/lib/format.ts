/**
 * Locale-driven formatting (action-plan.md §5): "Numbers, dates and
 * currencies must be formatted according to the active locale... Handle it
 * with the browser's native internationalisation APIs, never with
 * hand-rolled formatting." `locale` here is always a BCP-47 tag derived from
 * either the user's UI-language preference or the project's report_language
 * — callers decide which axis applies (§5's "two axes not to be confused").
 */

export function formatNumber(value: number, locale: string, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale, options).format(value);
}

export function formatPercent(value: number, locale: string, fractionDigits = 1): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** `currencyCode` comes from `projects.currency_code` (ISO 4217) — never
 * converted, per §7's "currency is the property's... any conversion is a
 * read-time derived metric, with rate and date made explicit." */
export function formatCurrency(value: number, locale: string, currencyCode: string): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency: currencyCode }).format(value);
}

export function formatDate(isoDate: string, locale: string, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(locale, options).format(new Date(isoDate));
}
