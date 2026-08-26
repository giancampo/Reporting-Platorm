import ReactECharts from "echarts-for-react";
import type { MetricDictionaryIndex } from "../lib/aggregation";
import { groupAndAggregate } from "../lib/aggregation";
import { formatNumber } from "../lib/format";
import { useUiLocale } from "../lib/useLocale";
import type { ReportRow } from "../lib/types";

/** Renders a chart purely from a report_defs block + the already-fetched
 * document rows — no chart is ever built from a hardcoded metric/dimension
 * list (action-plan.md §4). */
export function ChartBlock(props: {
  rows: ReportRow[];
  dimension: string;
  metric: string;
  dictionary: MetricDictionaryIndex;
}) {
  const locale = useUiLocale();
  const grouped = groupAndAggregate(props.rows, [props.dimension], [props.metric], props.dictionary);

  const categories = grouped.map((g) => g.dimensions[props.dimension]);
  const values = grouped.map((g) => {
    const agg = g.metrics[props.metric];
    return agg?.available ? agg.value : null;
  });

  const option = {
    xAxis: { type: "category", data: categories },
    yAxis: { type: "value" },
    series: [{ type: "bar", data: values }],
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: number) => formatNumber(value, locale),
    },
  };

  return <ReactECharts option={option} style={{ height: 320 }} />;
}
