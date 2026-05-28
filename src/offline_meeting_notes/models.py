from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AudioMetadata:
    source: str
    path: Path
    duration_seconds: float
    format: str
    sample_rate: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(slots=True)
class TranscriptSegment:
    start: str
    end: str
    text: str

    def to_srt_block(self, index: int) -> str:
        return f"{index}\n{self.start.replace('.', ',')} --> {self.end.replace('.', ',')}\n{self.text.strip()}\n"

    def to_vtt_block(self) -> str:
        return f"{self.start} --> {self.end}\n{self.text.strip()}\n"


@dataclass(slots=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    full_transcript: str
    backend: str
    latency_ms: int
    real_time_factor: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [asdict(segment) for segment in self.segments],
            "full_transcript": self.full_transcript,
            "backend": self.backend,
            "latency_ms": self.latency_ms,
            "real_time_factor": self.real_time_factor,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class CleanTranscript:
    clean_transcript: str
    uncertain_segments: list[TranscriptSegment] = field(default_factory=list)


@dataclass(slots=True)
class TranscriptChunk:
    chunk_id: int
    start: str
    end: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ActionItem:
    owner: str
    task: str
    deadline: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class MeetingNotes:
    summary: str
    important_points: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    risks_blockers: list[str]
    follow_up_email: str
    transcript_reference: list[str]
    backend: str

    def to_markdown(self) -> str:
        decisions = self.decisions or ["not mentioned"]
        open_questions = self.open_questions or ["not mentioned"]
        risks = self.risks_blockers or ["not mentioned"]
        references = self.transcript_reference or ["not mentioned"]

        lines = [
            "# Meeting Notes",
            "",
            "## Summary",
            self.summary or "not mentioned",
            "",
            "## Important Points",
            *[f"- {point}" for point in (self.important_points or ["not mentioned"])],
            "",
            "## Key Decisions",
            *[f"- {decision}" for decision in decisions],
            "",
            "## Action Items",
            "",
            "| Owner | Task | Deadline | Evidence |",
            "|---|---|---|---|",
        ]

        if self.action_items:
            for item in self.action_items:
                lines.append(f"| {item.owner} | {item.task} | {item.deadline} | {item.evidence} |")
        else:
            lines.append("| not mentioned | not mentioned | not mentioned | not mentioned |")

        lines.extend(
            [
                "",
                "## Open Questions",
                *[f"- {question}" for question in open_questions],
                "",
                "## Risks / Blockers",
                *[f"- {risk}" for risk in risks],
                "",
                "## Follow-Up Email Draft",
                self.follow_up_email,
                "",
                "## Transcript Reference",
                *[f"- {reference}" for reference in references],
                "",
                "## Backend",
                self.backend,
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "important_points": list(self.important_points),
            "decisions": list(self.decisions),
            "action_items": [item.to_dict() for item in self.action_items],
            "open_questions": list(self.open_questions),
            "risks_blockers": list(self.risks_blockers),
            "follow_up_email": self.follow_up_email,
            "transcript_reference": list(self.transcript_reference),
            "backend": self.backend,
        }


@dataclass(slots=True)
class QAAnswer:
    answer: str
    citations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MeetingSession:
    audio: AudioMetadata
    transcription: TranscriptionResult
    chunks: list[TranscriptChunk]
    notes: MeetingNotes

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio": self.audio.to_dict(),
            "transcription": self.transcription.to_dict(),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "notes": self.notes.to_dict(),
        }
