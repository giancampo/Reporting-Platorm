"""Row-level exclusion rules from the `exclusion_rules` config table
(action-plan.md §9: "they produce a separate excluded file; they delete
nothing"). Rules are simple boolean expressions evaluated against a row's
canonical dimension/metric values — kept intentionally small (no arbitrary
code execution) since these are analyst-authored config, not developer code.
"""

from __future__ import annotations

import ast
import operator

_ALLOWED_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
}
_ALLOWED_BOOL_OPS = {ast.And: all, ast.Or: any}


class ExclusionRuleError(ValueError):
    pass


def _eval_node(node: ast.AST, row_context: dict) -> object:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, row_context)
    if isinstance(node, ast.BoolOp):
        combiner = _ALLOWED_BOOL_OPS[type(node.op)]
        return combiner(_eval_node(v, row_context) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, row_context)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left = _eval_node(node.left, row_context)
        right = _eval_node(node.comparators[0], row_context)
        op = _ALLOWED_COMPARISONS.get(type(node.ops[0]))
        if op is None:
            raise ExclusionRuleError(f"Unsupported comparison operator: {node.ops[0]}")
        return op(left, right)
    if isinstance(node, ast.Name):
        if node.id not in row_context:
            raise ExclusionRuleError(f"Unknown field '{node.id}' in exclusion rule.")
        return row_context[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    raise ExclusionRuleError(f"Unsupported expression element: {ast.dump(node)}")


def evaluate_filter(expression: str, row: dict) -> bool:
    """`expression` example: "device_category == 'desktop' and country == 'XX'".
    `row` is the canonical dict: dimension_values merged with metric_values."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExclusionRuleError(f"Invalid exclusion rule expression: {expression!r}") from exc

    context = {**row.get("dimension_values", {}), **row.get("metric_values", {})}
    return bool(_eval_node(tree, context))


def apply_exclusion_rules(rows: list[dict], rule_expressions: list[str]) -> tuple[list[dict], list[dict]]:
    """Returns (kept, excluded). A row matching ANY active rule is excluded."""
    if not rule_expressions:
        return rows, []

    kept: list[dict] = []
    excluded: list[dict] = []
    for row in rows:
        if any(evaluate_filter(expr, row) for expr in rule_expressions):
            excluded.append(row)
        else:
            kept.append(row)
    return kept, excluded
