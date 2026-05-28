from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.models import TranscriptSegment, TranscriptionResult
from offline_meeting_notes.pipeline import MeetingPipeline, PipelineSettings
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner
from offline_meeting_notes.transcription import TransformersWhisperRunner


def test_real_audio_uses_builtin_whisper_runner_when_no_sidecar(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OFFLINE_NOTES_WHISPER_COMMAND", raising=False)

    def fake_transcribe(self, audio):  # type: ignore[no-untyped-def]
        return TranscriptionResult(
            segments=[TranscriptSegment("00:00:00.000", "00:00:01.000", "hello from whisper")],
            full_transcript="hello from whisper",
            backend=self.backend_name,
            latency_ms=1,
            real_time_factor=0.0,
        )

    monkeypatch.setattr(TransformersWhisperRunner, "transcribe", fake_transcribe)
    audio = AudioManager().create_placeholder_wav()

    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(
        audio,
        PipelineSettings(whisper_backend="auto"),
    )

    assert session.transcription.backend == "local_whisper_transformers"
    assert session.transcription.full_transcript == "hello from whisper."
