import zipfile

from offline_meeting_notes.packaging import create_portable_package


def test_portable_package_excludes_large_runtime_dirs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("readme", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    for excluded in ("external", "models", "logs", "recordings", "exports"):
        folder = root / excluded
        folder.mkdir()
        (folder / "asset.bin").write_text("do not include", encoding="utf-8")

    package = create_portable_package(tmp_path / "dist", root)

    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()

    assert "README.md" in names
    assert "sample_data/sample_meeting.wav" in names
    assert not any(name.startswith(("external/", "models/", "logs/", "recordings/", "exports/")) for name in names)
