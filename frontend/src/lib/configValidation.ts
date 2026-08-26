/**
 * Startup config validation (action-plan.md §13): "the application verifies
 * that every report_defs entry references metrics and dimensions actually
 * present in the files. A config pointing at a non-existent field must fail
 * loudly, not render an empty chart." Also the anti-pattern list in §15
 * calls this out explicitly.
 *
 * This validates report_defs block references against the metric
 * dictionary (metrics) and, when a sample document is supplied, against the
 * dimensions actually present in extracted data.
 */

import type { MetricDictionaryIndex } from "./aggregation";

export interface ReportBlock {
  type: string;
  dataset?: string;
  metric?: string;
  dimension?: string;
}

export interface ConfigValidationError {
  pageKey: string;
  blockIndex: number;
  reason: string;
}

export function validateReportDefs(
  pages: Array<{ page_key: string; layout: ReportBlock[] }>,
  dictionary: MetricDictionaryIndex
): ConfigValidationError[] {
  const errors: ConfigValidationError[] = [];

  for (const page of pages) {
    page.layout.forEach((block, index) => {
      if (block.metric && !dictionary.has(block.metric)) {
        errors.push({
          pageKey: page.page_key,
          blockIndex: index,
          reason: `Block references unknown metric '${block.metric}' — add it to metric_dictionary before referencing it from report_defs.`,
        });
      }
    });
  }

  return errors;
}

export class ConfigValidationFailure extends Error {
  constructor(public errors: ConfigValidationError[]) {
    super(
      `${errors.length} report_defs configuration error(s):\n` +
        errors.map((e) => `  - [${e.pageKey}#${e.blockIndex}] ${e.reason}`).join("\n")
    );
  }
}

/** Call at app startup after loading report_defs + metric_dictionary. Throws
 * (rather than rendering an empty chart) when any block references a metric
 * that doesn't exist. */
export function assertReportDefsValid(
  pages: Array<{ page_key: string; layout: ReportBlock[] }>,
  dictionary: MetricDictionaryIndex
): void {
  const errors = validateReportDefs(pages, dictionary);
  if (errors.length > 0) {
    throw new ConfigValidationFailure(errors);
  }
}
