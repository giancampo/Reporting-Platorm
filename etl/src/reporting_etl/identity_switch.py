"""Modeled vs observed reporting identity (action-plan.md §7).

This is a PROPERTY-LEVEL change via the GA4 Admin API (v1alpha), not a
query-level one: while the identity is switched, anyone else reading that
property sees the switched value too. Every requirement below exists to
bound that blast radius:

- Atomic sequence per property: read+record initial identity, switch, run
  every query that needs the switched state, restore — never interleaved
  with another property's switch.
- Guaranteed restore even on crash: restore lives in a `finally` block, and
  `verify_and_recover_stale_switches()` must run at the start of every ETL
  invocation to catch a property left mid-switch by a previous crashed run.
- Narrowest possible window: only the queries that need the non-resting
  identity are run while switched.
- Per-project resting identity, from `projects.resting_reporting_identity`,
  never a hardcoded default.
- Explicit fallback: the Admin API is alpha and can change without notice.
  If the switch itself fails, the resting-identity extraction still runs and
  the caller must flag the comparison as unavailable for that day rather
  than fabricate a gap.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol


class ReportingIdentityError(RuntimeError):
    pass


class AdminApiClient(Protocol):
    def get_reporting_identity(self, property_id: str) -> str: ...
    def set_reporting_identity(self, property_id: str, identity: str) -> None: ...


@dataclass
class IdentitySwitchOutcome:
    property_id: str
    initial_identity: str
    target_identity: str
    final_identity: str
    restore_ok: bool
    switch_succeeded: bool


class SwitchStateStore(Protocol):
    """Persistence for in-progress switches, backed by `etl_runs` in
    production. Lets `verify_and_recover_stale_switches` detect a property a
    prior crashed run left mid-switch."""

    def record_switch_start(self, property_id: str, initial_identity: str, target_identity: str) -> None: ...
    def record_switch_end(self, property_id: str, final_identity: str, restore_ok: bool) -> None: ...
    def get_open_switches(self) -> list[tuple[str, str]]: ...  # (property_id, initial_identity)


@contextmanager
def reporting_identity(
    admin_client: AdminApiClient,
    state_store: SwitchStateStore,
    property_id: str,
    target_identity: str,
) -> Iterator[IdentitySwitchOutcome]:
    """Switches `property_id` to `target_identity` for the duration of the
    `with` block and restores the identity it had beforehand, guaranteed via
    `finally` even if the caller's queries raise. Yields an outcome object
    whose `switch_succeeded` field the caller must check before running any
    query that depends on the switched state — on failure, run only the
    resting-identity extraction and flag the comparison unavailable."""

    initial_identity = admin_client.get_reporting_identity(property_id)
    outcome = IdentitySwitchOutcome(
        property_id=property_id,
        initial_identity=initial_identity,
        target_identity=target_identity,
        final_identity=initial_identity,
        restore_ok=False,
        switch_succeeded=False,
    )

    if initial_identity == target_identity:
        # Already in the desired state: nothing to switch or restore.
        outcome.switch_succeeded = True
        outcome.restore_ok = True
        yield outcome
        return

    state_store.record_switch_start(property_id, initial_identity, target_identity)
    try:
        # This inner try/except covers ONLY the switch call itself. It must not
        # also wrap the `yield outcome` that hands control to the caller's
        # `with` body — a caller exception thrown in at that yield would
        # otherwise be mis-caught here as a switch failure and, worse, force a
        # second yield, which contextlib rejects ("generator didn't stop after
        # throw()"). Restoring is always the outer `finally`'s job regardless
        # of which branch below runs.
        try:
            admin_client.set_reporting_identity(property_id, target_identity)
        except Exception:
            outcome.switch_succeeded = False
            yield outcome
            raise
        outcome.switch_succeeded = True
        yield outcome
    finally:
        try:
            admin_client.set_reporting_identity(property_id, initial_identity)
            outcome.final_identity = initial_identity
            outcome.restore_ok = True
        except Exception:
            outcome.restore_ok = False
            outcome.final_identity = target_identity if outcome.switch_succeeded else initial_identity
        state_store.record_switch_end(property_id, outcome.final_identity, outcome.restore_ok)


def verify_and_recover_stale_switches(
    admin_client: AdminApiClient, state_store: SwitchStateStore
) -> list[IdentitySwitchOutcome]:
    """Must run at the start of every ETL invocation, before any property is
    switched by this run. Restores any property a previous crashed run left
    in the wrong state, and reports what it found so it lands in `etl_runs`
    rather than being silently corrected."""
    recovered: list[IdentitySwitchOutcome] = []
    for property_id, initial_identity in state_store.get_open_switches():
        current = admin_client.get_reporting_identity(property_id)
        restore_ok = True
        if current != initial_identity:
            try:
                admin_client.set_reporting_identity(property_id, initial_identity)
            except Exception:
                restore_ok = False
        state_store.record_switch_end(property_id, initial_identity if restore_ok else current, restore_ok)
        recovered.append(
            IdentitySwitchOutcome(
                property_id=property_id,
                initial_identity=initial_identity,
                target_identity=current,
                final_identity=initial_identity if restore_ok else current,
                restore_ok=restore_ok,
                switch_succeeded=True,
            )
        )
    return recovered
