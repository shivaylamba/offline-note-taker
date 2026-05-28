from offline_meeting_notes.__main__ import main


def test_smoke_subcommand_exports_files(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    export_dir = tmp_path / "exports"

    result = main(["smoke", "--export-dir", str(export_dir)])

    assert result == 0
    assert (export_dir / "meeting_notes.md").exists()
    assert (export_dir / "meeting_summary.json").exists()
    assert (tmp_path / "logs").exists()
