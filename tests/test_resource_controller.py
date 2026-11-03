from datetime import datetime, timezone
from panther.domain.models import ProcessIdentity
from panther.services.resource_controller import ResourceController, ALLOWED_PRIORITIES


class FakePriorityAdapter:
    def __init__(self, initial=None):
        self.priorities = {}
        self.calls = []
        self.initial = 0x20 if initial is None else initial

    def change_priority(self, identity, priority, prevent_foreground=False):
        self.calls.append((identity, priority))
        previous = self.priorities.get(identity.key, self.initial)
        self.priorities[identity.key] = priority
        return True, "verified", previous, priority


def identity():
    return ProcessIdentity(987654, 123456.0, "example.exe", r"C:\\Program Files\\Example\\example.exe")


def eligible():
    return {"category": "User application", "can_terminate": False}


def test_automatic_control_is_disabled_by_default(tmp_path):
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=FakePriorityAdapter())
    assert controller._automatic_enabled is False


def test_rejects_priority_outside_conservative_allowlist(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x80,
                                      "test", user_confirmed=True, classification=eligible())
    assert result.result == "failed"
    assert "allowlist" in result.error
    assert adapter.calls == []


def test_requires_explicit_confirmation(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000,
                                      "test", classification=eligible())
    assert result.result == "rejected"
    assert adapter.calls == []


def test_recommendation_mode_never_executes(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000,
                                      "test", mode="recommendation", user_confirmed=True,
                                      classification=eligible())
    assert result.result == "rejected"
    assert adapter.calls == []


def test_success_is_verified_and_persisted(tmp_path):
    db = tmp_path / "history.db"
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=db, process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000,
                                      "user confirmed", user_confirmed=True, classification=eligible())
    assert result.result == "success"
    assert result.verified is True
    assert result.identity_key == identity().key
    reloaded = ResourceController(db_path=db, process_adapter=adapter).get_history()
    assert len(reloaded) == 1
    assert reloaded[0].rollback_data["identity"] == identity()


def test_rollback_requires_confirmation_and_restores_original(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000,
                                      "confirmed", user_confirmed=True, classification=eligible())
    assert controller.rollback(result.id)[0] is False
    ok, message = controller.rollback(result.id, user_confirmed=True)
    assert ok is True
    assert message == "Rolled back successfully"
    assert adapter.priorities[identity().key] == 0x20
    assert controller.get_history()[-1].action_type == "rollback"


def test_rejects_foreground_automatic_target_even_when_enabled(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    controller.enable_automatic(True)
    result = controller.set_priority(identity(), 0x4000,
        "automatic", mode="automatic", user_confirmed=True, classification=eligible(), is_foreground=True)
    assert result.result == "rejected"
    assert adapter.calls == []


def test_automatic_mode_requires_explicit_enablement(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000,
        "automatic", mode="automatic", user_confirmed=True, classification=eligible())
    assert result.result == "rejected"
    assert adapter.calls == []



def test_native_adapter_fails_closed_off_windows():
    import os
    from panther.services.resource_controller import WindowsPriorityAdapter
    if os.name != "nt":
        ok, message, previous, actual = WindowsPriorityAdapter().change_priority(
            identity(), 0x4000
        )
        assert ok is False
        assert "only on Windows" in message
        assert previous is None and actual is None


def test_rollback_cannot_be_replayed(tmp_path):
    adapter = FakePriorityAdapter()
    controller = ResourceController(db_path=tmp_path / "history.db", process_adapter=adapter)
    result = controller.set_priority(identity(), 0x4000, "confirmed",
                                     user_confirmed=True, classification=eligible())
    assert controller.rollback(result.id, user_confirmed=True)[0] is True
    original = next(action for action in controller.get_history() if action.id == result.id)
    assert original.result == "rolled_back"
    assert original.reversible is False
    assert controller.rollback(result.id, user_confirmed=True)[0] is False
