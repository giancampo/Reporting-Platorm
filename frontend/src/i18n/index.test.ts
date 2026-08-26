import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveLocalizedText, t } from "./index";

describe("t (static UI strings)", () => {
  it("returns the English string for the 'en' locale", () => {
    expect(t("en", "nav.overview")).toBe("Overview");
  });

  it("returns the Italian translation when present", () => {
    expect(t("it", "nav.overview")).toBe("Panoramica");
  });

  it("falls back to English when the Italian translation is missing, never blank", () => {
    // 'print.generatedAt' exists only in en.json.
    expect(t("it", "print.generatedAt", { date: "2026-08-26" })).toBe("Report generated on 2026-08-26");
  });

  it("interpolates {token} params", () => {
    expect(t("en", "freshness.lastUpdated", { date: "2026-08-26" })).toBe("Last updated 2026-08-26");
  });

  it("throws for a key missing even from the English reference file", () => {
    expect(() => t("en", "this.key.does.not.exist")).toThrow(/Missing 'en' translation/);
  });
});

describe("t fallback warning", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("warns once per missing key when falling back", () => {
    // A key not touched by any other test in this file — MISSING_KEYS_WARNED
    // is module-level state that persists across tests, so reusing a key
    // another test already triggered would make this assertion flaky.
    const warnSpy = vi.spyOn(console, "warn");
    t("it", "admin.projects.new");
    t("it", "admin.projects.new");
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });
});

describe("resolveLocalizedText (analyst-authored content)", () => {
  it("prefers 'it' when present and locale is 'it'", () => {
    expect(resolveLocalizedText({ en: "Overview", it: "Panoramica" }, "it")).toBe("Panoramica");
  });

  it("falls back to 'en' when 'it' is missing, never machine-translating", () => {
    expect(resolveLocalizedText({ en: "Overview" }, "it")).toBe("Overview");
  });

  it("uses 'en' for the 'en' locale even if 'it' is present", () => {
    expect(resolveLocalizedText({ en: "Overview", it: "Panoramica" }, "en")).toBe("Overview");
  });
});
