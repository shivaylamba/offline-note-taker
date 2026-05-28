from __future__ import annotations

import re

from .models import CleanTranscript, TranscriptSegment, TranscriptionResult

FILLER_REPETITIONS = re.compile(r"\b(um|uh|ah|er)(?:[,\s]+\1\b)+", re.IGNORECASE)


class TranscriptCleanupAgent:
    def clean(self, transcription: TranscriptionResult) -> CleanTranscript:
        cleaned_segments: list[TranscriptSegment] = []
        uncertain: list[TranscriptSegment] = []

        for segment in transcription.segments:
            text = self._clean_text(segment.text)
            cleaned = TranscriptSegment(segment.start, segment.end, text)
            cleaned_segments.append(cleaned)
            if "[unclear]" in text.lower() or "[inaudible]" in text.lower():
                uncertain.append(cleaned)

        return CleanTranscript(
            clean_transcript=" ".join(segment.text for segment in cleaned_segments).strip(),
            uncertain_segments=uncertain,
        )

    def _clean_text(self, text: str) -> str:
        stripped = " ".join(text.split())
        stripped = FILLER_REPETITIONS.sub(lambda match: match.group(1), stripped)
        if stripped and stripped[-1] not in ".?!":
            stripped += "."
        return stripped
