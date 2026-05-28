from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .app_paths import settings_path


@dataclass(slots=True)
class AppSettings:
    whisper_app_dir: str = ""
    whisper_python_path: str = ""
    whisper_encoder_path: str = ""
    whisper_decoder_path: str = ""
    qairt_home: str = ""
    qwen3_genie_config: str = ""
    adsp_library_path: str = ""
    audio_input_device_id: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        target = path or settings_path()
        if not target.exists():
            return cls()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(payload, dict):
            return cls()
        known: dict[str, Any] = {field: payload.get(field, "") for field in cls.__dataclass_fields__}
        return cls(**{key: str(value or "") for key, value in known.items()})

    def save(self, path: Path | None = None) -> Path:
        target = path or settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return target

    def apply_to_environment(self) -> None:
        mappings = {
            "OFFLINE_NOTES_WHISPER_APP_DIR": self.whisper_app_dir,
            "OFFLINE_NOTES_WHISPER_PYTHON": self.whisper_python_path,
            "OFFLINE_NOTES_WHISPER_ENCODER_PATH": self.whisper_encoder_path,
            "OFFLINE_NOTES_WHISPER_DECODER_PATH": self.whisper_decoder_path,
            "QAIRT_HOME": self.qairt_home,
            "OFFLINE_NOTES_QWEN3_GENIE_CONFIG": self.qwen3_genie_config,
            "ADSP_LIBRARY_PATH": self.adsp_library_path,
        }
        for name, value in mappings.items():
            if value:
                os.environ[name] = value

    def path_or_none(self, value: str) -> Path | None:
        return Path(value).expanduser() if value.strip() else None


def load_settings() -> AppSettings:
    return AppSettings.load()


def save_detected_settings(settings: AppSettings | None = None) -> Path:
    from .aihub_runtime import qualcomm_runtime_status

    current = settings or AppSettings.load()
    status = qualcomm_runtime_status()
    current.whisper_app_dir = current.whisper_app_dir or _string_path(status.whisper_app_dir)
    current.whisper_python_path = current.whisper_python_path or _string_path(status.whisper_python_path)
    current.whisper_encoder_path = current.whisper_encoder_path or _string_path(status.whisper_encoder_path)
    current.whisper_decoder_path = current.whisper_decoder_path or _string_path(status.whisper_decoder_path)
    current.qairt_home = current.qairt_home or _string_path(status.qairt_home)
    current.qwen3_genie_config = current.qwen3_genie_config or _string_path(status.qwen3_genie_config)
    if current.qairt_home and not current.adsp_library_path:
        current.adsp_library_path = str(Path(current.qairt_home) / "lib" / "hexagon-v73" / "unsigned")
    return current.save()


def _string_path(path: Path | None) -> str:
    return str(path) if path else ""
