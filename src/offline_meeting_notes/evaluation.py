from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import TranscriptChunk, TranscriptSegment
from .quality import evaluate_notes
from .summarization import FallbackMeetingNotesRunner, MeetingNotesInput


DEFAULT_FIXTURE_DIR = Path("tests") / "fixtures" / "eval"


@dataclass(slots=True)
class ExpectedAction:
    owner: str
    task_contains: str
    deadline: str = "not mentioned"


@dataclass(slots=True)
class EvalFixture:
    name: str
    transcript: str
    expected_actions: list[ExpectedAction] = field(default_factory=list)
    expected_decision_count: int = 0


@dataclass(slots=True)
class EvalCaseResult:
    name: str
    expected_actions: int
    extracted_actions: int
    owner_correct: int
    deadline_correct: int
    action_matches: int
    unsupported_decisions: int
    citation_coverage: float
    fallback_used: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvalReport:
    cases: list[EvalCaseResult]
    totals: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"cases": [case.to_dict() for case in self.cases], "totals": dict(self.totals)}

    def to_markdown_table(self) -> str:
        lines = [
            "| Fixture | Expected Actions | Extracted | Owner Acc. | Deadline Acc. | Citation Coverage | Unsupported Decisions |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for case in self.cases:
            owner_acc = _ratio(case.owner_correct, case.expected_actions)
            deadline_acc = _ratio(case.deadline_correct, case.expected_actions)
            lines.append(
                f"| {case.name} | {case.expected_actions} | {case.extracted_actions} | "
                f"{owner_acc:.0%} | {deadline_acc:.0%} | {case.citation_coverage:.0%} | {case.unsupported_decisions} |"
            )
        totals = self.totals
        lines.append(
            f"| **Total** | {totals['expected_actions']} | {totals['extracted_actions']} | "
            f"{totals['owner_accuracy']:.0%} | {totals['deadline_accuracy']:.0%} | "
            f"{totals['citation_coverage']:.0%} | {totals['unsupported_decisions']} |"
        )
        return "\n".join(lines)

    def to_text(self) -> str:
        return "\n".join(["Offline Note Taker Eval", "=======================", "", self.to_markdown_table()])


def run_eval(fixture_dir: str | Path = DEFAULT_FIXTURE_DIR) -> EvalReport:
    fixtures = load_fixtures(fixture_dir)
    results = [evaluate_fixture(fixture) for fixture in fixtures]
    return EvalReport(cases=results, totals=_totals(results))


def load_fixtures(fixture_dir: str | Path = DEFAULT_FIXTURE_DIR) -> list[EvalFixture]:
    root = Path(fixture_dir)
    fixtures = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append(
            EvalFixture(
                name=str(payload.get("name") or path.stem),
                transcript=str(payload["transcript"]),
                expected_actions=[
                    ExpectedAction(
                        owner=str(item.get("owner", "not mentioned")),
                        task_contains=str(item.get("task_contains", "")),
                        deadline=str(item.get("deadline", "not mentioned")),
                    )
                    for item in payload.get("expected_actions", [])
                ],
                expected_decision_count=int(payload.get("expected_decision_count", 0)),
            )
        )
    if not fixtures:
        raise ValueError(f"No eval fixtures found in {root}")
    return fixtures


def evaluate_fixture(fixture: EvalFixture) -> EvalCaseResult:
    segment = TranscriptSegment("00:00:00.000", "00:00:30.000", fixture.transcript)
    payload = MeetingNotesInput(
        chunks=[TranscriptChunk(1, segment.start, segment.end, fixture.transcript)],
        segments=[segment],
    )
    notes = FallbackMeetingNotesRunner().generate(payload)
    session = _session_for_quality(segment, notes, payload.chunks)
    quality = evaluate_notes(session)
    matched_indices: set[int] = set()
    owner_correct = 0
    deadline_correct = 0
    action_matches = 0

    for expected in fixture.expected_actions:
        match_index = _match_action(expected, notes.action_items, matched_indices)
        if match_index is None:
            continue
        matched_indices.add(match_index)
        action_matches += 1
        actual = notes.action_items[match_index]
        if actual.owner.lower() == expected.owner.lower():
            owner_correct += 1
        if actual.deadline.lower() == expected.deadline.lower():
            deadline_correct += 1

    return EvalCaseResult(
        name=fixture.name,
        expected_actions=len(fixture.expected_actions),
        extracted_actions=len(notes.action_items),
        owner_correct=owner_correct,
        deadline_correct=deadline_correct,
        action_matches=action_matches,
        unsupported_decisions=quality.unsupported_decision_count,
        citation_coverage=quality.citation_coverage,
        fallback_used=quality.fallback_used,
    )


def _match_action(expected: ExpectedAction, actions, used: set[int]) -> int | None:  # type: ignore[no-untyped-def]
    needle = expected.task_contains.lower()
    for index, action in enumerate(actions):
        if index in used:
            continue
        if needle and needle in action.task.lower():
            return index
    return None


def _session_for_quality(segment: TranscriptSegment, notes, chunks):  # type: ignore[no-untyped-def]
    from .models import AudioMetadata, MeetingSession, TranscriptionResult

    audio = AudioMetadata(source="fixture", path=Path(f"{segment.start}.wav"), duration_seconds=30.0, format="wav", sample_rate=16000)
    transcription = TranscriptionResult(
        segments=[segment],
        full_transcript=segment.text,
        backend="fixture",
        latency_ms=0,
        real_time_factor=0.0,
    )
    return MeetingSession(audio=audio, transcription=transcription, chunks=chunks, notes=notes)


def _totals(results: list[EvalCaseResult]) -> dict[str, Any]:
    expected = sum(item.expected_actions for item in results)
    extracted = sum(item.extracted_actions for item in results)
    owner_correct = sum(item.owner_correct for item in results)
    deadline_correct = sum(item.deadline_correct for item in results)
    unsupported = sum(item.unsupported_decisions for item in results)
    citation = sum(item.citation_coverage for item in results) / len(results) if results else 0.0
    return {
        "fixtures": len(results),
        "expected_actions": expected,
        "extracted_actions": extracted,
        "owner_accuracy": _ratio(owner_correct, expected),
        "deadline_accuracy": _ratio(deadline_correct, expected),
        "citation_coverage": round(citation, 4),
        "unsupported_decisions": unsupported,
        "fallback_rate": _ratio(sum(1 for item in results if item.fallback_used), len(results)),
    }


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 1.0
    return round(float(numerator) / float(denominator), 4)
