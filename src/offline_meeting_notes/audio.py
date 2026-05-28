from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

from .models import AudioMetadata

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}
DEFAULT_SAMPLE_RATE = 16000


class AudioError(RuntimeError):
    """Raised when local audio capture or import fails."""


class AudioManager:
    def import_audio(self, path: str | os.PathLike[str]) -> AudioMetadata:
        audio_path = Path(path).expanduser().resolve()
        if not audio_path.exists():
            raise AudioError(f"Audio file does not exist: {audio_path}")
        if audio_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
            raise AudioError(f"Unsupported audio format. Supported: {supported}")

        duration, sample_rate = self._read_basic_metadata(audio_path)
        return AudioMetadata(
            source="file",
            path=audio_path,
            duration_seconds=duration,
            format=audio_path.suffix.lower().lstrip("."),
            sample_rate=sample_rate,
        )

    def create_placeholder_wav(self, duration_seconds: float = 1.0) -> AudioMetadata:
        target = Path(tempfile.gettempdir()) / "offline_meeting_notes_placeholder.wav"
        self._write_silence(target, duration_seconds)
        return self.import_audio(target)

    def create_sample_meeting_wav(self) -> AudioMetadata:
        target = Path(tempfile.gettempdir()) / "offline_meeting_notes_sample.wav"
        self._write_silence(target, duration_seconds=3.0)
        target.with_suffix(".txt").write_text(
            "Alice will send the launch notes by Friday. "
            "The team agreed to use the Snapdragon NPU demo path for Whisper. "
            "The Qwen production path needs target-device verification. "
            "A blocker is missing Qualcomm model artifacts for the local LLM.",
            encoding="utf-8",
        )
        return self.import_audio(target)

    def _write_silence(self, target: Path, duration_seconds: float) -> None:
        frame_count = int(DEFAULT_SAMPLE_RATE * duration_seconds)
        silence = b"\x00\x00" * frame_count
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(DEFAULT_SAMPLE_RATE)
            wav.writeframes(silence)

    def _read_basic_metadata(self, path: Path) -> tuple[float, int]:
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wav:
                    frames = wav.getnframes()
                    sample_rate = wav.getframerate()
                    duration = frames / float(sample_rate) if sample_rate else 0.0
                    return duration, sample_rate
            except wave.Error as exc:
                raise AudioError(f"Invalid WAV file: {path}") from exc
        return 0.0, DEFAULT_SAMPLE_RATE


class WavRecorder:
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._stream = None
        self._frames: list[bytes] = []
        self._target_path: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self, target_path: str | os.PathLike[str] | None = None) -> Path:
        if self.is_recording:
            raise AudioError("Recording is already active.")

        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise AudioError(
                "Microphone recording needs the local audio package. Run: "
                'python -m pip install -e ".[gui]"'
            ) from exc

        try:
            sd.query_devices(kind="input")
        except Exception as exc:  # noqa: BLE001 - normalize PortAudio/device errors for the GUI.
            raise AudioError(
                "No working microphone input was found. Check Windows microphone privacy permission, "
                "confirm an input device is enabled, or use Upload Audio."
            ) from exc

        self._target_path = Path(target_path or self._default_recording_path()).resolve()
        self._frames = []

        def callback(indata, _frames, _time, status):  # type: ignore[no-untyped-def]
            if status:
                return
            pcm = np.clip(indata[:, 0], -1.0, 1.0)
            self._frames.append((pcm * 32767).astype(np.int16).tobytes())

        try:
            self._stream = sd.InputStream(
                channels=1,
                samplerate=self.sample_rate,
                dtype="float32",
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - normalize PortAudio/device errors for the GUI.
            self._stream = None
            raise AudioError(
                "Could not start microphone recording. Check Windows microphone permission, "
                "close other apps using the microphone, or use Upload Audio."
            ) from exc
        return self._target_path

    def stop(self) -> AudioMetadata:
        if not self.is_recording or self._target_path is None:
            raise AudioError("No active recording to stop.")

        stream = self._stream
        self._stream = None
        stream.stop()
        stream.close()

        self._target_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self._target_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(b"".join(self._frames))

        metadata = AudioManager().import_audio(self._target_path)
        self._target_path = None
        self._frames = []
        return metadata

    def _default_recording_path(self) -> Path:
        root = Path.cwd() / "recordings"
        root.mkdir(parents=True, exist_ok=True)
        index = 1
        while True:
            candidate = root / f"meeting_recording_{index:03d}.wav"
            if not candidate.exists():
                return candidate
            index += 1
