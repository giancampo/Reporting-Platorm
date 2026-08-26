"""Connector plugin interface.

action-plan.md §4: "Connectors are plugins behind a common interface. Adding
Google Ads or Shopify means adding a file, not modifying the orchestrator."

Every connector receives a `QueryDef` (loaded from the `query_defs` table,
never hardcoded) and a `Connection` (loaded from `connections`), and returns
rows already in canonical field names — a connector owns the translation from
its source's native vocabulary to the platform's canonical schema
(action-plan.md §6). `main.py` never knows a source-specific field name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Connection:
    id: str
    project_id: str
    source: str
    resource_id: str
    secret_ref: str | None
    metadata: dict


@dataclass(frozen=True)
class QueryDef:
    id: str
    project_id: str | None
    source: str
    report_key: str
    dimensions: list[str]
    metrics: list[str]
    granularity: str  # 'daily' | 'monthly'
    high_cardinality: bool
    top_n: int


@dataclass(frozen=True)
class ExtractedRow:
    """One row of canonical data. `dimension_values` keys are canonical
    dimension names; `metric_values` keys are canonical metric names.
    Everything downstream (bot filter, cardinality bucketing, storage adapter)
    operates only on this shape, never on a source-native one."""

    date_key: date
    dimension_values: dict[str, str] = field(default_factory=dict)
    metric_values: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    rows: list[ExtractedRow]
    # Dimensionless total for the same metrics/period, queried separately.
    # Required by the "never sum a breakdown" rule (action-plan.md §7, §9) —
    # a connector that cannot produce this must return None and the caller
    # flags the dataset as unreconciled rather than silently trusting a sum.
    totals: dict[str, float] | None
    reporting_identity: str | None = None  # 'blended' | 'observed' | None if N/A


class Connector(ABC):
    """One instance per (project, connection). Implementations must not
    perform any transformation beyond native → canonical renaming: bot
    filtering, cardinality bucketing and exclusion rules are applied
    uniformly downstream in `transform/`, not duplicated per connector."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    @abstractmethod
    def extract(
        self, query_def: QueryDef, start: date, end: date
    ) -> ExtractionResult:
        """Return canonical rows for [start, end] inclusive, plus the
        dimensionless total for the same window when the source supports it."""
        raise NotImplementedError

    def supports_identity_switch(self) -> bool:
        """True only for sources where modeled/observed reporting identity
        applies (action-plan.md §7). Default: not applicable."""
        return False
