from offline_meeting_notes.models import TranscriptSegment
from offline_meeting_notes.qa import MeetingQAAgent


def test_qa_answers_only_from_transcript() -> None:
    segments = [
        TranscriptSegment("00:00:00.000", "00:00:04.000", "Alice will send the launch notes by Friday."),
        TranscriptSegment("00:00:05.000", "00:00:08.000", "The budget topic was not discussed."),
    ]

    answer = MeetingQAAgent().answer("Who owns the launch notes?", segments)

    assert "Alice will send" in answer.answer
    assert "Owner: Alice" in answer.answer
    assert "Task: send the launch notes" in answer.answer
    assert answer.citations == ["00:00:00.000-00:00:04.000"]


def test_qa_says_not_mentioned_when_missing() -> None:
    segments = [TranscriptSegment("00:00:00.000", "00:00:04.000", "We discussed the launch notes.")]

    answer = MeetingQAAgent().answer("What was the budget?", segments)

    assert answer.answer == "The transcript does not mention it."
    assert answer.citations == []


def test_qa_action_items_uses_structured_extraction() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:41.236",
            "The main tasks for us is to test the entire flow to push the code to GitHub and number three write a Medium article first.",
        )
    ]

    answer = MeetingQAAgent().answer("what is the action item and who is the owner for that?", segments)

    assert "Owner: not mentioned" in answer.answer
    assert "test the entire flow" in answer.answer
    assert "push the code to GitHub" in answer.answer
    assert "write a Medium article" in answer.answer
    assert answer.citations == ["00:00:00.000-00:00:41.236"]


def test_qa_filters_action_items_by_owner() -> None:
    segments = [
        TranscriptSegment(
            "00:00:00.000",
            "00:00:37.102",
            "Our major takeaway for today's meeting is number one, Sam, you need to build the entire architecture of our application. "
            "Ron, you are supposed to go ahead and build the backend. "
            "And the biggest takeaway or the task for Simon is that you need to coordinate the entire effort for bringing the app live on the Play Store.",
        )
    ]

    answer = MeetingQAAgent().answer("What is the task for Simon?", segments)

    assert "Owner: Simon" in answer.answer
    assert "coordinate the entire effort for bringing the app live on the Play Store" in answer.answer
    assert "Owner: Sam" not in answer.answer
    assert "Owner: Ron" not in answer.answer
