import pytest


def test_gui_has_performance_tab() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from offline_meeting_notes.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    labels = [window.details.tabText(index) for index in range(window.details.count())]

    assert "Performance" in labels
    assert window.copy_proof_button.text() == "Copy Proof"
    window.close()
    app.processEvents()
