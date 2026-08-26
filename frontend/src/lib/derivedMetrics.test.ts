import { describe, expect, it } from "vitest";
import { DerivedMetricError, evaluateExpression } from "./derivedMetrics";

const values: Record<string, number> = { engaged_sessions: 40, sessions: 100, revenue: 250, transactions: 5 };
const resolve = (key: string) => values[key] ?? null;

describe("evaluateExpression", () => {
  it("evaluates a simple division", () => {
    expect(evaluateExpression("engaged_sessions / sessions", resolve)).toBeCloseTo(0.4);
  });

  it("respects operator precedence and parentheses", () => {
    expect(evaluateExpression("revenue / transactions", resolve)).toBeCloseTo(50);
    expect(evaluateExpression("(revenue + 50) / transactions", resolve)).toBeCloseTo(60);
  });

  it("propagates unavailability instead of treating an unknown metric as 0", () => {
    expect(evaluateExpression("unknown_metric / sessions", resolve)).toBeNull();
  });

  it("returns null on division by zero rather than Infinity", () => {
    expect(evaluateExpression("sessions / 0", resolve)).toBeNull();
  });

  it("rejects syntax outside the supported arithmetic grammar", () => {
    expect(() => evaluateExpression("sessions; alert('x')", resolve)).toThrow(DerivedMetricError);
  });

  it("rejects unbalanced parentheses", () => {
    expect(() => evaluateExpression("(sessions / transactions", resolve)).toThrow(DerivedMetricError);
  });
});
