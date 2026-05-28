from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .app_paths import app_logs_dir


@dataclass(slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    log_path: Path


class LocalProcessRunner:
    def __init__(self, log_dir: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir) if log_dir else app_logs_dir()

    def run(
        self,
        command: list[str] | str,
        *,
        name: str,
        cwd: str | Path | None = None,
        timeout: int | float | None = None,
        shell: bool = False,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        started = datetime.now().isoformat(timespec="seconds")
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=shell,
                env=env,
                check=False,
            )
            return self._write_result(name, command, cwd, started, completed.returncode, completed.stdout, completed.stderr)
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_timeout_output(exc.stdout)
            stderr = _decode_timeout_output(exc.stderr) or f"Process timed out after {timeout} seconds."
            return self._write_result(name, command, cwd, started, -9, stdout, stderr)

    def log_path(self, name: str) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in name)
        return self.log_dir / f"{stamp}-{safe}.log"

    def _write_result(
        self,
        name: str,
        command: list[str] | str,
        cwd: str | Path | None,
        started: str,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> ProcessResult:
        path = self.log_path(name)
        lines = [
            f"name: {name}",
            f"started: {started}",
            f"cwd: {cwd or ''}",
            f"returncode: {returncode}",
            f"command: {command}",
            "",
            "[stdout]",
            stdout,
            "",
            "[stderr]",
            stderr,
        ]
        path.write_text("\n".join(lines), encoding="utf-8", errors="replace")
        return ProcessResult(returncode=returncode, stdout=stdout, stderr=stderr, log_path=path)


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        process.kill()


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
