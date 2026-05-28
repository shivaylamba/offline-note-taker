from __future__ import annotations

import threading
from pathlib import Path

from .aihub_runtime import qualcomm_runtime_status
from .audio import AudioError, AudioManager, WavRecorder
from .diagnostics import DiagnosticsLogger
from .exporters import ExportAgent
from .models import AudioMetadata, MeetingSession
from .pipeline import MeetingPipeline, PipelineSettings, PreparedTranscript
from .qa import MeetingQAAgent
from .runtime_doctor import run_runtime_doctor

try:
    from PySide6.QtCore import QObject, QThread, Qt, Signal
    from PySide6.QtGui import QAction, QFont
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QStatusBar,
        QStyle,
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.audio_manager = AudioManager()
        self.pipeline = MeetingPipeline(audio_manager=self.audio_manager)
        self.qa_agent = MeetingQAAgent()
        self.diagnostics_logger = DiagnosticsLogger()
        self.recorder = WavRecorder()
        self.selected_audio: AudioMetadata | None = None
        self.session: MeetingSession | None = None
        self.is_processing = False
        self.worker_thread: QThread | None = None
        self.worker: ProcessingWorker | None = None
        self.notes_stream_active = False
        self.notes_stream_has_text = False
        self.cancel_requested = False

        self.setWindowTitle("Offline Meeting Notes")
        self.resize(980, 760)
        self._build_ui()
        self._sync_actions()
        runtime = qualcomm_runtime_status()
        self._append(
            "Assistant",
            "This app is configured for Qualcomm AI Hub mode: Whisper Windows for transcription "
            "and Qwen3-4B via Genie for notes.\n\n"
            + runtime.message()
            + "\n\nUse Try Sample only to test the UI without the AI Hub assets.",
        )
        self._set_status("Ready")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Offline Meeting Notes")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.status_label = QLabel("No audio loaded")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        badge_row = QHBoxLayout()
        self.whisper_badge = QLabel("Whisper: not run")
        self.notes_badge = QLabel("Notes: not run")
        self.fallback_badge = QLabel("Fallback: none")
        for badge in (self.whisper_badge, self.notes_badge, self.fallback_badge):
            badge.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            badge_row.addWidget(badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        layout.addLayout(self._action_bar())

        panels = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()

        self.transcript_text = self._read_only_text("Transcript will appear here after Whisper finishes.")
        self.notes_text = self._read_only_text("Meeting notes will appear here after local LLM extraction.")
        self.runtime_text = self._read_only_text(qualcomm_runtime_status().message())
        self.runtime_text.setPlainText(qualcomm_runtime_status().message())
        self.chat = self._read_only_text("Ask questions after notes are generated.")

        left.addWidget(self._panel("Transcript", self.transcript_text), stretch=1)
        left.addWidget(self._panel("Meeting Notes", self.notes_text), stretch=2)
        right.addWidget(self._panel("Runtime Check", self.runtime_text), stretch=1)
        right.addWidget(self._panel("Q&A", self.chat), stretch=1)
        panels.addLayout(left, stretch=3)
        panels.addLayout(right, stretch=2)
        layout.addLayout(panels, stretch=1)

        layout.addLayout(self._composer())

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        self.addAction(quit_action)

    def _read_only_text(self, placeholder: str) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setPlaceholderText(placeholder)
        widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        return widget

    def _panel(self, title: str, widget: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(widget)
        return box

    def _action_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        style = self.style()

        self.record_button = QPushButton("Record")
        self.record_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.record_button.clicked.connect(self._record)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.clicked.connect(self._stop)

        self.upload_button = QPushButton("Upload Audio")
        self.upload_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.upload_button.clicked.connect(self._upload_audio)

        self.runtime_button = QPushButton("Runtime Check")
        self.runtime_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.runtime_button.clicked.connect(self._runtime_check)

        self.sample_button = QPushButton("Try Sample")
        self.sample_button.clicked.connect(self._try_sample)

        self.cancel_button = QPushButton("Cancel Notes")
        self.cancel_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.cancel_button.clicked.connect(self._cancel_notes)

        self.export_button = QPushButton("Export")
        self.export_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_button.clicked.connect(self._export_all)

        row.addWidget(self.record_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.upload_button)
        row.addWidget(self.runtime_button)
        row.addWidget(self.sample_button)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        row.addWidget(self.export_button)
        return row

    def _composer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Ask about the meeting notes")
        self.question_input.returnPressed.connect(self._ask)
        self.ask_button = QPushButton("Send")
        self.ask_button.clicked.connect(self._ask)
        row.addWidget(self.question_input, stretch=1)
        row.addWidget(self.ask_button)
        return row

    def _record(self) -> None:
        try:
            target = self.recorder.start()
        except AudioError as exc:
            self._append("Assistant", str(exc))
            self._show_error(str(exc))
            return
        self._append("You", "Record meeting")
        self._append("Assistant", "Recording. Click Stop when the meeting is finished.")
        self.status_label.setText(f"Recording to {target}")
        self._sync_actions()

    def _stop(self) -> None:
        try:
            audio = self.recorder.stop()
        except AudioError as exc:
            self._append("Assistant", str(exc))
            self._show_error(str(exc))
            return
        self._append("You", "Stop recording")
        self._process_audio(audio)

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
            self._append("Assistant", "The local AI pipeline is already processing audio. Please wait for it to finish.")
            return

        self.selected_audio = audio
        self.session = None
        self.is_processing = True
        self.cancel_requested = False
        self.notes_stream_active = False
        self.notes_stream_has_text = False
        self.transcript_text.setPlainText("")
        self.notes_text.setPlainText("Waiting for transcript...")
        self.whisper_badge.setText("Whisper: running")
        self.notes_badge.setText("Notes: waiting")
        self.fallback_badge.setText("Fallback: none")
        self.status_label.setText(f"Processing {audio.path.name}")
        self._append("Assistant", "Transcribing and generating notes locally. Qwen/QNN notes can take a few minutes.")
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
        self._set_status("Runtime ready" if report.ok else "Runtime check found missing pieces")
        self._append("Assistant", "Runtime Check complete. See the Runtime Check panel.")

    def _cancel_notes(self) -> None:
        if not self.worker or not self.is_processing:
            return
        self.cancel_requested = True
        self.worker.cancel()
        self.cancel_button.setEnabled(False)
        self._append_notes_status("Cancel requested. Waiting for Genie to stop cleanly.")
        self._set_status("Cancelling notes generation")

    def _transcript_ready(self, prepared: object) -> None:
        if not isinstance(prepared, PreparedTranscript):
            return
        self.status_label.setText(
            f"Transcript ready: {self.selected_audio.path.name if self.selected_audio else 'audio'} | "
            f"backend: {prepared.transcription.backend} | generating notes"
        )
        self.whisper_badge.setText(f"Whisper: {prepared.transcription.backend}")
        self.notes_badge.setText("Notes: starting")
        self._set_status("Transcript ready; generating notes")
        warnings = (
            f"\n\nWarnings: {'; '.join(prepared.transcription.warnings)}"
            if prepared.transcription.warnings
            else ""
        )
        self._append(
            "Assistant",
            "Transcript ready. I am generating the meeting notes now.\n\n"
            "Transcript\n"
            "----------\n"
            f"{prepared.transcription.full_transcript}"
            f"{warnings}",
        )
        self.transcript_text.setPlainText(prepared.transcription.full_transcript + warnings)

    def _notes_started(self) -> None:
        self.notes_stream_active = True
        self.notes_stream_has_text = False
        self.notes_badge.setText("Notes: Qwen3 Genie running")
        self.notes_text.setPlainText("Extracting structured notes with the local LLM.")
        self._append("Assistant", "Extracting structured notes with the local LLM.")
        self._sync_actions()

    def _notes_delta(self, text: str) -> None:
        if not text:
            return
        if not self.notes_stream_active:
            self._notes_started()
        self.notes_stream_has_text = True
        self._append_notes_status(text)
        self._append("Assistant", text)

    def _processing_finished(self, session: object) -> None:
        self.is_processing = False
        if isinstance(session, MeetingSession):
            self.session = session
            log_path = self.diagnostics_logger.write(session)
            self.status_label.setText(
                f"Ready: {session.audio.path.name} | transcript: {session.transcription.backend} | notes: {session.notes.backend}"
            )
            self.notes_badge.setText(f"Notes: {session.notes.backend}")
            self.fallback_badge.setText(
                f"Fallback: {session.notes.fallback_reason}" if session.notes.fallback_reason else "Fallback: none"
            )
            self.notes_text.setPlainText(session.notes.to_markdown())
            self._append("Assistant", f"Done. Exports and Q&A are ready.\n\nDiagnostics log: {log_path}")
            self._sync_actions()
        else:
            self.status_label.setText("Processing failed")
            self.notes_text.setPlainText("Processing failed: unexpected local pipeline result.")
            self._append("Assistant", "The local AI pipeline returned an unexpected result.")
            self._sync_actions()

    def _processing_failed(self, message: str) -> None:
        self.is_processing = False
        self.notes_stream_active = False
        self.status_label.setText("Processing failed")
        self.notes_badge.setText("Notes: failed")
        self.notes_text.setPlainText(message)
        self._append(
            "Assistant",
            "I captured the audio, but could not finish the local AI pipeline.\n\n"
            f"{message}",
        )
        self._set_status("Processing failed")
        self._sync_actions()

    def _processing_thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None
        self._sync_actions()

    def _load_session(self, session: MeetingSession) -> None:
        self.session = session
        self.status_label.setText(
            f"Ready: {session.audio.path.name} | transcript: {session.transcription.backend} | notes: {session.notes.backend}"
        )
        self.transcript_text.setPlainText(session.transcription.full_transcript)
        self.notes_text.setPlainText(session.notes.to_markdown())
        self.whisper_badge.setText(f"Whisper: {session.transcription.backend}")
        self.notes_badge.setText(f"Notes: {session.notes.backend}")
        self.fallback_badge.setText(
            f"Fallback: {session.notes.fallback_reason}" if session.notes.fallback_reason else "Fallback: none"
        )
        self._append("Assistant", self._format_result(session))
        self._sync_actions()

    def _format_result(self, session: MeetingSession) -> str:
        warnings = f"\n\nWarnings: {'; '.join(session.transcription.warnings)}" if session.transcription.warnings else ""
        return (
            "Done. Here are the notes.\n\n"
            f"{session.notes.to_markdown()}\n"
            "Transcript\n"
            "----------\n"
            f"{session.transcription.full_transcript}"
            f"{warnings}"
        )

    def _ask(self) -> None:
        question = self.question_input.text().strip()
        if not question:
            return
        self._append("You", question)
        self.question_input.clear()
        if not self.session:
            self._append("Assistant", "Generate notes first, then I can answer from the transcript.")
            return
        answer = self.qa_agent.answer(question, self.session.transcription.segments, self.session.notes)
        citations = f"\n\nCitations: {', '.join(answer.citations)}" if answer.citations else ""
        self._append("Assistant", answer.answer + citations)

    def _export_all(self) -> None:
        if not self.session:
            self._append("Assistant", "Generate notes before exporting.")
            return
        target = QFileDialog.getExistingDirectory(self, "Choose Export Folder", str(Path.cwd() / "exports"))
        if not target:
            return
        exported = ExportAgent(target).export_all(self.session)
        log_path = self.diagnostics_logger.write(self.session, exported)
        lines = "\n".join(f"- {kind}: {path}" for kind, path in exported.items())
        self._append("Assistant", f"Exported files:\n{lines}\n- diagnostics: {log_path}")
        self._set_status(f"Exported to {target}")

    def _append(self, speaker: str, message: str) -> None:
        existing = self.chat.toPlainText().strip()
        block = f"{speaker}:\n{message.strip()}"
        self.chat.setPlainText(f"{existing}\n\n{block}".strip())
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _append_notes_status(self, text: str) -> None:
        existing = self.notes_text.toPlainText().strip()
        block = text.strip()
        self.notes_text.setPlainText(f"{existing}\n\n{block}".strip())
        scrollbar = self.notes_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _sync_actions(self) -> None:
        is_recording = self.recorder.is_recording
        has_session = self.session is not None
        is_busy = self.is_processing
        self.record_button.setEnabled(not is_recording and not is_busy)
        self.upload_button.setEnabled(not is_recording and not is_busy)
        self.runtime_button.setEnabled(not is_busy)
        self.sample_button.setEnabled(not is_recording and not is_busy)
        self.stop_button.setEnabled(is_recording and not is_busy)
        self.cancel_button.setEnabled(is_busy and self.notes_stream_active and not self.cancel_requested)
        self.export_button.setEnabled(has_session and not is_busy)
        self.question_input.setEnabled(has_session and not is_busy)
        self.ask_button.setEnabled(has_session and not is_busy)

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Offline Meeting Notes", message)
        self._set_status(message)


def run_app() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
