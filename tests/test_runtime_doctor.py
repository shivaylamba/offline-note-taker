from types import SimpleNamespace

from offline_meeting_notes.runtime_doctor import RuntimeDoctor


def test_runtime_doctor_reports_missing_required_assets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "offline_meeting_notes.runtime_doctor.qualcomm_runtime_status",
        lambda: SimpleNamespace(
            whisper_app_dir=None,
            whisper_demo_py=None,
            whisper_python_path=None,
            whisper_encoder_path=None,
            whisper_decoder_path=None,
            qairt_home=None,
            genie_t2t_run=None,
            qwen3_genie_config=None,
        ),
    )

    report = RuntimeDoctor().run(detect_npu=False)

    assert not report.ok
    assert "Whisper Windows app" in report.to_text()
    assert "Qwen3 Genie config" in report.to_text()


def test_runtime_doctor_passes_with_fake_runtime_tree(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    whisper_app = tmp_path / "whisper_windows_py"
    whisper_app.mkdir()
    whisper_demo = whisper_app / "demo.py"
    whisper_demo.write_text("print('demo')", encoding="utf-8")
    whisper_python = tmp_path / "python.exe"
    whisper_python.write_text("", encoding="utf-8")
    encoder = tmp_path / "HfWhisperEncoder.onnx"
    decoder = tmp_path / "HfWhisperDecoder.onnx"
    encoder.write_text("", encoding="utf-8")
    decoder.write_text("", encoding="utf-8")

    qairt_home = tmp_path / "QAIRT" / "2.45.0"
    genie = qairt_home / "bin" / "aarch64-windows-msvc" / "genie-t2t-run.exe"
    adsp = qairt_home / "lib" / "hexagon-v73" / "unsigned"
    genie.parent.mkdir(parents=True)
    adsp.mkdir(parents=True)
    genie.write_text("", encoding="utf-8")

    bundle = tmp_path / "qwen_bundle"
    bundle.mkdir()
    for filename in RuntimeDoctor.REQUIRED_QWEN_FILES:
        (bundle / filename).write_text("{}", encoding="utf-8")
    qwen_config = bundle / "genie_config.json"

    monkeypatch.setattr(
        "offline_meeting_notes.runtime_doctor.qualcomm_runtime_status",
        lambda: SimpleNamespace(
            whisper_app_dir=whisper_app,
            whisper_demo_py=whisper_demo,
            whisper_python_path=whisper_python,
            whisper_encoder_path=encoder,
            whisper_decoder_path=decoder,
            qairt_home=qairt_home,
            genie_t2t_run=genie,
            qwen3_genie_config=qwen_config,
        ),
    )
    monkeypatch.delenv("ADSP_LIBRARY_PATH", raising=False)

    report = RuntimeDoctor().run(detect_npu=False)

    assert report.ok
    assert "[PASS] QAIRT 2.45.x" in report.to_text()
    assert "[WARN] ADSP_LIBRARY_PATH" in report.to_text()
