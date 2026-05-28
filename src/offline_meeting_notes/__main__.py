from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audio import AudioManager
from .exporters import ExportAgent
from .pipeline import MeetingPipeline, PipelineSettings
from .summarization import FallbackMeetingNotesRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Meeting Notes MVP")
    parser.add_argument("--cli-smoke", action="store_true", help="Run a local non-GUI smoke test.")
    parser.add_argument("--audio-file", help="Process a local audio file without launching the GUI.")
    parser.add_argument("--export-dir", default="exports", help="Directory for CLI exports.")
    args = parser.parse_args(argv)

    if args.cli_smoke:
        return cli_smoke(args.export_dir)
    if args.audio_file:
        return process_audio_file(args.audio_file, args.export_dir)

    try:
        from .gui import run_app
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2
    return run_app()


def cli_smoke(export_dir: str) -> int:
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio, PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    return 0


def process_audio_file(audio_file: str, export_dir: str) -> int:
    session = MeetingPipeline().process_file(Path(audio_file), PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    print(session.notes.to_markdown())
    print("Exports:")
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
