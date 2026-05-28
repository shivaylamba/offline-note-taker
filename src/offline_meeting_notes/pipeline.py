from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .audio import AudioManager
from .chunking import ChunkingAgent
from .cleanup import TranscriptCleanupAgent
from .models import AudioMetadata, MeetingNotes, MeetingSession, TranscriptChunk, TranscriptSegment, TranscriptionResult
from .summarization import (
    FallbackMeetingNotesRunner,
    MeetingNotesInput,
    MeetingNotesRunner,
    Qwen3GenieMeetingNotesRunner,
)
from .transcription import (
    CommandWhisperRunner,
    FallbackWhisperRunner,
    QualcommWhisperWindowsRunner,
    TransformersWhisperRunner,
    WhisperRunner,
    WhisperRunnerError,
    WhisperRuntimeConfig,
)


@dataclass(slots=True)
class PipelineSettings:
    whisper_backend: str = "qualcomm_aihub"
    whisper_app_dir: str = ""
    whisper_model_build_dir: str = ""
    audio_device_id: str = ""
    backend_label: str = "qualcomm_whisper_windows"


@dataclass(slots=True)
class PreparedTranscript:
    transcription: TranscriptionResult
    chunks: list[TranscriptChunk]


class MeetingPipeline:
    def __init__(
        self,
        audio_manager: AudioManager | None = None,
        chunker: ChunkingAgent | None = None,
        notes_runner: MeetingNotesRunner | None = None,
    ) -> None:
        self.audio_manager = audio_manager or AudioManager()
        self.cleanup_agent = TranscriptCleanupAgent()
        self.chunker = chunker or ChunkingAgent()
        self.notes_runner = notes_runner

    def process_file(self, path: str | Path, settings: PipelineSettings | None = None) -> MeetingSession:
        return self.process_audio(self.audio_manager.import_audio(path), settings)

    def process_audio(self, audio: AudioMetadata, settings: PipelineSettings | None = None) -> MeetingSession:
        prepared = self.prepare_transcript(audio, settings)
        notes = self.generate_notes(prepared)
        return MeetingSession(audio=audio, transcription=prepared.transcription, chunks=prepared.chunks, notes=notes)

    def prepare_transcript(self, audio: AudioMetadata, settings: PipelineSettings | None = None) -> PreparedTranscript:
        settings = settings or PipelineSettings()
        runner = self._runner_for(settings, audio)
        transcription = runner.transcribe(audio)
        cleaned = self.cleanup_agent.clean(transcription)
        cleaned_segments = self._cleaned_segments(transcription.segments, cleaned.clean_transcript)
        chunks = self.chunker.chunk_segments(cleaned_segments)
        cleaned_transcription = TranscriptionResult(
            segments=cleaned_segments,
            full_transcript=cleaned.clean_transcript,
            backend=transcription.backend,
            latency_ms=transcription.latency_ms,
            real_time_factor=transcription.real_time_factor,
            warnings=transcription.warnings,
        )
        return PreparedTranscript(transcription=cleaned_transcription, chunks=chunks)

    def generate_notes(
        self,
        prepared: PreparedTranscript,
        on_text: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> MeetingNotes:
        notes_runner = self.notes_runner or self._default_notes_runner()
        payload = MeetingNotesInput(chunks=prepared.chunks, segments=prepared.transcription.segments)
        return notes_runner.generate_stream(payload, on_text, cancel_event)

    def _runner_for(self, settings: PipelineSettings, audio: AudioMetadata) -> WhisperRunner:
        if settings.whisper_backend == "auto":
            if audio.path.with_suffix(".txt").exists():
                return FallbackWhisperRunner()
            command_runner = CommandWhisperRunner.from_environment()
            if command_runner:
                return command_runner
            return TransformersWhisperRunner()
        if settings.whisper_backend == "qualcomm_aihub":
            if audio.path.with_suffix(".txt").exists():
                return FallbackWhisperRunner()
            command_runner = CommandWhisperRunner.from_environment()
            if command_runner:
                return command_runner
            return QualcommWhisperWindowsRunner.autodetect()
        if settings.whisper_backend == "qualcomm":
            return QualcommWhisperWindowsRunner(
                WhisperRuntimeConfig(
                    app_dir=Path(settings.whisper_app_dir) if settings.whisper_app_dir else None,
                    model_build_dir=Path(settings.whisper_model_build_dir) if settings.whisper_model_build_dir else None,
                    audio_device_id=settings.audio_device_id or None,
                    backend_label=settings.backend_label or "qualcomm_whisper_windows",
                )
            )
        return FallbackWhisperRunner()

    def _default_notes_runner(self) -> MeetingNotesRunner:
        return Qwen3GenieMeetingNotesRunner.autodetect()

    def _cleaned_segments(self, segments: list[TranscriptSegment], clean_text: str) -> list[TranscriptSegment]:
        if len(segments) == 1:
            segment = segments[0]
            return [TranscriptSegment(start=segment.start, end=segment.end, text=clean_text)]
        return [
            TranscriptSegment(start=segment.start, end=segment.end, text=self.cleanup_agent._clean_text(segment.text))
            for segment in segments
        ]
