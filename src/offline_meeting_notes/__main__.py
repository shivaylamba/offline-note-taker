from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audio import AudioManager
from .diagnostics import DiagnosticsLogger
from .evaluation import run_eval
from .exporters import ExportAgent
from .packaging import create_portable_package
from .pipeline import MeetingPipeline, PipelineSettings
from .runtime_doctor import run_runtime_doctor
from .session_store import SessionStore
from .settings import AppSettings, save_detected_settings
from .summarization import FallbackMeetingNotesRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Note Taker")
    parser.add_argument("--cli-smoke", action="store_true", help="Run a local non-GUI smoke test.")
    parser.add_argument("--audio-file", help="Process a local audio file without launching the GUI.")
    parser.add_argument("--export-dir", default="exports", help="Directory for CLI exports.")
    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Check local Qualcomm runtime configuration.")
    doctor_parser.add_argument("--no-npu-detect", action="store_true", help="Skip Windows NPU device query.")
    doctor_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    smoke_parser = subparsers.add_parser("smoke", help="Run a local non-GUI smoke test.")
    smoke_parser.add_argument("--export-dir", default="exports", help="Directory for exported outputs.")

    setup_parser = subparsers.add_parser("setup", help="Save detected or provided local runtime settings.")
    setup_parser.add_argument("--whisper-app-dir", default="")
    setup_parser.add_argument("--whisper-python", default="")
    setup_parser.add_argument("--whisper-encoder", default="")
    setup_parser.add_argument("--whisper-decoder", default="")
    setup_parser.add_argument("--qairt-home", default="")
    setup_parser.add_argument("--qwen3-genie-config", default="")
    setup_parser.add_argument("--adsp-library-path", default="")

    process_parser = subparsers.add_parser("process", help="Process a local audio file without launching the GUI.")
    process_parser.add_argument("--audio", required=True, help="Audio file to process.")
    process_parser.add_argument("--export-dir", default="exports", help="Directory for exported outputs.")
    process_parser.add_argument("--session", default="", help="Optional session id or directory to save the run.")

    package_parser = subparsers.add_parser("package", help="Create a portable beta zip without Qualcomm assets.")
    package_parser.add_argument("--output", default="dist", help="Output directory for the portable zip.")

    eval_parser = subparsers.add_parser("eval", help="Run local quality evals over golden transcript fixtures.")
    eval_parser.add_argument("--fixtures", default=str(Path("tests") / "fixtures" / "eval"), help="Fixture directory.")
    eval_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor(no_npu_detect=args.no_npu_detect, as_json=args.json)
    if args.command == "setup":
        return setup(args)
    if args.command == "smoke":
        return cli_smoke(args.export_dir)
    if args.command == "process":
        return process_audio_file(args.audio, args.export_dir, args.session)
    if args.command == "package":
        return package_app(args.output)
    if args.command == "eval":
        return eval_app(args.fixtures, args.json)
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


def doctor(no_npu_detect: bool = False, as_json: bool = False) -> int:
    report = run_runtime_doctor(detect_npu=not no_npu_detect)
    print(json.dumps(report.to_dict(), indent=2) if as_json else report.to_text())
    return 0 if report.ok else 1


def setup(args: argparse.Namespace) -> int:
    settings = AppSettings.load()
    settings.whisper_app_dir = args.whisper_app_dir or settings.whisper_app_dir
    settings.whisper_python_path = args.whisper_python or settings.whisper_python_path
    settings.whisper_encoder_path = args.whisper_encoder or settings.whisper_encoder_path
    settings.whisper_decoder_path = args.whisper_decoder or settings.whisper_decoder_path
    settings.qairt_home = args.qairt_home or settings.qairt_home
    settings.qwen3_genie_config = args.qwen3_genie_config or settings.qwen3_genie_config
    settings.adsp_library_path = args.adsp_library_path or settings.adsp_library_path
    settings.apply_to_environment()
    path = save_detected_settings(settings)
    print(f"Saved settings: {path}")
    return doctor(no_npu_detect=True)


def cli_smoke(export_dir: str) -> int:
    audio = AudioManager().create_sample_meeting_wav()
    session = MeetingPipeline(notes_runner=FallbackMeetingNotesRunner()).process_audio(audio, PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    log_path = DiagnosticsLogger().write(session, exported)
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    print(f"diagnostics: {log_path}")
    return 0


def process_audio_file(audio_file: str, export_dir: str, session_target: str = "") -> int:
    session = MeetingPipeline().process_file(Path(audio_file), PipelineSettings())
    exported = ExportAgent(export_dir).export_all(session)
    log_path = DiagnosticsLogger().write(session, exported)
    store = SessionStore()
    session_dir = store.resolve_session_dir(session_target) if session_target else None
    session_dir = store.save(session, session_dir, export=True)
    print(session.notes.to_markdown())
    print("Exports:")
    for kind, path in exported.items():
        print(f"{kind}: {path}")
    print(f"diagnostics: {log_path}")
    print(f"session: {session_dir}")
    return 0


def package_app(output: str) -> int:
    package_path = create_portable_package(output)
    print(f"portable_package: {package_path}")
    return 0


def eval_app(fixtures: str, as_json: bool = False) -> int:
    report = run_eval(fixtures)
    print(json.dumps(report.to_dict(), indent=2) if as_json else report.to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
