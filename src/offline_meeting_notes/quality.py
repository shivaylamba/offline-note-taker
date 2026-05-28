from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .models import MeetingNotes, MeetingSession


TIMESTAMP_RE = re.compile(r"\d\d:\d\d:\d\d\.\d{3}-\d\d:\d\d:\d\d\.\d{3}")


@dataclass(slots=True)
class NotesQualityReport:
    action_item_count: int
    citation_coverage: float
    unsupported_decision_count: int
    fallback_used: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_notes(session: MeetingSession) -> NotesQualityReport:
    return NotesQualityReport(
        action_item_count=len(session.notes.action_items),
        citation_coverage=_citation_coverage(session.notes),
        unsupported_decision_count=_unsupported_decisions(session),
        fallback_used=bool(session.notes.fallback_reason or "fallback" in session.notes.backend),
    )


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
