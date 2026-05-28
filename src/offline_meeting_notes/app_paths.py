from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "OfflineNoteTaker"


def app_data_dir() -> Path:
    configured = os.environ.get("OFFLINE_NOTES_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def sessions_dir() -> Path:
    return app_data_dir() / "sessions"


def app_logs_dir() -> Path:
    return app_data_dir() / "logs"
