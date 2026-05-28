from offline_meeting_notes.models import TranscriptChunk, TranscriptSegment
from pathlib import Path

from offline_meeting_notes.summarization import (
    FallbackMeetingNotesRunner,
    MeetingNotesInput,
    Qwen3GenieMeetingNotesRunner,
)


def test_fallback_summary_does_not_invent_missing_action_fields() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:05.000",
            "We discussed the launch plan. Action item: prepare the demo.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:05.000", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    assert notes.action_items
    assert notes.action_items[0].owner == "not mentioned"
    assert notes.action_items[0].deadline == "not mentioned"


def test_decisions_are_not_invented() -> None:
    segments = [TranscriptSegment("00:00:00.000", "00:00:03.000", "We reviewed the roadmap.")]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:03.000", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    assert notes.decisions == []
    assert "- not mentioned" in notes.to_markdown()


def test_explicit_action_owner_and_deadline_are_extracted() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:05.000",
            "Alice will send the launch notes by Friday.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:05.000", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    assert notes.action_items[0].owner == "Alice"
    assert notes.action_items[0].task == "send the launch notes"
    assert notes.action_items[0].deadline == "Friday"


def test_takeaway_follow_up_is_extracted_as_action_item() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:20.000",
            "The main takeaway would be to then go ahead and push the code on GitHub.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:20.000", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    assert notes.action_items
    assert notes.action_items[0].owner == "not mentioned"
    assert notes.action_items[0].deadline == "not mentioned"
    assert "push the code on GitHub" in notes.action_items[0].task


def test_named_owners_are_extracted_from_demo_phrasing() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:37.102",
            "Our major takeaway for today's meeting is number one, Sam, you need to build the entire architecture of our application. "
            "Ron, you are supposed to go ahead and build the backend. "
            "And the biggest takeaway or the task for Simon is that you need to coordinate the entire effort for bringing the app live on the Play Store.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:37.102", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    by_owner = {item.owner: item.task for item in notes.action_items}
    assert by_owner["Sam"] == "build the entire architecture of our application"
    assert by_owner["Ron"] == "build the backend"
    assert by_owner["Simon"] == "coordinate the entire effort for bringing the app live on the Play Store"


def test_responsible_and_role_phrasing_extract_action_items() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:44.044",
            "So Simon, you are responsible for delivering the app by tomorrow. "
            "and Jack your DevOps and back in lead, to ensure that everything works and it does not break.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:44.044", segments[0].text)]

    notes = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=chunks, segments=segments))

    by_owner = {item.owner: item for item in notes.action_items}
    assert by_owner["Simon"].task == "delivering the app"
    assert by_owner["Simon"].deadline == "tomorrow"
    assert by_owner["Jack"].task == "ensure that everything works and it does not break"


def test_qwen_genie_control_markers_are_stripped() -> None:
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    assert runner._stream_visible_text("[BEGIN]:Summary\n[END") == "Summary\n"
    assert runner._stream_visible_text("[BEGIN]:Summary\n[EN") == "Summary\n"
    assert runner._extract_output("[BEGIN]:Summary\n[END") == "Summary"


def test_qwen_genie_prompt_includes_grounded_action_hints() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:20.000",
            "Number four would be to push this code to GitHub.",
        )
    ]
    chunks = [TranscriptChunk(1, "00:00:00.000", "00:00:20.000", segments[0].text)]
    payload = MeetingNotesInput(chunks=chunks, segments=segments)
    grounded = FallbackMeetingNotesRunner().generate(payload)
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    prompt = runner._prompt(payload)

    assert "Return only valid JSON" in prompt
    assert "push this code to GitHub" in prompt


def test_qwen_genie_json_notes_parse_action_items() -> None:
    fallback = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=[], segments=[]))
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    notes = runner._notes_from_llm_text(
        """
        {
          "summary": "The meeting assigned launch work.",
          "important_points": ["Simon owns delivery."],
          "decisions": [],
          "action_items": [
            {
              "owner": "Simon",
              "task": "deliver the app",
              "deadline": "tomorrow",
              "evidence": "00:00:00.000-00:00:44.044: Simon is responsible for delivering the app by tomorrow."
            }
          ],
          "open_questions": [],
          "risks_blockers": [],
          "follow_up_email": "Hi team, please follow up on the action items.",
          "transcript_reference": ["00:00:00.000-00:00:44.044"]
        }
        """,
        fallback,
    )

    assert notes.summary == "The meeting assigned launch work."
    assert notes.action_items[0].owner == "Simon"
    assert notes.action_items[0].task == "deliver the app"
    assert notes.action_items[0].deadline == "tomorrow"


def test_qwen_genie_drops_decisions_when_transcript_has_no_decision_language() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:44.044",
            "Simon is the product owner. Jack is DevOps lead.",
        )
    ]
    fallback = FallbackMeetingNotesRunner().generate(
        MeetingNotesInput(chunks=[TranscriptChunk(1, segments[0].start, segments[0].end, segments[0].text)], segments=segments)
    )
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    notes = runner._notes_from_llm_text(
        """
        {
          "summary": "Roles were discussed.",
          "important_points": ["Simon is product owner", "Jack is DevOps lead"],
          "decisions": ["Simon is the product owner", "Jack is DevOps lead"],
          "action_items": [],
          "open_questions": [],
          "risks_blockers": [],
          "follow_up_email": "not mentioned",
          "transcript_reference": ["00:00:00.000-00:00:44.044"]
        }
        """,
        fallback,
    )

    assert notes.decisions == []


def test_qwen_genie_repairs_missing_final_json_brace() -> None:
    fallback = FallbackMeetingNotesRunner().generate(MeetingNotesInput(chunks=[], segments=[]))
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    notes = runner._notes_from_llm_text(
        """
        {
          "summary": "Launch responsibilities were assigned.",
          "important_points": ["Simon owns delivery."],
          "decisions": [],
          "action_items": [
            {"owner": "Jack", "task": "ensure everything works", "deadline": "not mentioned", "evidence": "Jack... to ensure everything works"}
          ],
          "open_questions": [],
          "risks_blockers": ["not mentioned"],
          "follow_up_email": "not mentioned",
          "transcript_reference": "00:00:00.000-00:00:44.044"
        """,
        fallback,
    )

    assert notes.action_items[0].owner == "Jack"
    assert notes.risks_blockers == []
    assert notes.transcript_reference == ["00:00:00.000-00:00:44.044"]


def test_qwen_genie_rejects_schema_placeholders() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:44.044",
            "Simon, you are responsible for delivering the app by tomorrow.",
        )
    ]
    fallback = FallbackMeetingNotesRunner().generate(
        MeetingNotesInput(chunks=[TranscriptChunk(1, segments[0].start, segments[0].end, segments[0].text)], segments=segments)
    )
    runner = Qwen3GenieMeetingNotesRunner(genie_config=Path("."), qairt_home=Path("."))

    notes = runner._notes_from_llm_text(
        """
        {
          "summary": "string",
          "important_points": ["string"],
          "decisions": ["string"],
          "action_items": [{"owner": "string", "task": "string", "deadline": "string", "evidence": "string"}],
          "open_questions": ["string"],
          "risks_blockers": ["string"],
          "follow_up_email": "string",
          "transcript_reference": ["string"]
        }
        """,
        fallback,
    )

    assert notes.summary == fallback.summary
    assert notes.action_items == fallback.action_items
