from __future__ import annotations

import re

from .models import TranscriptChunk, TranscriptSegment


class ChunkingAgent:
    def __init__(self, max_chars: int = 2800) -> None:
        self.max_chars = max_chars

    def chunk_segments(self, segments: list[TranscriptSegment]) -> list[TranscriptChunk]:
        if not segments:
            return []

        chunks: list[TranscriptChunk] = []
        current: list[TranscriptSegment] = []
        current_len = 0

        for segment in segments:
            segment_len = len(segment.text)
            if current and current_len + segment_len + 1 > self.max_chars:
                chunks.append(self._build_chunk(len(chunks) + 1, current))
                current = []
                current_len = 0
            current.append(segment)
            current_len += segment_len + 1

        if current:
            chunks.append(self._build_chunk(len(chunks) + 1, current))
        return chunks

    def chunk_text(self, text: str) -> list[TranscriptChunk]:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        segments = [
            TranscriptSegment(start="00:00:00.000", end="00:00:00.000", text=sentence)
            for sentence in sentences
        ]
        return self.chunk_segments(segments)

    def _build_chunk(self, chunk_id: int, segments: list[TranscriptSegment]) -> TranscriptChunk:
        return TranscriptChunk(
            chunk_id=chunk_id,
            start=segments[0].start,
            end=segments[-1].end,
            text=" ".join(segment.text for segment in segments).strip(),
        )
