from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import AudioMetadata, TranscriptSegment, TranscriptionResult
from .timecode import seconds_to_timestamp
from .aihub_runtime import find_whisper_app_dir, find_whisper_model_paths, find_whisper_python


class WhisperRunnerError(RuntimeError):
    """Raised when a transcription runner cannot produce a result."""


@dataclass(slots=True)
class WhisperRuntimeConfig:
    app_dir: Path | None = None
    python_path: Path | None = None
    model_build_dir: Path | None = None
    encoder_path: Path | None = None
    decoder_path: Path | None = None
    audio_device_id: str | None = None
    backend_label: str = "qualcomm_whisper_windows"
    timeout_seconds: int = 600


class WhisperRunner:
    backend_name = "unknown"

    def transcribe(self, audio: AudioMetadata) -> TranscriptionResult:
        raise NotImplementedError


class FallbackWhisperRunner(WhisperRunner):
    backend_name = "sample_transcript"

    def transcribe(self, audio: AudioMetadata) -> TranscriptionResult:
        started = time.perf_counter()
        transcript_text = self._sidecar_text(audio.path)
        if not transcript_text:
            raise WhisperRunnerError(
                "Real Whisper transcription is not configured. Set OFFLINE_NOTES_WHISPER_COMMAND "
                "to the command that runs your working Whisper/ExecuTorch pipeline. The command may "
                "use {audio} as the audio-file placeholder."
            )
        duration = max(audio.duration_seconds, 1.0)
        segment = TranscriptSegment(
            start=seconds_to_timestamp(0),
            end=seconds_to_timestamp(duration),
            text=transcript_text,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return TranscriptionResult(
            segments=[segment],
            full_transcript=transcript_text,
            backend=self.backend_name,
            latency_ms=latency_ms,
            real_time_factor=round((latency_ms / 1000) / duration, 4),
            warnings=["Using bundled sample transcript."],
        )

    def _sidecar_text(self, path: Path) -> str:
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip()
        return ""


class TransformersWhisperRunner(WhisperRunner):
    backend_name = "local_whisper_transformers"
    _model = None
    _processor = None
    _model_name: str | None = None

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.environ.get("OFFLINE_NOTES_WHISPER_MODEL", "openai/whisper-tiny.en")

    def transcribe(self, audio: AudioMetadata) -> TranscriptionResult:
        started = time.perf_counter()
        samples = self._load_wav(audio.path)
        if samples.size == 0:
            raise WhisperRunnerError("Audio file is empty.")
        if not np.any(np.abs(samples) > 1e-4):
            duration = max(audio.duration_seconds, samples.size / 16000, 1.0)
            return TranscriptionResult(
                segments=[
                    TranscriptSegment(
                        start=seconds_to_timestamp(0),
                        end=seconds_to_timestamp(duration),
                        text="No speech detected.",
                    )
                ],
                full_transcript="No speech detected.",
                backend=self.backend_name,
                latency_ms=int((time.perf_counter() - started) * 1000),
                real_time_factor=0.0,
                warnings=[],
            )

        processor, model = self._load_model()
        segments = []
        chunk_seconds = 30
        sample_rate = 16000
        chunk_size = chunk_seconds * sample_rate

        for index, start_sample in enumerate(range(0, samples.size, chunk_size), start=1):
            chunk = samples[start_sample : start_sample + chunk_size]
            if not np.any(np.abs(chunk) > 1e-4):
                continue
            inputs = processor(chunk, sampling_rate=sample_rate, return_tensors="pt")
            generated_ids = model.generate(inputs.input_features)
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            if not text:
                continue
            start_seconds = start_sample / sample_rate
            end_seconds = min(samples.size, start_sample + chunk.size) / sample_rate
            segments.append(
                TranscriptSegment(
                    start=seconds_to_timestamp(start_seconds),
                    end=seconds_to_timestamp(end_seconds),
                    text=text,
                )
            )

        if not segments:
            duration = max(audio.duration_seconds, samples.size / sample_rate, 1.0)
            segments = [
                TranscriptSegment(
                    start=seconds_to_timestamp(0),
                    end=seconds_to_timestamp(duration),
                    text="No speech detected.",
                )
            ]

        latency_ms = int((time.perf_counter() - started) * 1000)
        duration = max(audio.duration_seconds, samples.size / sample_rate, 1.0)
        return TranscriptionResult(
            segments=segments,
            full_transcript=" ".join(segment.text for segment in segments).strip(),
            backend=self.backend_name,
            latency_ms=latency_ms,
            real_time_factor=round((latency_ms / 1000) / duration, 4),
            warnings=[],
        )

    def _load_model(self):  # type: ignore[no-untyped-def]
        if self.__class__._model is not None and self.__class__._model_name == self.model_name:
            return self.__class__._processor, self.__class__._model
        try:
            from transformers import AutoProcessor, WhisperForConditionalGeneration
        except ImportError as exc:
            raise WhisperRunnerError(
                "Local Whisper dependencies are missing. Run: python -m pip install -e \".[gui,dev]\""
            ) from exc

        processor = AutoProcessor.from_pretrained(self.model_name)
        model = WhisperForConditionalGeneration.from_pretrained(self.model_name)
        model.eval()
        self.__class__._processor = processor
        self.__class__._model = model
        self.__class__._model_name = self.model_name
        return processor, model

    def _load_wav(self, path: Path) -> np.ndarray:
        if path.suffix.lower() != ".wav":
            raise WhisperRunnerError(
                "The built-in local Whisper backend currently supports WAV files. "
                "Record in the app or convert uploaded audio to WAV. For MP3/M4A/FLAC, wire your "
                "Whisper runner with OFFLINE_NOTES_WHISPER_COMMAND."
            )
        try:
            with wave.open(str(path), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as exc:
            raise WhisperRunnerError(f"Cannot read WAV audio: {path}") from exc

        dtype_by_width = {1: np.uint8, 2: np.int16, 4: np.int32}
        dtype = dtype_by_width.get(sample_width)
        if dtype is None:
            raise WhisperRunnerError(f"Unsupported WAV sample width: {sample_width}")
        samples = np.frombuffer(frames, dtype=dtype)
        if sample_width == 1:
            samples = (samples.astype(np.float32) - 128.0) / 128.0
        else:
            max_value = float(2 ** (8 * sample_width - 1))
            samples = samples.astype(np.float32) / max_value
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        if sample_rate != 16000:
            samples = self._resample(samples, sample_rate, 16000)
        return samples.astype(np.float32)

    def _resample(self, samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate <= 0:
            raise WhisperRunnerError("Invalid WAV sample rate.")
        if samples.size == 0 or source_rate == target_rate:
            return samples
        duration = samples.size / source_rate
        target_count = max(1, int(round(duration * target_rate)))
        source_x = np.linspace(0, duration, num=samples.size, endpoint=False)
        target_x = np.linspace(0, duration, num=target_count, endpoint=False)
        return np.interp(target_x, source_x, samples).astype(np.float32)


class CommandWhisperRunner(WhisperRunner):
    backend_name = "external_whisper_command"

    def __init__(self, command_template: str, timeout_seconds: int = 900) -> None:
        self.command_template = command_template
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "CommandWhisperRunner | None":
        command = os.environ.get("OFFLINE_NOTES_WHISPER_COMMAND", "").strip()
        if not command:
            return None
        return cls(command)

    def transcribe(self, audio: AudioMetadata) -> TranscriptionResult:
        command = self.command_template.format(audio=str(audio.path))
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout).strip()
            raise WhisperRunnerError(error or f"Whisper command failed: {command}")

        segments = self._parse_segments(completed.stdout)
        if not segments:
            text = self._extract_text(completed.stdout)
            if not text:
                raise WhisperRunnerError("Whisper command completed but did not return transcript text.")
            duration = max(audio.duration_seconds, 1.0)
            segments = [TranscriptSegment(seconds_to_timestamp(0), seconds_to_timestamp(duration), text)]

        full_transcript = " ".join(segment.text for segment in segments).strip()
        duration = max(audio.duration_seconds, 1.0)
        return TranscriptionResult(
            segments=segments,
            full_transcript=full_transcript,
            backend=self.backend_name,
            latency_ms=latency_ms,
            real_time_factor=round((latency_ms / 1000) / duration, 4),
            warnings=[],
        )

    def _parse_segments(self, stdout: str) -> list[TranscriptSegment]:
        stripped = stdout.strip()
        if not stripped:
            return []
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        raw_segments = payload.get("segments", []) if isinstance(payload, dict) else []
        segments = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            start = str(raw.get("start", "00:00:00.000"))
            end = str(raw.get("end", start))
            segments.append(TranscriptSegment(start=start, end=end, text=text))
        return segments

    def _extract_text(self, stdout: str) -> str:
        stripped = stdout.strip()
        if not stripped:
            return ""
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(payload, dict):
            return str(payload.get("full_transcript") or payload.get("text") or "").strip()
        return stripped


class QualcommWhisperWindowsRunner(WhisperRunner):
    backend_name = "qualcomm_whisper_windows"

    def __init__(self, config: WhisperRuntimeConfig) -> None:
        self.config = config

    @classmethod
    def autodetect(cls) -> "QualcommWhisperWindowsRunner":
        app_dir = find_whisper_app_dir()
        if not app_dir:
            raise WhisperRunnerError(
                "Qualcomm Whisper Windows is not installed. Clone Qualcomm ai-hub-apps, run the "
                "whisper_windows_py setup/export steps, and set OFFLINE_NOTES_WHISPER_APP_DIR."
            )
        encoder_path, decoder_path = find_whisper_model_paths(app_dir)
        if not encoder_path or not decoder_path:
            raise WhisperRunnerError(
                "Qualcomm Whisper Windows models are missing. Export Whisper-Base from AI Hub and set "
                "OFFLINE_NOTES_WHISPER_ENCODER_PATH and OFFLINE_NOTES_WHISPER_DECODER_PATH."
            )
        return cls(
            WhisperRuntimeConfig(
                app_dir=app_dir,
                python_path=find_whisper_python(app_dir),
                encoder_path=encoder_path,
                decoder_path=decoder_path,
                backend_label=cls.backend_name,
            )
        )

    def transcribe(self, audio: AudioMetadata) -> TranscriptionResult:
        if not self.config.app_dir:
            raise WhisperRunnerError("Whisper Windows app directory is not configured.")
        app_dir = self.config.app_dir.expanduser().resolve()
        demo_py = app_dir / "demo.py"
        if not demo_py.exists():
            raise WhisperRunnerError(f"Cannot find Whisper Windows demo.py at {demo_py}")

        python_path = self.config.python_path or find_whisper_python(app_dir) or Path(sys.executable)
        command = [str(python_path), str(demo_py), "--audio-file", str(audio.path), "--model-size", "base"]
        if self.config.encoder_path and self.config.decoder_path:
            command.extend(["--encoder-path", str(self.config.encoder_path)])
            command.extend(["--decoder-path", str(self.config.decoder_path)])
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=str(app_dir),
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
            check=False,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout).strip()
            raise WhisperRunnerError(error or "Whisper Windows runner failed.")

        text = self._extract_transcript(completed.stdout)
        if not text:
            raise WhisperRunnerError("Whisper Windows runner completed but no transcript text was found.")

        duration = max(audio.duration_seconds, 1.0)
        segment = TranscriptSegment(
            start=seconds_to_timestamp(0),
            end=seconds_to_timestamp(duration),
            text=text,
        )
        return TranscriptionResult(
            segments=[segment],
            full_transcript=text,
            backend=self.config.backend_label,
            latency_ms=latency_ms,
            real_time_factor=round((latency_ms / 1000) / duration, 4),
            warnings=[],
        )

    def _extract_transcript(self, stdout: str) -> str:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return ""
        for line in reversed(lines):
            lowered = line.lower()
            if lowered.startswith(("transcript:", "transcription:")):
                return line.split(":", 1)[1].strip()
        return lines[-1]
