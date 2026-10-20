"""Project-scoped credential selection: no API calls or real secrets."""

import pytest

from mp3_to_videoclip import transcription
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.providers import RUNWARE_KEY_ENV, runware_api_key


@pytest.mark.parametrize("project_key", [None, "", "  "])
def test_missing_selected_key_never_falls_back_to_other_variables(monkeypatch, project_key):
    monkeypatch.setenv("RUNWARE_API_KEY", "mock-shared-key")
    monkeypatch.setenv("MP3_TO_VIDEOCLIP_RUNWARE_API_KEY", "mock-old-project-key")
    if project_key is None:
        monkeypatch.delenv(RUNWARE_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(RUNWARE_KEY_ENV, project_key)
    with pytest.raises(ValueError, match=RUNWARE_KEY_ENV) as failure:
        runware_api_key()
    assert "mock-shared-key" not in str(failure.value)
    assert "mock-old-project-key" not in str(failure.value)


def test_selected_veil_key_is_used_and_doctor_never_displays_values(monkeypatch):
    monkeypatch.setenv("PROJECT_VEIL_RUNWARE_API", "mock-selected-secret")
    monkeypatch.setenv("RUNWARE_API_KEY", "mock-unrelated-secret")
    monkeypatch.setenv("MP3_TO_VIDEOCLIP_RUNWARE_API_KEY", "mock-old-project-key")
    assert RUNWARE_KEY_ENV == "PROJECT_VEIL_RUNWARE_API"
    assert runware_api_key() == "mock-selected-secret"
    report = execute(parser().parse_args(["doctor"]))
    assert report["runware_key_environment_variable"] == RUNWARE_KEY_ENV
    assert report["project_RUNWARE_API_KEY_present"] is True
    assert report["shared_RUNWARE_API_KEY_ignored"] is True
    assert "mock-selected-secret" not in str(report)
    assert "mock-unrelated-secret" not in str(report)


def test_audio_factory_uses_selected_key_without_network(monkeypatch):
    monkeypatch.setenv(RUNWARE_KEY_ENV, "mock-selected-key")
    monkeypatch.setenv("RUNWARE_API_KEY", "mock-wrong-key")
    seen = []
    sentinel = object()

    def constructor(key):
        seen.append(key)
        return sentinel

    monkeypatch.setattr(transcription, "RunwareClient", constructor)
    assert transcription._client(None) == (sentinel, True)
    assert seen == ["mock-selected-key"]
