from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.pipeline import MeetingPipeline
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner


def test_sample_meeting_generates_useful_fallback_notes() -> None:
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio)

    assert "Alice will send the launch notes by Friday" in session.transcription.full_transcript
    assert session.notes.action_items[0].owner == "Alice"
    assert session.notes.action_items[0].deadline == "Friday"
    assert session.notes.decisions
    assert session.notes.risks_blockers
