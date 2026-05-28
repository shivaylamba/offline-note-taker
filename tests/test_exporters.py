import json

from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.exporters import ExportAgent
from offline_meeting_notes.pipeline import MeetingPipeline
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner


def test_export_files_have_expected_structure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio)

    exported = ExportAgent(tmp_path).export_all(session)

    assert exported["markdown"].read_text(encoding="utf-8").startswith("# Meeting Notes")
    assert "WEBVTT" in exported["vtt"].read_text(encoding="utf-8")
    assert "-->" in exported["srt"].read_text(encoding="utf-8")

    payload = json.loads(exported["json"].read_text(encoding="utf-8"))
    assert payload["transcription"]["backend"] == "sample_transcript"
    assert payload["notes"]["backend"] == "deterministic_fallback"
