import { describe, expect, it } from "vitest";
import { aggregateMetric, buildMetricDictionaryIndex, groupAndAggregate } from "./aggregation";
import type { MetricDictionaryEntry, ReportRow } from "./types";

const DICTIONARY: MetricDictionaryEntry[] = [
  { metric_key: "sessions", additivity: "sum", unit: "count", numerator_key: null, denominator_key: null, valid_from: "1970-01-01", valid_to: null },
  { metric_key: "engaged_sessions", additivity: "sum", unit: "count", numerator_key: null, denominator_key: null, valid_from: "1970-01-01", valid_to: null },
  {
    metric_key: "engagement_rate",
    additivity: "ratio",
    unit: "percent",
    numerator_key: "engaged_sessions",
    denominator_key: "sessions",
    valid_from: "1970-01-01",
    valid_to: null,
  },
  { metric_key: "active_users", additivity: "unique", unit: "count", numerator_key: null, denominator_key: null, valid_from: "1970-01-01", valid_to: null },
];

const dict = buildMetricDictionaryIndex(DICTIONARY);

const ROWS: ReportRow[] = [
  { date_key: "2026-08-01", dimension_values: { source_medium: "google / organic" }, metric_values: { sessions: 100, engaged_sessions: 40 } },
  { date_key: "2026-08-01", dimension_values: { source_medium: "direct / (none)" }, metric_values: { sessions: 50, engaged_sessions: 45 } },
];

describe("aggregateMetric", () => {
  it("sums a 'sum' metric across rows", () => {
    expect(aggregateMetric("sessions", ROWS, dict)).toEqual({ value: 150, available: true });
  });

  it("computes a ratio from summed numerator/denominator, not a mean of per-row ratios", () => {
    // Per-row ratios are 0.4 and 0.9 -> naive mean would be 0.65.
    // Correct: (40 + 45) / (100 + 50) = 85 / 150.
    const result = aggregateMetric("engagement_rate", ROWS, dict);
    expect(result.available).toBe(true);
    expect(result.value).toBeCloseTo(85 / 150, 10);
  });

  it("returns unavailable for a ratio metric when the denominator sums to zero", () => {
    const zeroRows: ReportRow[] = [
      { date_key: "2026-08-01", dimension_values: {}, metric_values: { sessions: 0, engaged_sessions: 0 } },
    ];
    expect(aggregateMetric("engagement_rate", zeroRows, dict)).toEqual({ value: null, available: false });
  });

  it("throws when the metric has no dictionary entry, per the fail-loudly config-validation rule", () => {
    expect(() => aggregateMetric("unknown_metric", ROWS, dict)).toThrow(/No metric_dictionary entry/);
  });

  it("declares a 'unique' metric unavailable when combining more than one row", () => {
    const result = aggregateMetric("active_users", ROWS, dict);
    expect(result).toEqual({ value: null, available: false });
  });

  it("passes through a 'unique' metric's single value untouched", () => {
    const singleRow: ReportRow[] = [{ date_key: "2026-08-01", dimension_values: {}, metric_values: { active_users: 42 } }];
    expect(aggregateMetric("active_users", singleRow, dict)).toEqual({ value: 42, available: true });
  });
});

describe("groupAndAggregate", () => {
  it("groups by dimension and aggregates each metric per group", () => {
    const result = groupAndAggregate(ROWS, ["source_medium"], ["sessions"], dict);
    expect(result).toHaveLength(2);
    const google = result.find((r) => r.dimensions.source_medium === "google / organic");
    expect(google?.metrics.sessions).toEqual({ value: 100, available: true });
  });
});
