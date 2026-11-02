import pytest

from panther.services.process_classifier import ProcessClassifier


@pytest.fixture
def classifier(monkeypatch):
    monkeypatch.setattr(
        "panther.services.process_classifier.getpass.getuser",
        lambda: "tester",
    )
    return ProcessClassifier()


def make_process(**overrides):
    process = {
        "pid": 1234,
        "name": "editor.exe",
        "exe": r"C:\Program Files\Example\editor.exe".lower(),
        "username": r"DESKTOP\tester",
        "ppid": 100,
    }
    process.update(overrides)
    return process


def test_current_user_application_is_display_candidate_not_termination_authorized(classifier):
    result = classifier.classify(make_process())

    assert result["category"] == "User application"
    assert result["risk_level"] == "Review required"
    assert result["can_terminate"] is False
    assert "not prove it is safe to close" in result["explanation"]


def test_application_running_as_another_user_is_not_user_application(classifier):
    result = classifier.classify(make_process(username=r"NT AUTHORITY\SYSTEM"))

    assert result["category"] == "Unknown / unverified"
    assert result["can_terminate"] is False


def test_missing_user_identity_is_not_user_application(classifier):
    result = classifier.classify(make_process(username=None))

    assert result["category"] == "Unknown / unverified"
    assert result["can_terminate"] is False


def test_windowsapps_process_is_not_user_application(classifier):
    result = classifier.classify(
        make_process(exe=r"C:\Program Files\WindowsApps\Example\editor.exe".lower())
    )

    assert result["category"] == "Unknown / unverified"
    assert result["can_terminate"] is False


def test_temporary_appdata_executable_is_not_user_application(classifier):
    result = classifier.classify(
        make_process(exe=r"C:\Users\tester\AppData\Local\Temp\editor.exe".lower())
    )

    assert result["category"] == "Unknown / unverified"
    assert result["can_terminate"] is False
