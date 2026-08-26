"""Ties the three layers together (action-plan.md §11): computation -> rules
-> templates, plus the partial-period guard and the metric-dictionary
definition-change guard. This is the module the ETL/a Supabase Edge Function
calls to produce one `comments` draft row per report page/period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .computation import compute_change, z_score_outliers
from .metric_dictionary import MetricDictionaryEntry, definition_changed_between
from .partial_period import PeriodWindow, build_comparison_basis
from .rules import CommentRule, RuleContext, select_matching_rules
from .templates import render_template

DEFINITION_CHANGE_NOTE = {
    "en": "Note: the definition of {metric_key} changed during this comparison window; the figures above may not be like-for-like.",
    "it": "Nota: la definizione di {metric_key} è cambiata durante questo periodo di confronto; i valori sopra potrebbero non essere direttamente confrontabili.",
}

PARTIAL_PERIOD_NOTE = {
    "en": "This period is still in progress; the comparison uses an equal number of elapsed days.",
    "it": "Questo periodo è ancora in corso; il confronto utilizza lo stesso numero di giorni trascorsi.",
}


@dataclass(frozen=True)
class GeneratedComment:
    metric_key: str
    text: str
    is_partial_period_comparison: bool
    definition_changed: bool


def generate_comment(
    *,
    metric_key: str,
    current_period: PeriodWindow,
    comparison_period: PeriodWindow,
    current_value: float,
    comparison_value: float,
    contributor_deltas: dict[str, float],
    recent_weekly_values: list[float],
    rules: list[CommentRule],
    metric_dictionary_entries: list[MetricDictionaryEntry],
    locale: str,
    today: date,
    period_seed: str,
) -> GeneratedComment:
    """Single-metric, single-page comment. The caller is responsible for
    fetching `rules` scoped to (project, metric) and `metric_dictionary_entries`
    scoped to `metric_key` before calling this — this function does no I/O,
    which is what makes the snapshot tests in tests/test_snapshots.py stable."""

    _, was_truncated = build_comparison_basis(current_period, comparison_period, today)

    change = compute_change(current_value, comparison_value)
    total_delta = sum(contributor_deltas.values())
    top_contributor = None
    top_contributor_share = None
    if contributor_deltas and total_delta != 0:
        top_contributor = max(contributor_deltas, key=lambda k: abs(contributor_deltas[k]))
        top_contributor_share = contributor_deltas[top_contributor] / total_delta

    outlier_check = z_score_outliers(current_value, recent_weekly_values)

    context = RuleContext(
        pct_change=change.pct_change,
        absolute_change=change.absolute_change,
        top_contributor=top_contributor,
        top_contributor_share=top_contributor_share,
        is_outlier=outlier_check.is_outlier,
        z_score=outlier_check.z_score,
    )

    matched = select_matching_rules(rules, context)
    if not matched:
        text = ""
    else:
        top_rule = matched[0]
        tokens = {
            "metric_key": metric_key,
            "pct_change": f"{change.pct_change:.1%}" if change.pct_change is not None else "n/a",
            "top_contributor": top_contributor or "n/a",
        }
        text = render_template(top_rule, locale, period_seed, tokens)

    definition_changed = definition_changed_between(
        metric_dictionary_entries, metric_key, comparison_period.start, current_period.end
    )

    notes: list[str] = []
    if was_truncated:
        notes.append(PARTIAL_PERIOD_NOTE.get(locale, PARTIAL_PERIOD_NOTE["en"]))
    if definition_changed:
        notes.append(DEFINITION_CHANGE_NOTE.get(locale, DEFINITION_CHANGE_NOTE["en"]).format(metric_key=metric_key))

    full_text = " ".join([text, *notes]).strip()

    return GeneratedComment(
        metric_key=metric_key,
        text=full_text,
        is_partial_period_comparison=was_truncated,
        definition_changed=definition_changed,
    )
