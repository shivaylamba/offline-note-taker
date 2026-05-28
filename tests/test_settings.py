import os

from offline_meeting_notes.settings import AppSettings


def test_settings_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "settings.json"
    settings = AppSettings(
        whisper_app_dir=str(tmp_path / "whisper"),
        qairt_home=str(tmp_path / "qairt"),
        audio_input_device_id="3",
    )

    saved = settings.save(path)
    loaded = AppSettings.load(saved)

    assert loaded.whisper_app_dir == str(tmp_path / "whisper")
    assert loaded.qairt_home == str(tmp_path / "qairt")
    assert loaded.audio_input_device_id == "3"


def test_settings_apply_to_environment(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QAIRT_HOME", "")
    monkeypatch.setenv("OFFLINE_NOTES_QWEN3_GENIE_CONFIG", "")
    settings = AppSettings(qairt_home=str(tmp_path), qwen3_genie_config=str(tmp_path / "genie_config.json"))

    settings.apply_to_environment()

    assert os.environ["QAIRT_HOME"] == str(tmp_path)
    assert os.environ["OFFLINE_NOTES_QWEN3_GENIE_CONFIG"] == str(tmp_path / "genie_config.json")
