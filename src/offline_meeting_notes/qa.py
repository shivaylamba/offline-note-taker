from __future__ import annotations

import re

from .models import ActionItem, MeetingNotes, QAAnswer, TranscriptChunk, TranscriptSegment
from .summarization import FallbackMeetingNotesRunner, MeetingNotesInput

STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "any",
    "did",
    "do",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "only",
    "the",
    "there",
    "to",
    "was",
    "were",
    "what",
    "who",
}


class MeetingQAAgent:
    def answer(
        self,
        question: str,
        segments: list[TranscriptSegment],
        notes: MeetingNotes | None = None,
    ) -> QAAnswer:
        terms = self._terms(question)
        if not terms:
            return QAAnswer("Ask a question about the transcript.", [])

        if self._is_action_query(question):
            action_answer = self._answer_actions(question, segments, notes)
            if action_answer:
                return action_answer

        scored: list[tuple[int, TranscriptSegment]] = []
        for segment in segments:
            text = segment.text.lower()
            score = sum(1 for term in terms if term in text)
            if self._is_action_query(question) and self._looks_actionable(text):
                score += 2
            if score:
                scored.append((score, segment))

        if not scored:
            return QAAnswer("The transcript does not mention it.", [])

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [segment for _, segment in scored[:3]]
        citations = [f"{segment.start}-{segment.end}" for segment in selected]
        answer_text = " ".join(segment.text for segment in selected)
        return QAAnswer(answer_text, citations)

    def _terms(self, question: str) -> list[str]:
        return [
            term
            for term in re.findall(r"[a-zA-Z0-9]+", question.lower())
            if len(term) > 2 and term not in STOP_WORDS
        ]

    def _is_action_query(self, question: str) -> bool:
        lowered = question.lower()
        return "action" in lowered or "owner" in lowered or "own" in lowered or "task" in lowered

    def _looks_actionable(self, text: str) -> bool:
        return (
            "will" in text
            or "action item" in text
            or "needs to" in text
            or "task" in text
            or "takeaway" in text
            or "would be to" in text
        )

    def _answer_actions(
        self,
        question: str,
        segments: list[TranscriptSegment],
        notes: MeetingNotes | None,
    ) -> QAAnswer | None:
        meeting_notes = notes or self._extract_notes(segments)
        if not meeting_notes.action_items:
            return QAAnswer("The transcript does not mention an action item.", [])

        items = self._matching_action_items(question, meeting_notes.action_items) or meeting_notes.action_items
        citations = self._action_citations(items)
        lines = ["Action items mentioned:"]
        for item in items:
            lines.append(
                f"- Owner: {item.owner}; Task: {item.task}; Deadline: {item.deadline}; Evidence: {item.evidence}"
            )
        return QAAnswer("\n".join(lines), citations)

    def _matching_action_items(self, question: str, items: list[ActionItem]) -> list[ActionItem]:
        terms = [term for term in self._terms(question) if term not in {"action", "item", "items", "task", "tasks"}]
        if not terms:
            return []
        matches = []
        for item in items:
            haystack = f"{item.owner} {item.task} {item.evidence}".lower()
            if any(term in haystack for term in terms):
                matches.append(item)
        return matches

    def _extract_notes(self, segments: list[TranscriptSegment]) -> MeetingNotes:
        if not segments:
            return FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=[], segments=[]))
        chunk = TranscriptChunk(
            chunk_id=1,
            start=segments[0].start,
            end=segments[-1].end,
            text=" ".join(segment.text for segment in segments),
        )
        return FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=[chunk], segments=segments))

    def _action_citations(self, items: list[ActionItem]) -> list[str]:
        citations = []
        for item in items:
            match = re.search(r"\d\d:\d\d:\d\d\.\d{3}-\d\d:\d\d:\d\d\.\d{3}", item.evidence)
            if match and match.group(0) not in citations:
                citations.append(match.group(0))
        return citations
