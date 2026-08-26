"""Top-N + "Others" bucketing for high-cardinality dimensions (action-plan.md
§7: "high-cardinality reports (product name, landing page) must be stored at
monthly grain with top-N plus an Others bucket"). `top_n` and the monthly-only
rule come from `query_defs.high_cardinality` / `query_defs.top_n` — never a
constant here.
"""

from __future__ import annotations

from collections import defaultdict

OTHERS_LABEL = "(Others)"


def bucket_top_n(
    rows: list[dict],
    dimension_key: str,
    metric_key_for_ranking: str,
    top_n: int,
) -> list[dict]:
    """Ranks distinct values of `dimension_key` by the sum of
    `metric_key_for_ranking`, keeps the top N, and collapses the rest into a
    single OTHERS_LABEL row per remaining group-by combination (all other
    dimensions on the row are preserved as-is for the top N; for the Others
    row, every other dimension is dropped since it no longer represents one
    entity)."""
    totals_by_value: dict[str, float] = defaultdict(float)
    for row in rows:
        value = row["dimension_values"].get(dimension_key, "(not set)")
        totals_by_value[value] += row["metric_values"].get(metric_key_for_ranking, 0.0)

    ranked = sorted(totals_by_value.items(), key=lambda kv: kv[1], reverse=True)
    top_values = {value for value, _ in ranked[:top_n]}

    kept: list[dict] = []
    others_accumulator: dict[str, float] = defaultdict(float)
    others_date_key = None

    for row in rows:
        value = row["dimension_values"].get(dimension_key, "(not set)")
        if value in top_values:
            kept.append(row)
            continue
        others_date_key = row.get("date_key", others_date_key)
        for metric, amount in row["metric_values"].items():
            others_accumulator[metric] += amount

    if others_accumulator:
        kept.append(
            {
                "date_key": others_date_key,
                "dimension_values": {dimension_key: OTHERS_LABEL},
                "metric_values": dict(others_accumulator),
            }
        )

    return kept
