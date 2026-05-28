import json

from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.diagnostics import DiagnosticsLogger
from offline_meeting_notes.pipeline import MeetingPipeline
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner


def test_diagnostics_log_contains_runtime_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio)

    path = DiagnosticsLogger(tmp_path).write(session)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["audio_name"] == audio.path.name
    assert payload["whisper_backend"] == "sample_transcript"
    assert payload["qwen_backend"] == "deterministic_fallback"
    assert "whisper_latency_ms" in payload
    assert "qwen_elapsed_ms" in payload
