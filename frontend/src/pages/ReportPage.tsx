import { useEffect, useState } from "react";
import { ChartBlock } from "../components/ChartBlock";
import { FreshnessIndicator } from "../components/FreshnessIndicator";
import { resolveLocalizedText } from "../i18n";
import type { MetricDictionaryIndex } from "../lib/aggregation";
import { fetchReportDocument } from "../lib/reportData";
import type { LocalizedText, ReportDocument } from "../lib/types";
import { useReportLocale } from "../lib/useLocale";

export interface ReportBlockDef {
  type: "chart";
  dataset: string; // report_key
  source: string;
  granularity: "daily" | "monthly";
  dimension: string;
  metric: string;
}

/** Renders purely from a `report_defs` row — the page's structure (which
 * blocks, which datasets, order) is entirely config-driven (action-plan.md
 * §4, §14: "Adding a page is a report_defs record"). */
export function ReportPage(props: {
  projectSlug: string;
  pageTitle: LocalizedText;
  blocks: ReportBlockDef[];
  period: string;
  dictionary: MetricDictionaryIndex;
}) {
  const reportLocale = useReportLocale();
  const [documents, setDocuments] = useState<Record<string, ReportDocument>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all(
      props.blocks.map((block) =>
        fetchReportDocument({
          projectSlug: props.projectSlug,
          source: block.source,
          reportKey: block.dataset,
          granularity: block.granularity,
          period: props.period,
        }).then((doc) => [block.dataset, doc] as const)
      )
    )
      .then((entries) => {
        if (!cancelled) setDocuments(Object.fromEntries(entries));
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [props.projectSlug, props.period, props.blocks]);

  const firstDoc = Object.values(documents)[0];

  return (
    <section>
      <h1>{resolveLocalizedText(props.pageTitle, reportLocale)}</h1>
      {firstDoc && <FreshnessIndicator generatedAt={firstDoc.generated_at} />}
      {error && <p role="alert">{error}</p>}
      {props.blocks.map((block, i) => {
        const doc = documents[block.dataset];
        if (!doc) return null;
        return (
          <ChartBlock
            key={i}
            rows={doc.rows}
            dimension={block.dimension}
            metric={block.metric}
            dictionary={props.dictionary}
          />
        );
      })}
    </section>
  );
}
