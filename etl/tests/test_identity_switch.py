import pytest

from reporting_etl.identity_switch import reporting_identity, verify_and_recover_stale_switches


class FakeAdminClient:
    def __init__(self, initial_state: dict[str, str], fail_on_set_to: set[str] | None = None):
        self.state = dict(initial_state)
        self._fail_on_set_to = fail_on_set_to or set()
        self.set_calls: list[tuple[str, str]] = []

    def get_reporting_identity(self, property_id: str) -> str:
        return self.state[property_id]

    def set_reporting_identity(self, property_id: str, identity: str) -> None:
        self.set_calls.append((property_id, identity))
        if identity in self._fail_on_set_to:
            raise RuntimeError(f"Admin API rejected switch to {identity}")
        self.state[property_id] = identity


class FakeStateStore:
    def __init__(self):
        self.open_switches: dict[str, str] = {}
        self.ended: list[tuple[str, str, bool]] = []

    def record_switch_start(self, property_id, initial_identity, target_identity):
        self.open_switches[property_id] = initial_identity

    def record_switch_end(self, property_id, final_identity, restore_ok):
        self.open_switches.pop(property_id, None)
        self.ended.append((property_id, final_identity, restore_ok))

    def get_open_switches(self):
        return list(self.open_switches.items())


def test_switch_and_restore_happy_path():
    admin = FakeAdminClient({"p1": "blended"})
    store = FakeStateStore()

    with reporting_identity(admin, store, "p1", "observed") as outcome:
        assert outcome.switch_succeeded
        assert admin.get_reporting_identity("p1") == "observed"

    assert admin.get_reporting_identity("p1") == "blended"  # restored
    assert outcome.restore_ok
    assert store.open_switches == {}  # no leftover open switch


def test_restore_runs_even_if_caller_raises():
    admin = FakeAdminClient({"p1": "blended"})
    store = FakeStateStore()

    with pytest.raises(ValueError):
        with reporting_identity(admin, store, "p1", "observed"):
            raise ValueError("query blew up mid-switch")

    assert admin.get_reporting_identity("p1") == "blended"  # still restored
    assert store.open_switches == {}


def test_already_at_target_identity_is_a_no_op():
    admin = FakeAdminClient({"p1": "observed"})
    store = FakeStateStore()

    with reporting_identity(admin, store, "p1", "observed") as outcome:
        pass

    assert outcome.switch_succeeded
    assert outcome.restore_ok
    assert admin.set_calls == []  # never touched the API


def test_switch_failure_yields_outcome_with_switch_not_succeeded():
    admin = FakeAdminClient({"p1": "blended"}, fail_on_set_to={"observed"})
    store = FakeStateStore()

    with pytest.raises(RuntimeError):
        with reporting_identity(admin, store, "p1", "observed") as outcome:
            assert not outcome.switch_succeeded

    # Property never actually left 'blended'.
    assert admin.state["p1"] == "blended"


def test_verify_and_recover_stale_switches_restores_leftover_state():
    # Simulates a previous run that crashed after switching but before the
    # finally-block restore ran: the property is stuck on 'observed' and the
    # state store still has an open switch recorded.
    admin = FakeAdminClient({"p1": "observed"})
    store = FakeStateStore()
    store.open_switches["p1"] = "blended"  # what it should be restored to

    recovered = verify_and_recover_stale_switches(admin, store)

    assert len(recovered) == 1
    assert recovered[0].restore_ok
    assert admin.get_reporting_identity("p1") == "blended"
    assert store.open_switches == {}


def test_verify_and_recover_reports_failure_if_restore_fails():
    admin = FakeAdminClient({"p1": "observed"}, fail_on_set_to={"blended"})
    store = FakeStateStore()
    store.open_switches["p1"] = "blended"

    recovered = verify_and_recover_stale_switches(admin, store)

    assert recovered[0].restore_ok is False
    assert admin.get_reporting_identity("p1") == "observed"  # stuck, but reported
