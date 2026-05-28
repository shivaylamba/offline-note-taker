from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audio import AudioManager
from .diagnostics import DiagnosticsLogger
from .exporters import ExportAgent
from .pipeline import MeetingPipeline, PipelineSettings
from .runtime_doctor import run_runtime_doctor
from .summarization import FallbackMeetingNotesRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Note Taker")
    parser.add_argument("--cli-smoke", action="store_true", help="Run a local non-GUI smoke test.")
    parser.add_argument("--audio-file", help="Process a local audio file without launching the GUI.")
    parser.add_argument("--export-dir", default="exports", help="Directory for CLI exports.")
    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Check local Qualcomm runtime configuration.")
    doctor_parser.add_argument("--no-npu-detect", action="store_true", help="Skip Windows NPU device query.")

    smoke_parser = subparsers.add_parser("smoke", help="Run a local non-GUI smoke test.")
    smoke_parser.add_argument("--export-dir", default="exports", help="Directory for exported outputs.")

    process_parser = subparsers.add_parser("process", help="Process a local audio file without launching the GUI.")
    process_parser.add_argument("--audio", required=True, help="Audio file to process.")
    process_parser.add_argument("--export-dir", default="exports", help="Directory for exported outputs.")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor(no_npu_detect=args.no_npu_detect)
    if args.command == "smoke":
        return cli_smoke(args.export_dir)
    if args.command == "process":
        return process_audio_file(args.audio, args.export_dir)
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


def doctor(no_npu_detect: bool = False) -> int:
    report = run_runtime_doctor(detect_npu=not no_npu_detect)
    print(report.to_text())
    return 0 if report.ok else 1


def cli_smoke(export_dir: str) -> int:
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio, PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    log_path = DiagnosticsLogger().write(session, exported)
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    print(f"diagnostics: {log_path}")
    return 0


def process_audio_file(audio_file: str, export_dir: str) -> int:
    session = MeetingPipeline().process_file(Path(audio_file), PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    log_path = DiagnosticsLogger().write(session, exported)
    print(session.notes.to_markdown())
    print("Exports:")
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    print(f"diagnostics: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
