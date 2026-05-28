from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MeetingSession
from .quality import evaluate_notes


@dataclass(slots=True)
class RunDiagnostics:
    run_id: str
    created_at: str
    audio_name: str
    audio_path: str
    duration_seconds: float
    whisper_backend: str
    whisper_latency_ms: int
    whisper_real_time_factor: float
    qwen_backend: str
    qwen_elapsed_ms: int
    fallback_reason: str
    quality: dict[str, Any] = field(default_factory=dict)
    export_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DiagnosticsLogger:
    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)

    def write(self, session: MeetingSession, export_paths: dict[str, Path] | None = None) -> Path:
        diagnostics = self.from_session(session, export_paths)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{diagnostics.run_id}.json"
        path.write_text(json.dumps(diagnostics.to_dict(), indent=2), encoding="utf-8")
        return path

    def from_session(
        self,
        session: MeetingSession,
        export_paths: dict[str, Path] | None = None,
    ) -> RunDiagnostics:
        created = datetime.now(timezone.utc)
        run_id = created.strftime("%Y%m%dT%H%M%S%fZ")
        exports = {kind: str(path) for kind, path in (export_paths or {}).items()}
        quality = evaluate_notes(session).to_dict()
        return RunDiagnostics(
            run_id=run_id,
            created_at=created.isoformat(),
            audio_name=session.audio.path.name,
            audio_path=str(session.audio.path),
            duration_seconds=session.audio.duration_seconds,
            whisper_backend=session.transcription.backend,
            whisper_latency_ms=session.transcription.latency_ms,
            whisper_real_time_factor=session.transcription.real_time_factor,
            qwen_backend=session.notes.backend,
            qwen_elapsed_ms=session.notes.elapsed_ms,
            fallback_reason=session.notes.fallback_reason,
            quality=quality,
            export_paths=exports,
        )
