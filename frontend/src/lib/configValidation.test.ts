import { describe, expect, it } from "vitest";
import { buildMetricDictionaryIndex } from "./aggregation";
import { assertReportDefsValid, validateReportDefs } from "./configValidation";
import type { MetricDictionaryEntry } from "./types";

const dict = buildMetricDictionaryIndex([
  { metric_key: "sessions", additivity: "sum", unit: null, numerator_key: null, denominator_key: null, valid_from: "1970-01-01", valid_to: null },
] satisfies MetricDictionaryEntry[]);

describe("validateReportDefs", () => {
  it("passes when every referenced metric exists in the dictionary", () => {
    const pages = [{ page_key: "overview", layout: [{ type: "chart", metric: "sessions" }] }];
    expect(validateReportDefs(pages, dict)).toEqual([]);
  });

  it("flags a block referencing a metric absent from metric_dictionary", () => {
    const pages = [{ page_key: "overview", layout: [{ type: "chart", metric: "made_up_metric" }] }];
    const errors = validateReportDefs(pages, dict);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.reason).toMatch(/made_up_metric/);
  });
});

describe("assertReportDefsValid", () => {
  it("throws loudly instead of allowing a silent empty chart", () => {
    const pages = [{ page_key: "overview", layout: [{ type: "chart", metric: "nope" }] }];
    expect(() => assertReportDefsValid(pages, dict)).toThrow(/report_defs configuration error/);
  });

  it("does not throw for valid config", () => {
    const pages = [{ page_key: "overview", layout: [{ type: "chart", metric: "sessions" }] }];
    expect(() => assertReportDefsValid(pages, dict)).not.toThrow();
  });
});
