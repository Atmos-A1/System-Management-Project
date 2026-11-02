"""Tests for resource controller (Phase 9)."""

from panther.services.resource_controller import ResourceController


def test_resource_controller_init():
    controller = ResourceController()
    assert controller is not None
    assert controller._automatic_enabled is False  # Disabled by default


def test_automatic_disabled_by_default():
    controller = ResourceController()
    assert controller.history.automatic_enabled is False
    assert controller.history.mode in ("recommendation", "simulation")


def test_enable_automatic_only_if_explicit():
    controller = ResourceController()
    controller.enable_automatic(False)
    assert controller._automatic_enabled is False


def test_get_history():
    controller = ResourceController()
    history = controller.get_history()
    assert isinstance(history, list)
