"""Layer 2 of the comment engine (action-plan.md §11): thresholds and
priorities loaded from the `comment_rules` config table, editable without a
deploy. Every rule's `condition` is a small typed dict, not code — analyst
edits happen in the config table, not in a Python file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommentRule:
    rule_key: str
    metric_key: str
    condition: dict[str, Any]  # e.g. {"op": "abs_pct_change_gt", "value": 0.30}
    priority: int
    templates: dict[str, list[str]]  # locale -> variant strings, "en" mandatory


@dataclass(frozen=True)
class RuleContext:
    """Everything a condition might reference, precomputed by computation.py.
    Kept flat and explicit rather than a generic dict so a missing key
    fails fast with a clear KeyError instead of silently evaluating False."""

    pct_change: float | None
    absolute_change: float
    top_contributor: str | None
    top_contributor_share: float | None
    is_outlier: bool
    z_score: float | None


class UnsupportedConditionError(ValueError):
    pass


def evaluate_condition(condition: dict[str, Any], context: RuleContext) -> bool:
    op = condition.get("op")

    if op == "abs_pct_change_gt":
        return context.pct_change is not None and abs(context.pct_change) > condition["value"]
    if op == "abs_pct_change_lte":
        # The doc's "within ±3%, call it stable" example.
        return context.pct_change is not None and abs(context.pct_change) <= condition["value"]
    if op == "contributor_share_gt":
        return context.top_contributor_share is not None and context.top_contributor_share > condition["value"]
    if op == "is_outlier":
        return context.is_outlier
    if op == "pct_change_undefined":
        # previous_value was 0 — no meaningful percentage exists.
        return context.pct_change is None

    raise UnsupportedConditionError(f"Unknown condition op: {op!r}")


def select_matching_rules(rules: list[CommentRule], context: RuleContext) -> list[CommentRule]:
    """Returns rules whose condition matches, highest priority number first
    (priority is a rank, not a weight — the caller typically renders only
    the top match per metric to avoid contradictory sentences)."""
    matched = [rule for rule in rules if evaluate_condition(rule.condition, context)]
    return sorted(matched, key=lambda r: r.priority, reverse=True)
