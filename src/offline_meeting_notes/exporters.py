from __future__ import annotations

import json
from pathlib import Path

from .models import MeetingSession, TranscriptSegment


class ExportAgent:
    def __init__(self, output_dir: str | Path = "exports") -> None:
        self.output_dir = Path(output_dir)

    def export_all(self, session: MeetingSession) -> dict[str, Path]:
        return {
            "markdown": self.export_markdown(session),
            "txt": self.export_txt(session),
            "json": self.export_json(session),
            "srt": self.export_srt(session.transcription.segments),
            "vtt": self.export_vtt(session.transcription.segments),
        }

    def export_markdown(self, session: MeetingSession, filename: str = "meeting_notes.md") -> Path:
        path = self._path(filename)
        path.write_text(session.notes.to_markdown(), encoding="utf-8")
        return path

    def export_txt(self, session: MeetingSession, filename: str = "meeting_transcript.txt") -> Path:
        path = self._path(filename)
        content = [
            "Transcript",
            "==========",
            session.transcription.full_transcript,
            "",
            "Meeting Notes",
            "=============",
            session.notes.to_markdown(),
        ]
        path.write_text("\n".join(content), encoding="utf-8")
        return path

    def export_json(self, session: MeetingSession, filename: str = "meeting_summary.json") -> Path:
        path = self._path(filename)
        path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
        return path

    def export_srt(self, segments: list[TranscriptSegment], filename: str = "meeting_transcript.srt") -> Path:
        path = self._path(filename)
        text = "\n".join(segment.to_srt_block(index) for index, segment in enumerate(segments, start=1))
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path

    def export_vtt(self, segments: list[TranscriptSegment], filename: str = "meeting_transcript.vtt") -> Path:
        path = self._path(filename)
        body = "\n".join(segment.to_vtt_block() for segment in segments)
        path.write_text("WEBVTT\n\n" + body.strip() + "\n", encoding="utf-8")
        return path

    def _path(self, filename: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir / filename
