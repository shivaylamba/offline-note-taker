from pathlib import Path

from offline_meeting_notes.models import TranscriptChunk, TranscriptSegment
from offline_meeting_notes.quality import evaluate_notes
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner, MeetingNotesInput, Qwen3GenieMeetingNotesRunner
from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.pipeline import MeetingPipeline


def test_quality_report_tracks_citations_and_fallback() -> None:
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio)

    report = evaluate_notes(session)

    assert report.action_item_count >= 1
    assert report.citation_coverage > 0
    assert report.fallback_used


def test_qwen_action_validation_drops_unsupported_action_item() -> None:
    transcript = Path("tests/fixtures/clear_action_items.txt").read_text(encoding="utf-8")
    segment = TranscriptSegment("00:00:00.000", "00:00:10.000", transcript)
    payload = MeetingNotesInput(chunks=[TranscriptChunk(1, segment.start, segment.end, transcript)], segments=[segment])
    fallback = FallbackMeetingNotesRunner().generate(payload)
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    notes = runner._notes_from_llm_text(
        """
        {
          "summary": "Launch work was assigned.",
          "important_points": ["Alice sends notes."],
          "decisions": ["Use Snapdragon NPU demo path."],
          "action_items": [
            {"owner": "Alice", "task": "send the launch notes", "deadline": "Friday", "evidence": "00:00:00.000-00:00:10.000: Alice will send the launch notes by Friday."},
            {"owner": "Carol", "task": "buy conference tickets", "deadline": "tomorrow", "evidence": "not mentioned"}
          ],
          "open_questions": [],
          "risks_blockers": [],
          "follow_up_email": "Follow up on the listed items.",
          "transcript_reference": ["00:00:00.000-00:00:10.000"]
        }
        """,
        fallback,
    )

    owners = {item.owner for item in notes.action_items}
    assert "Alice" in owners
    assert "Carol" not in owners
