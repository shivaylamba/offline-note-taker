from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_paths import sessions_dir
from .diagnostics import DiagnosticsLogger
from .exporters import ExportAgent
from .models import ActionItem, AudioMetadata, MeetingNotes, MeetingSession, TranscriptChunk, TranscriptSegment, TranscriptionResult


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    title: str
    created_at: str
    audio_name: str
    transcript_preview: str
    notes_preview: str
    notes_backend: str
    path: Path


class SessionStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else sessions_dir()

    def create_session_dir(self, session_id: str | None = None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        base = session_id or datetime.now().strftime("%Y%m%dT%H%M%S%f")
        path = self.root / self._safe_session_id(base)
        suffix = 1
        while path.exists():
            path = self.root / f"{self._safe_session_id(base)}-{suffix}"
            suffix += 1
        path.mkdir(parents=True, exist_ok=False)
        return path

    def resolve_session_dir(self, session: str | Path | None) -> Path:
        if not session:
            return self.create_session_dir()
        candidate = Path(session)
        if candidate.is_absolute() or candidate.parent != Path("."):
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        path = self.root / self._safe_session_id(str(session))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, session: MeetingSession, session_dir: Path | None = None, export: bool = False) -> Path:
        target = session_dir or self.create_session_dir()
        target.mkdir(parents=True, exist_ok=True)
        copied_audio = self._copy_audio(session.audio, target)
        payload = session.to_dict()
        payload["session_id"] = target.name
        payload["created_at"] = datetime.now().isoformat(timespec="seconds")
        payload["audio"]["session_audio_path"] = str(copied_audio)
        (target / "session.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (target / "transcript.json").write_text(
            json.dumps(session.transcription.to_dict(), indent=2),
            encoding="utf-8",
        )
        (target / "notes.json").write_text(json.dumps(session.notes.to_dict(), indent=2), encoding="utf-8")
        diagnostics_logger = DiagnosticsLogger(target)
        diagnostics_logger.write(session)
        (target / "diagnostics.json").write_text(
            json.dumps(diagnostics_logger.from_session(session).to_dict(), indent=2),
            encoding="utf-8",
        )
        if export:
            ExportAgent(target / "exports").export_all(session)
        return target

    def load(self, session_id_or_dir: str | Path) -> MeetingSession:
        path = Path(session_id_or_dir)
        if not path.exists():
            path = self.root / str(session_id_or_dir)
        payload = json.loads((path / "session.json").read_text(encoding="utf-8"))
        return self._session_from_dict(payload)

    def delete(self, session_id_or_dir: str | Path) -> None:
        path = Path(session_id_or_dir)
        if not path.exists():
            path = self.root / str(session_id_or_dir)
        if path.exists() and path.is_dir():
            shutil.rmtree(path)

    def list(self) -> list[SessionSummary]:
        if not self.root.exists():
            return []
        summaries = []
        for path in sorted(self.root.iterdir(), reverse=True):
            session_file = path / "session.json"
            if not session_file.exists():
                continue
            try:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            transcript = str(payload.get("transcription", {}).get("full_transcript", ""))
            notes_summary = str(payload.get("notes", {}).get("summary", ""))
            summaries.append(
                SessionSummary(
                    session_id=path.name,
                    title=self._title(payload, transcript),
                    created_at=str(payload.get("created_at", "")),
                    audio_name=Path(str(payload.get("audio", {}).get("path", ""))).name,
                    transcript_preview=transcript[:180],
                    notes_preview=notes_summary[:180],
                    notes_backend=str(payload.get("notes", {}).get("backend", "")),
                    path=path,
                )
            )
        return summaries

    def search(self, query: str) -> list[SessionSummary]:
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return self.list()
        matches = []
        for summary in self.list():
            haystack = (
                f"{summary.title} {summary.audio_name} {summary.transcript_preview} "
                f"{summary.notes_preview} {summary.notes_backend}"
            ).lower()
            if all(term in haystack for term in terms):
                matches.append(summary)
        return matches

    def _copy_audio(self, audio: AudioMetadata, target: Path) -> Path:
        suffix = audio.path.suffix or f".{audio.format}"
        destination = target / f"audio{suffix}"
        if audio.path.exists() and audio.path.resolve() != destination.resolve():
            shutil.copy2(audio.path, destination)
        return destination

    def _session_from_dict(self, payload: dict[str, Any]) -> MeetingSession:
        audio_raw = payload["audio"]
        audio = AudioMetadata(
            source=str(audio_raw.get("source", "file")),
            path=Path(str(audio_raw.get("session_audio_path") or audio_raw.get("path", ""))),
            duration_seconds=float(audio_raw.get("duration_seconds", 0)),
            format=str(audio_raw.get("format", "wav")),
            sample_rate=int(audio_raw.get("sample_rate", 16000)),
        )
        transcript_raw = payload["transcription"]
        segments = [
            TranscriptSegment(start=str(item["start"]), end=str(item["end"]), text=str(item["text"]))
            for item in transcript_raw.get("segments", [])
        ]
        transcription = TranscriptionResult(
            segments=segments,
            full_transcript=str(transcript_raw.get("full_transcript", "")),
            backend=str(transcript_raw.get("backend", "")),
            latency_ms=int(transcript_raw.get("latency_ms", 0)),
            real_time_factor=float(transcript_raw.get("real_time_factor", 0)),
            warnings=[str(item) for item in transcript_raw.get("warnings", [])],
        )
        chunks = [
            TranscriptChunk(
                chunk_id=int(item["chunk_id"]),
                start=str(item["start"]),
                end=str(item["end"]),
                text=str(item["text"]),
            )
            for item in payload.get("chunks", [])
        ]
        notes_raw = payload["notes"]
        notes = MeetingNotes(
            summary=str(notes_raw.get("summary", "")),
            important_points=[str(item) for item in notes_raw.get("important_points", [])],
            decisions=[str(item) for item in notes_raw.get("decisions", [])],
            action_items=[
                ActionItem(
                    owner=str(item.get("owner", "not mentioned")),
                    task=str(item.get("task", "not mentioned")),
                    deadline=str(item.get("deadline", "not mentioned")),
                    evidence=str(item.get("evidence", "not mentioned")),
                )
                for item in notes_raw.get("action_items", [])
            ],
            open_questions=[str(item) for item in notes_raw.get("open_questions", [])],
            risks_blockers=[str(item) for item in notes_raw.get("risks_blockers", [])],
            follow_up_email=str(notes_raw.get("follow_up_email", "")),
            transcript_reference=[str(item) for item in notes_raw.get("transcript_reference", [])],
            backend=str(notes_raw.get("backend", "")),
            elapsed_ms=int(notes_raw.get("elapsed_ms", 0)),
            fallback_reason=str(notes_raw.get("fallback_reason", "")),
            validation_messages=[str(item) for item in notes_raw.get("validation_messages", [])],
        )
        return MeetingSession(audio=audio, transcription=transcription, chunks=chunks, notes=notes)

    def _title(self, payload: dict[str, Any], transcript: str) -> str:
        audio_name = Path(str(payload.get("audio", {}).get("path", ""))).stem
        if transcript:
            return transcript[:60].strip() + ("..." if len(transcript) > 60 else "")
        return audio_name or payload.get("session_id", "Meeting")

    def _safe_session_id(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
        return safe.strip("-") or datetime.now().strftime("%Y%m%dT%H%M%S%f")
