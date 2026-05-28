from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .settings import load_settings


DEFAULT_QAIRT_HOME = Path(r"C:\Qualcomm\AIStack\QAIRT\2.45.0.260326")
FALLBACK_QAIRT_HOME = Path(r"C:\Users\Admin\Downloads\v2.41.0.251128\qairt\2.41.0.251128")


@dataclass(slots=True)
class QualcommRuntimeStatus:
    whisper_app_dir: Path | None
    whisper_demo_py: Path | None
    whisper_python_path: Path | None
    whisper_encoder_path: Path | None
    whisper_decoder_path: Path | None
    qwen3_genie_config: Path | None
    qairt_home: Path | None
    genie_t2t_run: Path | None
    missing: list[str]

    @property
    def ready(self) -> bool:
        return not self.missing

    def message(self) -> str:
        if self.ready:
            return "Qualcomm AI Hub runtime is configured."
        return "Qualcomm AI Hub runtime is not fully configured:\n- " + "\n- ".join(self.missing)


def find_whisper_app_dir() -> Path | None:
    settings = load_settings()
    configured = os.environ.get("OFFLINE_NOTES_WHISPER_APP_DIR", "").strip() or settings.whisper_app_dir.strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path.cwd() / "external" / "ai-hub-apps" / "apps" / "whisper_windows_py",
            Path.home() / "Documents" / "ai-hub-apps" / "apps" / "whisper_windows_py",
            Path.home() / "Desktop" / "ai-hub-apps" / "apps" / "whisper_windows_py",
        ]
    )
    for candidate in candidates:
        if (candidate / "demo.py").exists():
            return candidate
    return None


def find_whisper_model_paths(app_dir: Path | None = None) -> tuple[Path | None, Path | None]:
    settings = load_settings()
    encoder_configured = os.environ.get("OFFLINE_NOTES_WHISPER_ENCODER_PATH", "").strip() or settings.whisper_encoder_path.strip()
    decoder_configured = os.environ.get("OFFLINE_NOTES_WHISPER_DECODER_PATH", "").strip() or settings.whisper_decoder_path.strip()
    if encoder_configured and decoder_configured:
        encoder = Path(encoder_configured)
        decoder = Path(decoder_configured)
        if encoder.exists() and decoder.exists():
            return encoder, decoder

    candidates: list[tuple[Path, Path]] = []
    if app_dir:
        candidates.extend(
            [
                (
                    app_dir
                    / "export_assets"
                    / "whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite"
                    / "HfWhisperEncoder.onnx",
                    app_dir
                    / "export_assets"
                    / "whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite"
                    / "HfWhisperDecoder.onnx",
                ),
                (
                    app_dir
                    / "build"
                    / "whisper_base_float"
                    / "precompiled"
                    / "qualcomm-snapdragon-x-elite"
                    / "HfWhisperEncoder"
                    / "model.onnx",
                    app_dir
                    / "build"
                    / "whisper_base_float"
                    / "precompiled"
                    / "qualcomm-snapdragon-x-elite"
                    / "HfWhisperDecoder"
                    / "model.onnx",
                ),
                (app_dir / "models" / "HfWhisperEncoder.onnx", app_dir / "models" / "HfWhisperDecoder.onnx"),
                (app_dir / "models" / "encoder.onnx", app_dir / "models" / "decoder.onnx"),
            ]
        )
    candidates.append(
        (
            Path.cwd() / "models" / "whisper" / "encoder.onnx",
            Path.cwd() / "models" / "whisper" / "decoder.onnx",
        )
    )
    for encoder, decoder in candidates:
        if encoder.exists() and decoder.exists():
            return encoder, decoder
    return None, None


def find_whisper_python(app_dir: Path | None = None) -> Path | None:
    settings = load_settings()
    configured = os.environ.get("OFFLINE_NOTES_WHISPER_PYTHON", "").strip() or settings.whisper_python_path.strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(Path.cwd() / "external" / "aihub-whisper-venv311" / "Scripts" / "python.exe")
    if app_dir:
        try:
            external_dir = app_dir.parents[2]
            candidates.append(external_dir / "aihub-whisper-venv311" / "Scripts" / "python.exe")
        except IndexError:
            pass
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_qairt_home() -> Path | None:
    settings = load_settings()
    configured = os.environ.get("QAIRT_HOME", "").strip() or settings.qairt_home.strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path.home() / "Downloads" / "v2.45.0.260326154327" / "qairt" / "2.45.0.260326154327",
            Path(r"C:\Qualcomm\AIStack\QAIRT\2.45.0.260326"),
            DEFAULT_QAIRT_HOME,
            FALLBACK_QAIRT_HOME,
        ]
    )
    qualcomm_root = Path(r"C:\Qualcomm\AIStack\QAIRT")
    if qualcomm_root.exists():
        candidates.extend(sorted(qualcomm_root.glob("2.45*")))
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        candidates.extend(
            sorted(
                (
                    path.parent.parent.parent
                    for path in downloads.rglob("bin/aarch64-windows-msvc/genie-t2t-run.exe")
                ),
                key=lambda path: ("2.45" not in str(path), str(path)),
            )
        )
    for candidate in candidates:
        if (candidate / "bin" / "aarch64-windows-msvc" / "genie-t2t-run.exe").exists():
            return candidate
    return None


def find_qwen3_genie_config() -> Path | None:
    settings = load_settings()
    configured = os.environ.get("OFFLINE_NOTES_QWEN3_GENIE_CONFIG", "").strip() or settings.qwen3_genie_config.strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path.cwd() / "models" / "qwen3_4b" / "genie_bundle" / "genie_config.json",
            Path.cwd() / "models" / "qwen3_4b" / "genie_config.json",
            Path.home() / "Documents" / "qwen3_4b" / "genie_bundle" / "genie_config.json",
            Path.home() / "Desktop" / "qwen3_4b" / "genie_bundle" / "genie_config.json",
        ]
    )
    model_root = Path.cwd() / "models" / "qwen3_4b"
    if model_root.exists():
        candidates.extend(sorted(model_root.rglob("genie_config.json")))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def qairt_version_is_compatible(qairt_home: Path | None) -> bool:
    if not qairt_home:
        return False
    text = str(qairt_home)
    return "2.45" in text or "2.46" in text or "2.47" in text


def has_qai_hub_client_config() -> bool:
    return (Path.home() / ".qai_hub" / "client.ini").exists()


def qualcomm_runtime_status() -> QualcommRuntimeStatus:
    whisper_app_dir = find_whisper_app_dir()
    whisper_python = find_whisper_python(whisper_app_dir)
    whisper_encoder, whisper_decoder = find_whisper_model_paths(whisper_app_dir)
    qairt_home = find_qairt_home()
    qwen3_config = find_qwen3_genie_config()
    whisper_demo = whisper_app_dir / "demo.py" if whisper_app_dir else None
    genie_t2t = qairt_home / "bin" / "aarch64-windows-msvc" / "genie-t2t-run.exe" if qairt_home else None

    missing = []
    if not whisper_app_dir:
        missing.append(
            "Whisper Windows app missing. Clone Qualcomm ai-hub-apps and set "
            "OFFLINE_NOTES_WHISPER_APP_DIR to apps\\whisper_windows_py."
        )
    if not whisper_encoder or not whisper_decoder:
        missing.append(
            "Whisper-Base ONNX models missing. Run the Whisper Windows export/download step so "
            "export_assets\\whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite exists."
        )
    if not whisper_python:
        missing.append(
            "Whisper Python runtime missing. Create external\\aihub-whisper-venv311 with "
            "qai-hub-models[whisper-base] and onnxruntime-qnn, or set OFFLINE_NOTES_WHISPER_PYTHON."
        )
    if not qairt_home:
        missing.append("QAIRT_HOME missing or invalid. Install QAIRT SDK and set QAIRT_HOME.")
    elif not qairt_version_is_compatible(qairt_home):
        missing.append(
            "Qwen3-4B Snapdragon X Elite ready-made assets require QAIRT 2.45.x. "
            f"Current QAIRT_HOME is {qairt_home}."
        )
    if not qwen3_config:
        missing.append(
            "Qwen3-4B Genie bundle missing. Run scripts\\setup_qwen3_4b_genie.ps1 "
            "or set OFFLINE_NOTES_QWEN3_GENIE_CONFIG to genie_config.json."
        )

    return QualcommRuntimeStatus(
        whisper_app_dir=whisper_app_dir,
        whisper_demo_py=whisper_demo,
        whisper_python_path=whisper_python,
        whisper_encoder_path=whisper_encoder,
        whisper_decoder_path=whisper_decoder,
        qwen3_genie_config=qwen3_config,
        qairt_home=qairt_home,
        genie_t2t_run=genie_t2t,
        missing=missing,
    )
