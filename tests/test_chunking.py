from offline_meeting_notes.chunking import ChunkingAgent
from offline_meeting_notes.models import TranscriptSegment


def test_chunking_preserves_order_and_timestamps() -> None:
    segments = [
        TranscriptSegment("00:00:00.000", "00:00:01.000", "Alpha launch discussion."),
        TranscriptSegment("00:00:01.000", "00:00:02.000", "Beta timeline discussion."),
        TranscriptSegment("00:00:02.000", "00:00:03.000", "Gamma risk discussion."),
    ]

    chunks = ChunkingAgent(max_chars=35).chunk_segments(segments)

    assert [chunk.chunk_id for chunk in chunks] == [1, 2, 3]
    assert chunks[0].start == "00:00:00.000"
    assert chunks[-1].end == "00:00:03.000"
    assert "Alpha" in chunks[0].text
    assert "Gamma" in chunks[-1].text
