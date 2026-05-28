from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from .audio import AudioManager


EXCLUDED_ROOTS = {".git", "external", "models", "exports", "logs", "recordings", "dist", "build", ".venv"}
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
INCLUDED_ROOTS = {"AGENTS.md", "README.md", "pyproject.toml", ".gitignore", "docs", "scripts", "src", "tests"}


def create_portable_package(output_dir: str | Path = "dist", repo_root: str | Path | None = None) -> Path:
    root = Path(repo_root or Path.cwd()).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / f"offline-note-taker-beta-{datetime.now().strftime('%Y%m%dT%H%M%S')}.zip"

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_package_files(root):
            archive.write(path, path.relative_to(root).as_posix())
        sample = AudioManager().create_sample_meeting_wav()
        archive.write(sample.path, "sample_data/sample_meeting.wav")
        sidecar = sample.path.with_suffix(".txt")
        if sidecar.exists():
            archive.write(sidecar, "sample_data/sample_meeting.txt")
        archive.writestr(
            "RUN_ME_FIRST.txt",
            "\n".join(
                [
                    "Offline Note Taker portable beta",
                    "",
                    "1. Install Python 3.12.",
                    "2. From this folder, run: python -m pip install -e \".[gui,dev]\"",
                    "3. Run: python -m offline_meeting_notes doctor",
                    "4. Run: python -m offline_meeting_notes",
                    "",
                    "Qualcomm SDK/model assets are intentionally not bundled.",
                ]
            ),
        )
    return package_path


def _iter_package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for child in root.iterdir():
        if child.name in EXCLUDED_ROOTS:
            continue
        if child.name not in INCLUDED_ROOTS:
            continue
        if child.is_file():
            files.append(child)
            continue
        for path in child.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if relative.parts[0] in EXCLUDED_ROOTS:
                continue
            files.append(path)
    return sorted(files)
