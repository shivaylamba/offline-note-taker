from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .aihub_runtime import qairt_version_is_compatible, qualcomm_runtime_status


@dataclass(slots=True)
class RuntimeCheck:
    name: str
    status: str
    message: str
    path: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeDoctorReport:
    checks: list[RuntimeCheck]

    @property
    def ok(self) -> bool:
        return not any(check.failed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checks": [check.to_dict() for check in self.checks]}

    def to_text(self) -> str:
        lines = ["Runtime Check", "=============", ""]
        for check in self.checks:
            marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[check.status]
            path = f" ({check.path})" if check.path else ""
            lines.append(f"[{marker}] {check.name}: {check.message}{path}")
        lines.append("")
        lines.append("Result: ready" if self.ok else "Result: missing required runtime pieces")
        return "\n".join(lines)


class RuntimeDoctor:
    REQUIRED_QWEN_FILES = (
        "genie_config.json",
        "tokenizer.json",
        "qwen3_4b_w4a16_part_1_of_4.bin",
        "qwen3_4b_w4a16_part_2_of_4.bin",
        "qwen3_4b_w4a16_part_3_of_4.bin",
        "qwen3_4b_w4a16_part_4_of_4.bin",
    )

    def run(self, detect_npu: bool = True) -> RuntimeDoctorReport:
        status = qualcomm_runtime_status()
        checks = [
            self._path_check("Whisper Windows app", status.whisper_app_dir, "Found Whisper Windows app.", True),
            self._path_check("Whisper demo.py", status.whisper_demo_py, "Found Whisper demo entrypoint.", True),
            self._path_check("Whisper Python", status.whisper_python_path, "Found Whisper Python environment.", True),
            self._path_check("Whisper encoder ONNX", status.whisper_encoder_path, "Found Whisper encoder model.", True),
            self._path_check("Whisper decoder ONNX", status.whisper_decoder_path, "Found Whisper decoder model.", True),
            self._qairt_check(status.qairt_home),
            self._path_check("genie-t2t-run.exe", status.genie_t2t_run, "Found Genie text runner.", True),
            self._path_check("Qwen3 Genie config", status.qwen3_genie_config, "Found Qwen3 Genie config.", True),
        ]
        checks.extend(self._qwen_bundle_checks(status.qwen3_genie_config))
        checks.append(self._adsp_check(status.qairt_home))
        if detect_npu:
            checks.append(self._npu_check())
        return RuntimeDoctorReport(checks=checks)

    def _path_check(
        self,
        name: str,
        path: Path | None,
        ok_message: str,
        required: bool,
    ) -> RuntimeCheck:
        if path and path.exists():
            return RuntimeCheck(name=name, status="pass", message=ok_message, path=str(path))
        status = "fail" if required else "warn"
        return RuntimeCheck(name=name, status=status, message="Missing or not detected.")

    def _qairt_check(self, qairt_home: Path | None) -> RuntimeCheck:
        if not qairt_home or not qairt_home.exists():
            return RuntimeCheck("QAIRT 2.45.x", "fail", "QAIRT_HOME is missing or invalid.")
        if not qairt_version_is_compatible(qairt_home):
            return RuntimeCheck("QAIRT 2.45.x", "fail", "QAIRT version is not compatible.", str(qairt_home))
        return RuntimeCheck("QAIRT 2.45.x", "pass", "Found compatible QAIRT install.", str(qairt_home))

    def _qwen_bundle_checks(self, genie_config: Path | None) -> list[RuntimeCheck]:
        if not genie_config or not genie_config.exists():
            return [
                RuntimeCheck(
                    "Qwen3 bundle files",
                    "fail",
                    "Cannot validate bundle files because genie_config.json is missing.",
                )
            ]
        bundle_dir = genie_config.parent
        checks = []
        for filename in self.REQUIRED_QWEN_FILES:
            path = bundle_dir / filename
            checks.append(
                self._path_check(
                    f"Qwen3 bundle: {filename}",
                    path,
                    "Found.",
                    required=True,
                )
            )
        return checks

    def _adsp_check(self, qairt_home: Path | None) -> RuntimeCheck:
        configured = os.environ.get("ADSP_LIBRARY_PATH", "").strip()
        expected = qairt_home / "lib" / "hexagon-v73" / "unsigned" if qairt_home else None
        if configured and Path(configured).exists():
            return RuntimeCheck("ADSP_LIBRARY_PATH", "pass", "Environment variable points to an existing folder.", configured)
        if expected and expected.exists():
            return RuntimeCheck(
                "ADSP_LIBRARY_PATH",
                "warn",
                "Not set in the shell, but the expected QAIRT folder exists and the app sets it for Genie runs.",
                str(expected),
            )
        return RuntimeCheck("ADSP_LIBRARY_PATH", "fail", "Missing ADSP library path for Hexagon runtime.")

    def _npu_check(self) -> RuntimeCheck:
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-CimInstance Win32_PnPEntity | "
                        "Where-Object { $_.Name -match 'Hexagon.*NPU|NPU|Neural Processing' "
                        "-and $_.Name -notmatch 'Camera|Sensor|Spectra|Audio|CPU|GPU|Temperature|WLAN|Bluetooth|USB|I2C|Bus|Input' } | "
                        "Select-Object -First 1 -ExpandProperty Name"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return RuntimeCheck("NPU device", "warn", "Could not query Windows device list.")
        device = completed.stdout.strip()
        if device:
            return RuntimeCheck("NPU device", "pass", f"Detected {device}.")
        return RuntimeCheck("NPU device", "warn", "No NPU-like device name was detected through Windows device query.")


def run_runtime_doctor(detect_npu: bool = True) -> RuntimeDoctorReport:
    return RuntimeDoctor().run(detect_npu=detect_npu)
