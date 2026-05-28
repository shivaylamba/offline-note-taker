from __future__ import annotations

import html
import threading
import time
from pathlib import Path

from .aihub_runtime import qualcomm_runtime_status
from .audio import AudioError, AudioManager, WavRecorder
from .diagnostics import DiagnosticsLogger
from .exporters import ExportAgent
from .models import AudioMetadata, MeetingSession
from .pipeline import MeetingPipeline, PipelineSettings, PreparedTranscript
from .quality import proof_report_text
from .qa import MeetingQAAgent
from .runtime_doctor import run_runtime_doctor
from .session_store import SessionStore, SessionSummary
from .settings import AppSettings, save_detected_settings

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal
    from PySide6.QtGui import QAction, QFont
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSplitter,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTextBrowser,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised by manual launch without GUI extras.
    raise RuntimeError(
        'PySide6 is required for the desktop app. Install it with: python -m pip install -e ".[gui]"'
    ) from exc


class ProcessingWorker(QObject):
    transcript_ready = Signal(object)
    notes_started = Signal()
    notes_delta = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline: MeetingPipeline, audio: AudioMetadata) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.audio = audio
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            prepared = self.pipeline.prepare_transcript(self.audio, PipelineSettings())
            self.transcript_ready.emit(prepared)
            self.notes_started.emit()
            notes = self.pipeline.generate_notes(prepared, self.notes_delta.emit, self.cancel_event)
            session = MeetingSession(
                audio=self.audio,
                transcription=prepared.transcription,
                chunks=prepared.chunks,
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary should surface local model/config failures.
            self.failed.emit(str(exc))
        else:
            self.finished.emit(session)


class SetupDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Runtime Setup")
        self.resize(820, 620)
        self.settings = settings
        self.fields: dict[str, QLineEdit] = {}
        self.runtime_report = ""
        self._build_ui()
        self._run_check()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel("Configure local Qualcomm paths. Nothing is uploaded; these settings stay on this PC.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self._add_path(form, "Whisper app", "whisper_app_dir", self.settings.whisper_app_dir, directory=True)
        self._add_path(form, "Whisper Python", "whisper_python_path", self.settings.whisper_python_path)
        self._add_path(form, "Whisper encoder", "whisper_encoder_path", self.settings.whisper_encoder_path)
        self._add_path(form, "Whisper decoder", "whisper_decoder_path", self.settings.whisper_decoder_path)
        self._add_path(form, "QAIRT home", "qairt_home", self.settings.qairt_home, directory=True)
        self._add_path(form, "Qwen3 Genie config", "qwen3_genie_config", self.settings.qwen3_genie_config)
        self._add_path(form, "ADSP library path", "adsp_library_path", self.settings.adsp_library_path, directory=True)
        layout.addLayout(form)

        self.report = QTextBrowser()
        self.report.setMinimumHeight(210)
        layout.addWidget(self.report, stretch=1)

        actions = QHBoxLayout()
        detect = QPushButton("Auto-Detect")
        detect.clicked.connect(self._auto_detect)
        run = QPushButton("Runtime Check")
        run.clicked.connect(self._run_check)
        copy = QPushButton("Copy Runtime Report")
        copy.clicked.connect(self._copy_report)
        actions.addWidget(detect)
        actions.addWidget(run)
        actions.addWidget(copy)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_path(self, form: QFormLayout, label: str, key: str, value: str, directory: bool = False) -> None:
        row = QHBoxLayout()
        edit = QLineEdit(value)
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda _checked=False, e=edit, d=directory: self._browse(e, d))
        row.addWidget(edit, stretch=1)
        row.addWidget(browse)
        form.addRow(label, row)
        self.fields[key] = edit

    def _browse(self, edit: QLineEdit, directory: bool) -> None:
        if directory:
            selected = QFileDialog.getExistingDirectory(self, "Choose Folder", edit.text() or str(Path.home()))
        else:
            selected, _ = QFileDialog.getOpenFileName(self, "Choose File", edit.text() or str(Path.home()))
        if selected:
            edit.setText(selected)

    def _auto_detect(self) -> None:
        path = save_detected_settings(self._settings_from_fields())
        self.settings = AppSettings.load(path)
        for key, field in self.fields.items():
            field.setText(getattr(self.settings, key))
        self._run_check()

    def _run_check(self) -> None:
        settings = self._settings_from_fields()
        settings.apply_to_environment()
        report = run_runtime_doctor()
        self.runtime_report = report.to_text()
        self.report.setPlainText(self.runtime_report)

    def _copy_report(self) -> None:
        QApplication.clipboard().setText(self.runtime_report or self.report.toPlainText())

    def _settings_from_fields(self) -> AppSettings:
        return AppSettings(**{key: field.text().strip() for key, field in self.fields.items()})

    def accept(self) -> None:
        self.settings = self._settings_from_fields()
        self.settings.save()
        self.settings.apply_to_environment()
        super().accept()


class NotesReviewDialog(QDialog):
    def __init__(self, markdown: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Meeting Notes")
        self.resize(820, 680)
        layout = QVBoxLayout(self)
        label = QLabel("Edit the Markdown that will be used for the reviewed notes export.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = QTextEdit()
        self.editor.setPlainText(markdown)
        layout.addWidget(self.editor, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def markdown(self) -> str:
        return self.editor.toPlainText().strip() + "\n"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings.load()
        self.settings.apply_to_environment()
        self.audio_manager = AudioManager()
        self.pipeline = MeetingPipeline(audio_manager=self.audio_manager)
        self.qa_agent = MeetingQAAgent()
        self.session_store = SessionStore()
        self.diagnostics_logger = DiagnosticsLogger()
        self.recorder = WavRecorder()
        self.selected_audio: AudioMetadata | None = None
        self.session: MeetingSession | None = None
        self.current_session_dir: Path | None = None
        self.is_processing = False
        self.worker_thread: QThread | None = None
        self.worker: ProcessingWorker | None = None
        self.notes_stream_active = False
        self.cancel_requested = False
        self.recording_started_at = 0.0
        self.chat_blocks: list[str] = []
        self.reviewed_markdown = ""
        self.last_diagnostics_path: Path | None = None

        self.setWindowTitle("Offline Note Taker")
        self.resize(1220, 820)
        self._build_ui()
        self._refresh_devices()
        self._refresh_history()
        self._sync_actions()
        self._set_badges("Whisper: not run", "Notes: not run", "Fallback: none")
        self._append(
            "Assistant",
            "Upload meeting audio, record a meeting, or try the sample. Everything stays local on this PC.",
        )
        self._set_status("Ready")
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self._recording_tick)
        QTimer.singleShot(300, self._maybe_show_setup)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._sidebar(), stretch=0)
        layout.addWidget(self._workspace(), stretch=1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        self.addAction(quit_action)

        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f7f7f8; color: #111827; }
            QTextBrowser, QListWidget, QLineEdit, QComboBox {
                background: #ffffff; border: 1px solid #d7dbe2; border-radius: 8px; padding: 8px;
            }
            QPushButton { background: #ffffff; border: 1px solid #cfd5df; border-radius: 7px; padding: 7px 11px; }
            QPushButton:enabled:hover { background: #eef2ff; border-color: #9aa8ff; }
            QPushButton:disabled { color: #9ca3af; background: #f1f3f5; }
            QLabel#Badge { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 10px; padding: 4px 8px; }
            QLabel#Privacy { color: #047857; }
            """
        )

    def _sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(285)
        layout = QVBoxLayout(sidebar)
        title = QLabel("Meetings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search local meetings")
        self.search_input.textChanged.connect(self._refresh_history)
        layout.addWidget(self.search_input)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._open_history_item)
        layout.addWidget(self.history_list, stretch=1)

        row = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self._new_meeting)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_current_session)
        row.addWidget(self.new_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)

        self.setup_button = QPushButton("Setup")
        self.setup_button.clicked.connect(self._open_setup)
        layout.addWidget(self.setup_button)

        privacy = QLabel("Offline by design. Audio, transcripts, notes, and logs stay local.")
        privacy.setObjectName("Privacy")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        return sidebar

    def _workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        title = QLabel("Offline Note Taker")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.status_label = QLabel("Ready")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        badge_row = QHBoxLayout()
        self.whisper_badge = self._badge("Whisper: not run")
        self.notes_badge = self._badge("Notes: not run")
        self.fallback_badge = self._badge("Fallback: none")
        self.offline_badge = self._badge("Offline: network not required")
        for badge in (self.whisper_badge, self.notes_badge, self.fallback_badge, self.offline_badge):
            badge_row.addWidget(badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        layout.addLayout(self._action_bar())

        split = QSplitter(Qt.Orientation.Horizontal)
        self.chat = QTextBrowser()
        self.chat.setOpenLinks(False)
        self.chat.anchorClicked.connect(self._anchor_clicked)
        split.addWidget(self.chat)

        self.details = QTabWidget()
        self.transcript_text = self._browser("Transcript will appear after Whisper finishes.")
        self.notes_text = self._browser("Structured meeting notes will appear after local LLM extraction.")
        self.runtime_text = self._browser(qualcomm_runtime_status().message())
        self.exports_text = self._browser("Exports and diagnostics will appear here.")
        self.performance_text = self._browser("Performance and grounding proof will appear after a run.")
        self.details.addTab(self.transcript_text, "Transcript")
        self.details.addTab(self.notes_text, "Notes")
        self.details.addTab(self.performance_text, "Performance")
        self.details.addTab(self.runtime_text, "Runtime")
        self.details.addTab(self.exports_text, "Exports")
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, stretch=1)

        layout.addLayout(self._composer())
        return workspace

    def _badge(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Badge")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _browser(self, placeholder: str) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setOpenLinks(False)
        browser.setPlaceholderText(placeholder)
        browser.anchorClicked.connect(self._anchor_clicked)
        return browser

    def _action_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        style = self.style()
        self.record_button = QPushButton("Record")
        self.record_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.record_button.clicked.connect(self._record)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.clicked.connect(self._stop)
        self.upload_button = QPushButton("Upload")
        self.upload_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.upload_button.clicked.connect(self._upload_audio)
        self.sample_button = QPushButton("Try Sample")
        self.sample_button.clicked.connect(self._try_sample)
        self.runtime_button = QPushButton("Runtime Check")
        self.runtime_button.clicked.connect(self._runtime_check)
        self.cancel_button = QPushButton("Cancel Notes")
        self.cancel_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.cancel_button.clicked.connect(self._cancel_notes)
        self.review_button = QPushButton("Review Notes")
        self.review_button.clicked.connect(self._review_notes)
        self.copy_proof_button = QPushButton("Copy Proof")
        self.copy_proof_button.clicked.connect(self._copy_proof_report)
        self.export_button = QPushButton("Export")
        self.export_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_button.clicked.connect(self._export_all)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(210)
        self.timer_label = QLabel("00:00")
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setFixedWidth(95)

        for widget in (
            self.record_button,
            self.pause_button,
            self.stop_button,
            self.upload_button,
            self.sample_button,
            self.runtime_button,
            self.cancel_button,
            self.review_button,
            self.copy_proof_button,
            self.export_button,
            self.device_combo,
            self.timer_label,
            self.level_bar,
        ):
            row.addWidget(widget)
        row.addStretch(1)
        return row

    def _composer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Ask about this meeting")
        self.question_input.returnPressed.connect(self._ask)
        self.ask_button = QPushButton("Send")
        self.ask_button.clicked.connect(self._ask)
        row.addWidget(self.question_input, stretch=1)
        row.addWidget(self.ask_button)
        return row

    def _maybe_show_setup(self) -> None:
        if not qualcomm_runtime_status().ready:
            self._append("Assistant", "Runtime setup needs attention. Click Setup or Runtime Check to configure local paths.")

    def _open_setup(self) -> None:
        dialog = SetupDialog(AppSettings.load(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.settings
            self._runtime_check()

    def _refresh_devices(self) -> None:
        self.device_combo.clear()
        self.device_combo.addItem("Default microphone", "")
        try:
            for device in self.recorder.input_devices():
                self.device_combo.addItem(device.name, device.id)
        except AudioError:
            self.device_combo.addItem("No microphone detected", "")
        if self.settings.audio_input_device_id:
            index = self.device_combo.findData(self.settings.audio_input_device_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def _refresh_history(self, _text: str = "") -> None:
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        summaries = self.session_store.search(query) if query else self.session_store.list()
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        for summary in summaries:
            item = QListWidgetItem(f"{summary.title}\n{summary.created_at}")
            item.setData(Qt.ItemDataRole.UserRole, str(summary.path))
            self.history_list.addItem(item)

    def _open_history_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            session = self.session_store.load(Path(path))
        except Exception as exc:  # noqa: BLE001 - corrupted local session should not crash the app.
            self._show_error(f"Could not open meeting session: {exc}")
            return
        self.current_session_dir = Path(path)
        self._load_session(session)

    def _new_meeting(self) -> None:
        self.session = None
        self.current_session_dir = None
        self.selected_audio = None
        self.reviewed_markdown = ""
        self.last_diagnostics_path = None
        self.chat_blocks = []
        self.chat.clear()
        self.transcript_text.clear()
        self.notes_text.clear()
        self.performance_text.setPlainText("Performance and grounding proof will appear after a run.")
        self.exports_text.setPlainText("Exports and diagnostics will appear here.")
        self._set_badges("Whisper: not run", "Notes: not run", "Fallback: none")
        self._append("Assistant", "Ready for a new local meeting. Record, upload, or try the sample.")
        self._sync_actions()

    def _delete_current_session(self) -> None:
        if not self.current_session_dir:
            return
        if QMessageBox.question(self, "Delete Meeting", "Delete this local meeting session?") == QMessageBox.StandardButton.Yes:
            self.session_store.delete(self.current_session_dir)
            self._new_meeting()
            self._refresh_history()

    def _record(self) -> None:
        try:
            device_id = str(self.device_combo.currentData() or "")
            self.settings.audio_input_device_id = device_id
            self.settings.save()
            target = self.recorder.start(device_id=device_id)
        except AudioError as exc:
            self._append("Assistant", str(exc))
            self._show_error(str(exc))
            return
        self.recording_started_at = time.monotonic()
        self.record_timer.start(200)
        self._append("You", "Record meeting")
        self._append("Assistant", "Recording. Speak naturally, then click Stop when finished.")
        self.status_label.setText(f"Recording to {target}")
        self._sync_actions()

    def _toggle_pause(self) -> None:
        try:
            if self.recorder.is_paused:
                self.recorder.resume()
                self.pause_button.setText("Pause")
                self._append("Assistant", "Recording resumed.")
            else:
                self.recorder.pause()
                self.pause_button.setText("Resume")
                self._append("Assistant", "Recording paused.")
        except AudioError as exc:
            self._show_error(str(exc))
        self._sync_actions()

    def _stop(self) -> None:
        try:
            audio = self.recorder.stop()
        except AudioError as exc:
            self._append("Assistant", str(exc))
            self._show_error(str(exc))
            return
        self.record_timer.stop()
        self.timer_label.setText("00:00")
        self.level_bar.setValue(0)
        self.pause_button.setText("Pause")
        self._append("You", "Stop recording")
        self._process_audio(audio)

    def _recording_tick(self) -> None:
        elapsed = int(time.monotonic() - self.recording_started_at)
        self.timer_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        self.level_bar.setValue(self.recorder.level)

    def _upload_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload Audio",
            str(Path.home()),
            "Audio Files (*.wav *.mp3 *.m4a *.flac)",
        )
        if not path:
            return
        try:
            audio = self.audio_manager.import_audio(path)
        except AudioError as exc:
            self._append("Assistant", str(exc))
            self._show_error(str(exc))
            return
        self._append("You", f"Upload audio: {audio.path.name}")
        self._process_audio(audio)

    def _try_sample(self) -> None:
        audio = self.audio_manager.create_sample_meeting_wav()
        self._append("You", "Try sample meeting")
        self._process_audio(audio)

    def _process_audio(self, audio: AudioMetadata) -> None:
        if self.is_processing:
            self._append("Assistant", "The local AI pipeline is already processing audio.")
            return
        self.selected_audio = audio
        self.session = None
        self.current_session_dir = None
        self.is_processing = True
        self.cancel_requested = False
        self.notes_stream_active = False
        self.transcript_text.clear()
        self.notes_text.setPlainText("Waiting for transcript...")
        self.exports_text.setPlainText("Processing locally...")
        self._set_badges("Whisper: running", "Notes: waiting", "Fallback: none")
        self.status_label.setText(f"Processing {audio.path.name}")
        self._append("Assistant", "Transcribing locally first. Notes will start after the transcript is ready.")
        self._set_status("Processing locally")
        self._sync_actions()

        thread = QThread(self)
        worker = ProcessingWorker(self.pipeline, audio)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.transcript_ready.connect(self._transcript_ready)
        worker.notes_started.connect(self._notes_started)
        worker.notes_delta.connect(self._notes_delta)
        worker.finished.connect(self._processing_finished)
        worker.failed.connect(self._processing_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._processing_thread_finished)
        self.worker_thread = thread
        self.worker = worker
        thread.start()

    def _runtime_check(self) -> None:
        report = run_runtime_doctor()
        self.runtime_text.setPlainText(report.to_text())
        self.details.setCurrentWidget(self.runtime_text)
        self._set_status("Runtime ready" if report.ok else "Runtime check found missing pieces")
        self._append("Assistant", "Runtime Check complete. Open the Runtime panel for pass/fail details.")

    def _cancel_notes(self) -> None:
        if not self.worker or not self.is_processing:
            return
        self.cancel_requested = True
        self.worker.cancel()
        self.cancel_button.setEnabled(False)
        self._append("Assistant", "Cancel requested. I will stop Genie and render transcript-grounded fallback notes.")
        self._set_status("Cancelling notes generation")

    def _transcript_ready(self, prepared: object) -> None:
        if not isinstance(prepared, PreparedTranscript):
            return
        self._set_badges(f"Whisper: {prepared.transcription.backend}", "Notes: starting", "Fallback: none")
        self.status_label.setText(
            f"Transcript ready: {self.selected_audio.path.name if self.selected_audio else 'audio'}"
        )
        self._render_transcript(prepared.transcription.segments)
        warnings = f"\n\nWarnings: {'; '.join(prepared.transcription.warnings)}" if prepared.transcription.warnings else ""
        self._append(
            "Assistant",
            "Transcript ready. I am generating structured meeting notes now.\n\n"
            f"{prepared.transcription.full_transcript}{warnings}",
        )

    def _notes_started(self) -> None:
        self.notes_stream_active = True
        self.notes_badge.setText("Notes: Qwen3 Genie running")
        self.notes_text.setPlainText("Extracting structured notes with the local LLM.")
        self.details.setCurrentWidget(self.notes_text)
        self._append("Assistant", "Local LLM started. I will validate the output before showing final notes.")
        self._sync_actions()

    def _notes_delta(self, text: str) -> None:
        if not text:
            return
        if not self.notes_stream_active:
            self._notes_started()
        self._append("Assistant", text)
        current = self.notes_text.toPlainText().strip()
        self.notes_text.setPlainText(f"{current}\n\n{text}".strip())

    def _processing_finished(self, session: object) -> None:
        self.is_processing = False
        if isinstance(session, MeetingSession):
            self.session = session
            self.current_session_dir = self.session_store.save(session)
            self.reviewed_markdown = ""
            log_path = self.diagnostics_logger.write(session)
            self.last_diagnostics_path = log_path
            self._set_badges(
                f"Whisper: {session.transcription.backend}",
                f"Notes: {session.notes.backend}",
                f"Fallback: {session.notes.fallback_reason}" if session.notes.fallback_reason else "Fallback: none",
            )
            self.status_label.setText(f"Ready: {session.audio.path.name}")
            self._render_transcript(session.transcription.segments)
            self._render_notes(session)
            self._render_performance(session, log_path)
            self.exports_text.setPlainText(f"Session: {self.current_session_dir}\nDiagnostics: {log_path}")
            self._append("Assistant", "Structured notes are ready. You can ask questions, review evidence, or export.")
            self._refresh_history()
        else:
            self._processing_failed("Unexpected local pipeline result.")
        self._sync_actions()

    def _processing_failed(self, message: str) -> None:
        self.is_processing = False
        self.notes_stream_active = False
        self._set_badges(self.whisper_badge.text(), "Notes: failed", "Fallback: none")
        self.notes_text.setPlainText(message)
        self._append("Assistant", f"I could not finish the local AI pipeline.\n\n{message}")
        self._set_status("Processing failed")
        self._sync_actions()

    def _processing_thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None
        self._sync_actions()

    def _load_session(self, session: MeetingSession) -> None:
        self.session = session
        self.selected_audio = session.audio
        reviewed = self.current_session_dir / "reviewed_meeting_notes.md" if self.current_session_dir else None
        self.reviewed_markdown = reviewed.read_text(encoding="utf-8") if reviewed and reviewed.exists() else ""
        diagnostics = self.current_session_dir / "diagnostics.json" if self.current_session_dir else None
        self.last_diagnostics_path = diagnostics if diagnostics and diagnostics.exists() else None
        self._set_badges(
            f"Whisper: {session.transcription.backend}",
            f"Notes: {session.notes.backend}",
            f"Fallback: {session.notes.fallback_reason}" if session.notes.fallback_reason else "Fallback: none",
        )
        self.status_label.setText(f"Opened local session: {session.audio.path.name}")
        self._render_transcript(session.transcription.segments)
        self._render_notes(session)
        self._render_performance(session, self.last_diagnostics_path)
        self._append("Assistant", "Opened this local meeting. Ask a question or export the notes.")
        self._sync_actions()

    def _ask(self) -> None:
        question = self.question_input.text().strip()
        if not question:
            return
        self._append("You", question)
        self.question_input.clear()
        if not self.session:
            self._append("Assistant", "Generate or open meeting notes first, then I can answer from the transcript.")
            return
        answer = self.qa_agent.answer(question, self.session.transcription.segments, self.session.notes)
        self._append("Assistant", answer.answer, citations=answer.citations)

    def _export_all(self) -> None:
        if not self.session:
            self._append("Assistant", "Generate or open notes before exporting.")
            return
        target = QFileDialog.getExistingDirectory(self, "Choose Export Folder", str(Path.cwd() / "exports"))
        if not target:
            return
        exported = ExportAgent(target).export_all(self.session)
        if self.reviewed_markdown:
            exported["markdown"].write_text(self.reviewed_markdown, encoding="utf-8")
        if self.current_session_dir:
            self.session_store.save(self.session, self.current_session_dir, export=True)
            if self.reviewed_markdown:
                reviewed_path = self.current_session_dir / "reviewed_meeting_notes.md"
                reviewed_path.write_text(self.reviewed_markdown, encoding="utf-8")
                ExportAgent(self.current_session_dir / "exports").export_markdown(self.session).write_text(
                    self.reviewed_markdown,
                    encoding="utf-8",
                )
        log_path = self.diagnostics_logger.write(self.session, exported)
        self.last_diagnostics_path = log_path
        lines = "\n".join(f"- {kind}: {path}" for kind, path in exported.items())
        self.exports_text.setPlainText(f"Exported files:\n{lines}\n- diagnostics: {log_path}")
        self._render_performance(self.session, log_path)
        self.details.setCurrentWidget(self.exports_text)
        self._append("Assistant", f"Exported files:\n{lines}")
        self._set_status(f"Exported to {target}")

    def _review_notes(self) -> None:
        if not self.session:
            return
        dialog = NotesReviewDialog(self.reviewed_markdown or self.session.notes.to_markdown(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reviewed_markdown = dialog.markdown()
            self.notes_text.setMarkdown(self.reviewed_markdown)
            if self.current_session_dir:
                (self.current_session_dir / "reviewed_meeting_notes.md").write_text(
                    self.reviewed_markdown,
                    encoding="utf-8",
                )
            self._append("Assistant", "Reviewed notes saved locally. Export will use the reviewed Markdown.")

    def _render_transcript(self, segments) -> None:  # type: ignore[no-untyped-def]
        rows = []
        for segment in segments:
            stamp = f"{segment.start}-{segment.end}"
            rows.append(
                f'<p><a href="cite:{html.escape(stamp)}">{html.escape(stamp)}</a><br>{html.escape(segment.text)}</p>'
            )
        self.transcript_text.setHtml("".join(rows) or "<p>No transcript.</p>")

    def _render_notes(self, session: MeetingSession) -> None:
        self.notes_text.setMarkdown(session.notes.to_markdown())
        self.details.setCurrentWidget(self.notes_text)

    def _render_performance(self, session: MeetingSession, diagnostics_path: Path | None = None) -> None:
        report = proof_report_text(
            session,
            diagnostics_path=diagnostics_path or "",
            session_path=self.current_session_dir or "",
            detect_npu=True,
        )
        self.performance_text.setPlainText(report)

    def _copy_proof_report(self) -> None:
        if not self.session:
            return
        report = proof_report_text(
            self.session,
            diagnostics_path=self.last_diagnostics_path or "",
            session_path=self.current_session_dir or "",
            detect_npu=True,
        )
        QApplication.clipboard().setText(report)
        self._append("Assistant", "Copied the local proof report to the clipboard.")

    def _anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() != "cite" or not self.session:
            return
        stamp = url.path()
        matching = [
            segment
            for segment in self.session.transcription.segments
            if f"{segment.start}-{segment.end}" == stamp
        ]
        if matching:
            segment = matching[0]
            self.details.setCurrentWidget(self.transcript_text)
            self._set_status(f"Citation {stamp}: {segment.text}")

    def _append(self, speaker: str, message: str, citations: list[str] | None = None) -> None:
        safe_message = html.escape(message.strip()).replace("\n", "<br>")
        citation_html = ""
        if citations:
            links = [
                f'<a href="cite:{html.escape(citation)}">{html.escape(citation)}</a>'
                for citation in citations
            ]
            citation_html = "<div class='citations'>Citations: " + ", ".join(links) + "</div>"
        role = "assistant" if speaker.lower() == "assistant" else "user"
        block = (
            f"<div style='margin:10px 0;'>"
            f"<b>{html.escape(speaker)}</b>"
            f"<div style='background:{'#ffffff' if role == 'assistant' else '#e8f0ff'}; "
            f"border:1px solid #d7dbe2; border-radius:10px; padding:10px; margin-top:4px;'>"
            f"{safe_message}{citation_html}</div></div>"
        )
        self.chat_blocks.append(block)
        self.chat.setHtml("".join(self.chat_blocks))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _set_badges(self, whisper: str, notes: str, fallback: str) -> None:
        self.whisper_badge.setText(whisper)
        self.notes_badge.setText(notes)
        self.fallback_badge.setText(fallback)

    def _sync_actions(self) -> None:
        is_recording = self.recorder.is_recording
        has_session = self.session is not None
        is_busy = self.is_processing
        self.record_button.setEnabled(not is_recording and not is_busy)
        self.pause_button.setEnabled(is_recording and not is_busy)
        self.upload_button.setEnabled(not is_recording and not is_busy)
        self.sample_button.setEnabled(not is_recording and not is_busy)
        self.runtime_button.setEnabled(not is_busy)
        self.setup_button.setEnabled(not is_busy)
        self.stop_button.setEnabled(is_recording and not is_busy)
        self.cancel_button.setEnabled(is_busy and self.notes_stream_active and not self.cancel_requested)
        self.export_button.setEnabled(has_session and not is_busy)
        self.review_button.setEnabled(has_session and not is_busy)
        self.copy_proof_button.setEnabled(has_session and not is_busy)
        self.question_input.setEnabled(has_session and not is_busy)
        self.ask_button.setEnabled(has_session and not is_busy)
        self.delete_button.setEnabled(self.current_session_dir is not None and not is_busy)

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Offline Note Taker", message)
        self._set_status(message)


def run_app() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
