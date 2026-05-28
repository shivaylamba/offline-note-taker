from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import ActionItem, MeetingNotes, MeetingSession
from .runtime_doctor import run_runtime_doctor


TIMESTAMP_RE = re.compile(r"\d\d:\d\d:\d\d\.\d{3}-\d\d:\d\d:\d\d\.\d{3}")


@dataclass(slots=True)
class NotesQualityReport:
    action_item_count: int
    citation_coverage: float
    unsupported_decision_count: int
    fallback_used: bool
    action_grounding: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_notes(session: MeetingSession) -> NotesQualityReport:
    return NotesQualityReport(
        action_item_count=len(session.notes.action_items),
        citation_coverage=_citation_coverage(session.notes),
        unsupported_decision_count=_unsupported_decisions(session),
        fallback_used=bool(session.notes.fallback_reason or "fallback" in session.notes.backend),
        action_grounding=[classify_action_grounding(item, session.notes).to_dict() for item in session.notes.action_items],
    )


@dataclass(slots=True)
class ActionGrounding:
    owner: str
    task: str
    status: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def classify_action_grounding(item: ActionItem, notes: MeetingNotes) -> ActionGrounding:
    if notes.fallback_reason or "fallback" in notes.backend:
        status = "fallback"
    elif TIMESTAMP_RE.search(item.evidence):
        status = "grounded"
    elif item.evidence and item.evidence.lower() != "not mentioned":
        status = "weak evidence"
    else:
        status = "weak evidence"
    return ActionGrounding(owner=item.owner, task=item.task, status=status, evidence=item.evidence)


def proof_report_text(
    session: MeetingSession,
    diagnostics_path: str | Path = "",
    session_path: str | Path = "",
    detect_npu: bool = True,
) -> str:
    quality = evaluate_notes(session)
    npu_status = _npu_status(detect_npu)
    lines = [
        "Local Proof Report",
        "==================",
        "",
        f"Audio: {session.audio.path.name} ({session.audio.duration_seconds:.1f}s)",
        f"Whisper backend: {session.transcription.backend}",
        f"Whisper latency: {session.transcription.latency_ms} ms",
        f"Whisper real-time factor: {session.transcription.real_time_factor}",
        f"Notes backend: {session.notes.backend}",
        f"Qwen elapsed: {session.notes.elapsed_ms} ms",
        f"Fallback: {session.notes.fallback_reason or 'none'}",
        f"NPU status: {npu_status}",
        f"Citation coverage: {quality.citation_coverage:.0%}",
        f"Unsupported decisions: {quality.unsupported_decision_count}",
        f"Diagnostics: {diagnostics_path or 'not written'}",
        f"Session: {session_path or 'not saved'}",
        "",
        "Grounding",
        "---------",
    ]
    if quality.action_grounding:
        for item in quality.action_grounding:
            lines.append(f"- [{item['status']}] {item['owner']}: {item['task']} ({item['evidence']})")
    else:
        lines.append("- no action items")
    if session.notes.validation_messages:
        lines.extend(["", "Validation", "----------"])
        lines.extend(f"- {message}" for message in session.notes.validation_messages)
    return "\n".join(lines)


def proof_report_dict(
    session: MeetingSession,
    diagnostics_path: str | Path = "",
    session_path: str | Path = "",
    detect_npu: bool = True,
) -> dict[str, object]:
    quality = evaluate_notes(session)
    return {
        "audio": session.audio.to_dict(),
        "whisper_backend": session.transcription.backend,
        "whisper_latency_ms": session.transcription.latency_ms,
        "whisper_real_time_factor": session.transcription.real_time_factor,
        "notes_backend": session.notes.backend,
        "qwen_elapsed_ms": session.notes.elapsed_ms,
        "fallback_reason": session.notes.fallback_reason,
        "npu_status": _npu_status(detect_npu),
        "quality": quality.to_dict(),
        "validation_messages": list(session.notes.validation_messages),
        "diagnostics_path": str(diagnostics_path) if diagnostics_path else "",
        "session_path": str(session_path) if session_path else "",
    }


def _citation_coverage(notes: MeetingNotes) -> float:
    evidence_bearing = len(notes.important_points) + len(notes.decisions) + len(notes.open_questions) + len(notes.risks_blockers)
    evidence_bearing += len(notes.action_items)
    if evidence_bearing == 0:
        return 1.0
    cited = sum(1 for value in notes.important_points + notes.decisions + notes.open_questions + notes.risks_blockers if TIMESTAMP_RE.search(value))
    cited += sum(1 for item in notes.action_items if TIMESTAMP_RE.search(item.evidence))
    return round(cited / evidence_bearing, 4)


def _unsupported_decisions(session: MeetingSession) -> int:
    transcript = session.transcription.full_transcript.lower()
    decision_language = ("decided", "decision", "agreed", "approved", "confirmed", "go with")
    if any(term in transcript for term in decision_language):
        return 0
    return len(session.notes.decisions)


def _npu_status(detect_npu: bool) -> str:
    if not detect_npu:
        return "not checked"
    report = run_runtime_doctor(detect_npu=True)
    for check in report.checks:
        if check.name == "NPU device":
            return f"{check.status}: {check.message}"
    return "not checked"
