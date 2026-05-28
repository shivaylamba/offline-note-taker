from offline_meeting_notes.audio import AudioManager
from offline_meeting_notes.pipeline import MeetingPipeline
from offline_meeting_notes.session_store import SessionStore
from offline_meeting_notes.summarization import FallbackMeetingNotesRunner


def test_session_store_create_open_search_delete(tmp_path) -> None:  # type: ignore[no-untyped-def]
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio)
    store = SessionStore(tmp_path)

    session_dir = store.save(session, export=True)

    assert (session_dir / "session.json").exists()
    assert (session_dir / "transcript.json").exists()
    assert (session_dir / "notes.json").exists()
    assert (session_dir / "diagnostics.json").exists()
    assert (session_dir / "exports" / "meeting_notes.md").exists()
    assert store.load(session_dir).notes.action_items
    assert store.search("Snapdragon")

    store.delete(session_dir)

    assert not session_dir.exists()
