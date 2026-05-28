import json

from offline_meeting_notes.__main__ import main
from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner


def test_smoke_subcommand_exports_files(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    export_dir = tmp_path / "exports"

    result = main(["smoke", "--export-dir", str(export_dir)])

    assert result == 0
    assert (export_dir / "meeting_notes.md").exists()
    assert (export_dir / "meeting_summary.json").exists()
    assert (tmp_path / "logs").exists()


def test_doctor_json_subcommand_outputs_machine_readable_status(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["doctor", "--json", "--no-npu-detect"])

    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert result in {0, 1}
    assert "checks" in payload
    assert "ok" in payload


def test_process_subcommand_can_create_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "offline_meeting_notes.pipeline.MeetingPipeline._default_notes_runner",
        lambda self: FallbackMeetingNotesRunner(),
    )
    monkeypatch.chdir(tmp_path)
    audio = AudioManager().create_sample_meeting_wav()
    session_dir = tmp_path / "sessions" / "demo"

    result = main(["process", "--audio", str(audio.path), "--export-dir", str(tmp_path / "exports"), "--session", str(session_dir)])

    assert result == 0
    assert (session_dir / "session.json").exists()
    assert (session_dir / "diagnostics.json").exists()
