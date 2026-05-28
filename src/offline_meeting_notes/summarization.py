from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .aihub_runtime import find_qairt_home, find_qwen3_genie_config, qairt_version_is_compatible
from .models import ActionItem, MeetingNotes, TranscriptChunk, TranscriptSegment

DECISION_TERMS = ("decided", "decision", "agreed", "approved", "confirmed", "go with")
RISK_TERMS = ("risk", "blocker", "blocked", "dependency", "delay", "concern", "issue")
ACTION_PATTERNS = [
    re.compile(
        r"\b(?P<owner>[A-Z][a-zA-Z]+),\s+you\s+are\s+responsible\s+for\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
    ),
    re.compile(
        r"\b(?P<owner>[A-Z][a-zA-Z]+),\s+you\s+(?:need to|should|will|are supposed to|are supposed to go ahead and)\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
    ),
    re.compile(
        r"\b(?P<owner>[A-Z][a-zA-Z]+)\s+(?:you'?re|you are|your)\s+.*?,\s+to\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:task|takeaway).*?\bfor\s+(?P<owner>[A-Z][a-zA-Z]+)\s+(?:is that|is|would be)\s+(?:you\s+)?(?:need to|should|will|to|go ahead and)?\s*(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<owner>[A-Z][a-zA-Z]+)\s+(?:will|should|needs to|to)\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
    ),
    re.compile(
        r"\b[Aa]ction item[:\s-]+(?:(?P<owner>[A-Z][a-zA-Z]+)\s+)?(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
    ),
    re.compile(
        r"\b(?:main takeaway|takeaway|next step|follow[- ]?up)\b.*?\b(?:to|and)\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgo ahead and\s+(?P<task>.*?)(?:\s+by\s+(?P<deadline>[^.?!]+))?[.?!]?$",
        re.IGNORECASE,
    ),
]
ACTION_CUES = (
    "will",
    "should",
    "action item",
    "action items",
    "need to",
    "needs to",
    "responsible for",
    "task",
    "tasks",
    "main takeaway",
    "takeaway",
    "next step",
    "follow up",
    "follow-up",
    "go ahead and",
    "would be to",
    "ensure that",
)
OWNER_STOP_WORDS = {"us", "me", "you", "them", "team", "everyone"}
ACTION_VERB_PATTERN = re.compile(
    r"\b(?P<task>(?:test(?: out)?|push|write|compare|generate)\b.*?)"
    r"(?=\s+(?:and\s+)?(?:number\s+\w+\s+)?(?:to\s+)?(?:test(?: out)?|push|write|compare|generate)\b|[.?!]|$)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MeetingNotesInput:
    chunks: list[TranscriptChunk]
    segments: list[TranscriptSegment]


class MeetingNotesRunner:
    backend_name = "unknown"

    def generate(self, payload: MeetingNotesInput) -> MeetingNotes:
        raise NotImplementedError

    def generate_stream(
        self,
        payload: MeetingNotesInput,
        on_text: Callable[[str], None] | None = None,
    ) -> MeetingNotes:
        notes = self.generate(payload)
        if on_text:
            on_text(notes.to_markdown())
        return notes


class FallbackMeetingNotesRunner(MeetingNotesRunner):
    backend_name = "deterministic_fallback"

    def generate(self, payload: MeetingNotesInput) -> MeetingNotes:
        sentences = self._sentences_with_evidence(payload.segments)
        summary = self._summary(sentences)
        important_points = self._important_points(sentences)
        decisions = self._matching_sentences(sentences, DECISION_TERMS)
        actions = self._action_items(sentences)
        open_questions = [self._with_evidence(text, evidence) for text, evidence in sentences if "?" in text]
        risks = self._matching_sentences(sentences, RISK_TERMS)
        references = [f"{chunk.start}-{chunk.end}: chunk {chunk.chunk_id}" for chunk in payload.chunks]

        return MeetingNotes(
            summary=summary,
            important_points=important_points,
            decisions=decisions,
            action_items=actions,
            open_questions=open_questions,
            risks_blockers=risks,
            follow_up_email=self._follow_up_email(summary, actions),
            transcript_reference=references,
            backend=self.backend_name,
        )

    def _sentences_with_evidence(self, segments: list[TranscriptSegment]) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for segment in segments:
            evidence = f"{segment.start}-{segment.end}"
            parts = re.split(r"(?<=[.!?])\s+", segment.text.strip())
            for part in parts:
                cleaned = part.strip()
                if cleaned:
                    results.append((cleaned, evidence))
        return results

    def _summary(self, sentences: list[tuple[str, str]]) -> str:
        if not sentences:
            return "not mentioned"
        selected = [self._with_evidence(text, evidence) for text, evidence in sentences[:2]]
        return " ".join(selected)

    def _important_points(self, sentences: list[tuple[str, str]]) -> list[str]:
        if not sentences:
            return ["not mentioned"]
        points = [self._with_evidence(text, evidence) for text, evidence in sentences[:5]]
        return self._dedupe(points)

    def _matching_sentences(self, sentences: list[tuple[str, str]], terms: tuple[str, ...]) -> list[str]:
        matches = []
        for text, evidence in sentences:
            lowered = text.lower()
            if any(term in lowered for term in terms):
                matches.append(self._with_evidence(text, evidence))
        return self._dedupe(matches)

    def _action_items(self, sentences: list[tuple[str, str]]) -> list[ActionItem]:
        items: list[ActionItem] = []
        for text, evidence in sentences:
            lowered = text.lower()
            if not any(cue in lowered for cue in ACTION_CUES):
                continue
            matched_specific_action = False
            for pattern in ACTION_PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                owner = (match.groupdict().get("owner") or "not mentioned").strip()
                if owner.lower() in OWNER_STOP_WORDS or (owner != "not mentioned" and not owner[0].isupper()):
                    continue
                task = self._clean_task(match.groupdict().get("task") or "not mentioned")
                deadline = (match.groupdict().get("deadline") or "not mentioned").strip(" .")
                if task:
                    items.append(ActionItem(owner=owner, task=task, deadline=deadline, evidence=f"{evidence}: {text}"))
                    matched_specific_action = True
                break
            if not matched_specific_action:
                items.extend(self._verb_action_items(text, evidence))
        return self._dedupe_actions(items)

    def _verb_action_items(self, text: str, evidence: str) -> list[ActionItem]:
        items = []
        for match in ACTION_VERB_PATTERN.finditer(text):
            task = self._clean_task(match.group("task"))
            if task:
                items.append(
                    ActionItem(
                        owner="not mentioned",
                        task=task,
                        deadline="not mentioned",
                        evidence=f"{evidence}: {text}",
                    )
                )
        return items

    def _clean_task(self, task: str) -> str:
        task = re.sub(r"^(?:to\s+|then\s+|go ahead and\s+)+", "", task.strip(" ."), flags=re.IGNORECASE)
        task = re.sub(r"^(?:number\s+\w+\s+)?(?:would be to|is to|are to)\s+", "", task, flags=re.IGNORECASE)
        task = re.sub(r"^(?:go ahead and\s+)+", "", task, flags=re.IGNORECASE)
        return task.strip(" .")

    def _follow_up_email(self, summary: str, actions: list[ActionItem]) -> str:
        action_sentence = "No explicit action items were mentioned."
        if actions:
            action_sentence = "Action items are listed in the notes table."
        return (
            "Hi everyone,\n\n"
            f"Here are the meeting notes generated from the local transcript. Summary: {summary}\n\n"
            f"{action_sentence}\n\n"
            "Best,\nOffline Meeting Notes"
        )

    def _with_evidence(self, text: str, evidence: str) -> str:
        return f"{text} [{evidence}]"

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        deduped = []
        for value in values:
            key = value.lower()
            if key not in seen:
                deduped.append(value)
                seen.add(key)
        return deduped

    def _dedupe_actions(self, items: list[ActionItem]) -> list[ActionItem]:
        seen = set()
        deduped = []
        for item in items:
            key = (item.owner.lower(), item.task.lower(), item.deadline.lower())
            if key not in seen:
                deduped.append(item)
                seen.add(key)
        return deduped


class QwenHybridMeetingNotesRunner(MeetingNotesRunner):
    backend_name = "qwen3.5_hybrid_qnn"

    def __init__(
        self,
        python_path: Path,
        script_path: Path,
        timeout_seconds: int = 900,
        max_new_tokens: int = 80,
    ) -> None:
        self.python_path = python_path
        self.script_path = script_path
        self.timeout_seconds = timeout_seconds
        self.max_new_tokens = max_new_tokens
        self.grounded_extractor = FallbackMeetingNotesRunner()

    @classmethod
    def autodetect(cls) -> "QwenHybridMeetingNotesRunner | None":
        if os.environ.get("OFFLINE_NOTES_QWEN_BACKEND", "auto").lower() in {"off", "false", "0"}:
            return None

        python_path = Path(
            os.environ.get(
                "OFFLINE_NOTES_QWEN_PYTHON",
                r"C:\Users\Admin\Desktop\stable-diffusion-3\qwen35_qnn\.venv-aihub\Scripts\python.exe",
            )
        )
        script_path = Path(
            os.environ.get(
                "OFFLINE_NOTES_QWEN_SCRIPT",
                r"C:\Users\Admin\Desktop\stable-diffusion-3\qwen35_hybrid_qnn_chat.py",
            )
        )
        if python_path.exists() and script_path.exists():
            return cls(python_path=python_path, script_path=script_path)
        return None

    def generate(self, payload: MeetingNotesInput) -> MeetingNotes:
        grounded = self.grounded_extractor.generate(payload)
        prompt = self._prompt(payload)
        command = [
            str(self.python_path),
            str(self.script_path),
            prompt,
            "--max-new-tokens",
            str(self.max_new_tokens),
            "--temperature",
            "0",
        ]
        completed = subprocess.run(
            command,
            cwd=str(self.script_path.parent),
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(error or "Qwen hybrid QNN notes runner failed.")

        qwen_text = self._extract_assistant(completed.stdout)
        if not qwen_text:
            raise RuntimeError("Qwen hybrid QNN runner completed but did not return notes.")

        return MeetingNotes(
            summary=grounded.summary,
            important_points=grounded.important_points,
            decisions=grounded.decisions,
            action_items=grounded.action_items,
            open_questions=grounded.open_questions,
            risks_blockers=grounded.risks_blockers,
            follow_up_email=grounded.follow_up_email,
            transcript_reference=grounded.transcript_reference,
            backend=self.backend_name,
        )

    def _prompt(self, payload: MeetingNotesInput) -> str:
        transcript = "\n".join(f"[{segment.start}-{segment.end}] {segment.text}" for segment in payload.segments)
        return (
            "You are an offline meeting notes assistant. Use only the transcript. "
            "Write very concise meeting notes: summary, decisions, actions, blockers. "
            "Use 'not mentioned' for missing facts. Keep it short.\n\nTranscript:\n"
            f"{transcript}"
        )

    def _extract_assistant(self, stdout: str) -> str:
        marker = "Assistant:"
        if marker in stdout:
            return stdout.split(marker, 1)[1].strip()
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        return lines[-1] if lines else ""


class Qwen3GenieMeetingNotesRunner(MeetingNotesRunner):
    backend_name = "qwen3_4b_genie"

    def __init__(
        self,
        genie_config: Path,
        qairt_home: Path,
        timeout_seconds: int = 150,
    ) -> None:
        self.genie_config = genie_config
        self.qairt_home = qairt_home
        self.timeout_seconds = timeout_seconds
        self.grounded_extractor = FallbackMeetingNotesRunner()

    @classmethod
    def autodetect(cls) -> "Qwen3GenieMeetingNotesRunner":
        genie_config = find_qwen3_genie_config()
        qairt_home = find_qairt_home()
        missing = []
        if not genie_config:
            missing.append("Qwen3-4B Genie config was not found.")
        if not qairt_home:
            missing.append("QAIRT SDK was not found.")
        elif not qairt_version_is_compatible(qairt_home):
            missing.append(f"Qwen3-4B requires QAIRT 2.45.x, but QAIRT_HOME is {qairt_home}.")
        if missing:
            raise RuntimeError(
                " ".join(missing)
                + " Download the Qualcomm Qwen3-4B Snapdragon X Elite ready-made Genie bundle and set "
                "OFFLINE_NOTES_QWEN3_GENIE_CONFIG plus QAIRT_HOME."
            )
        return cls(genie_config=genie_config, qairt_home=qairt_home)  # type: ignore[arg-type]

    def generate(self, payload: MeetingNotesInput) -> MeetingNotes:
        return self._generate(payload, on_text=None)

    def generate_stream(
        self,
        payload: MeetingNotesInput,
        on_text: Callable[[str], None] | None = None,
    ) -> MeetingNotes:
        return self._generate(payload, on_text=on_text)

    def _generate(
        self,
        payload: MeetingNotesInput,
        on_text: Callable[[str], None] | None,
    ) -> MeetingNotes:
        fallback = self.grounded_extractor.generate(payload)
        prompt = self._prompt(payload)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write(prompt)
            prompt_file = Path(handle.name)
        try:
            command = [
                str(self.qairt_home / "bin" / "aarch64-windows-msvc" / "genie-t2t-run.exe"),
                "-c",
                str(self.genie_config),
                "--prompt_file",
                str(prompt_file),
            ]
            stdout, returncode = self._run_streaming(command, on_text)
        finally:
            prompt_file.unlink(missing_ok=True)

        if returncode != 0:
            error = stdout.strip()
            raise RuntimeError(error or "Qwen3 Genie runner failed.")

        qwen_text = self._extract_output(stdout)
        if not qwen_text:
            fallback.backend = f"{self.backend_name}_fallback_empty"
            return fallback

        return self._notes_from_llm_text(qwen_text, fallback)

    def _run_streaming(self, command: list[str], on_text: Callable[[str], None] | None) -> tuple[str, int]:
        process = subprocess.Popen(
            command,
            cwd=str(self.genie_config.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self._env(),
            bufsize=1,
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                while True:
                    char = process.stdout.read(1)
                    if not char:
                        break
                    output_queue.put(char)
            finally:
                output_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        stdout_parts: list[str] = []
        completed_json = False
        timed_out = False
        output_done = False
        started = time.monotonic()
        last_progress = started

        while True:
            try:
                char = output_queue.get(timeout=0.1)
            except queue.Empty:
                char = ""
            if char is None:
                output_done = True
                char = ""
            if char:
                stdout_parts.append(char)
                if char == "}" and self._has_complete_json("".join(stdout_parts)):
                    completed_json = True
                    if on_text:
                        on_text("Structured notes are ready. Rendering final notes now.")
                    process.terminate()
                    break
                now = time.monotonic()
                if on_text and now - last_progress >= 10:
                    elapsed = int(now - started)
                    on_text(f"Still extracting structured notes locally ({elapsed}s elapsed, NPU active).")
                    last_progress = now
                continue
            if output_done and process.poll() is not None:
                break
            now = time.monotonic()
            if now - started >= self.timeout_seconds:
                timed_out = True
                if on_text:
                    on_text("Qwen is taking too long; using the local transcript-grounded fallback notes.")
                process.terminate()
                break
            if on_text and now - last_progress >= 10:
                elapsed = int(now - started)
                on_text(f"Still extracting structured notes locally ({elapsed}s elapsed, NPU active).")
                last_progress = now

        if completed_json or timed_out:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            returncode = 0
        else:
            returncode = process.wait(timeout=5)
        stdout = "".join(stdout_parts)
        if on_text and not completed_json and not timed_out:
            final_text = self._extract_output(stdout)
            if final_text:
                on_text("Received local LLM output. Rendering final notes now.")
        return stdout, returncode

    def _has_complete_json(self, stdout: str) -> bool:
        text = self._extract_output(stdout)
        if "{" not in text or "}" not in text:
            return False
        try:
            self._json_payload(text)
        except ValueError:
            return False
        return True

    def _stream_visible_text(self, stdout: str) -> str:
        if "[BEGIN]:" not in stdout:
            return ""
        visible = stdout.split("[BEGIN]:", 1)[1]
        end_index = visible.find("[END")
        if end_index != -1:
            visible = visible[:end_index]
        visible = re.sub(r"<think>.*?</think>", "", visible, flags=re.DOTALL)
        visible = re.sub(r"<think>.*", "", visible, flags=re.DOTALL)
        visible = re.sub(r"\[E?N?D?$", "", visible)
        return visible

    def _visible_delta(self, previous: str, current: str) -> str:
        if current.startswith(previous):
            return current[len(previous) :]
        index = 0
        limit = min(len(previous), len(current))
        while index < limit and previous[index] == current[index]:
            index += 1
        return current[index:]

    def _prompt(self, payload: MeetingNotesInput) -> str:
        transcript = "\n".join(f"[{segment.start}-{segment.end}] {segment.text}" for segment in payload.segments)
        return (
            "<|im_start|>system\n"
            "You extract structured meeting notes from transcripts. Use only the transcript. "
            "Do not use outside knowledge. Do not comment on transcript quality. "
            "Treat an action item as any future task, responsibility, ownership statement, deliverable, instruction, "
            "follow-up, or commitment, regardless of exact wording. "
            "Owners can be people, roles, or not mentioned. Deadlines must be exact text from the transcript or not mentioned. "
            "Evidence must quote or closely paraphrase the transcript with its timestamp. "
            "Return only valid JSON. No Markdown. No prose before or after the JSON."
            "<|im_end|>\n"
            "<|im_start|>user\n"
            "Return one compact JSON object with these keys: "
            "summary, important_points, decisions, action_items, open_questions, risks_blockers, "
            "follow_up_email, transcript_reference.\n"
            "action_items must be an array of objects. Each action item object must contain: "
            "owner, task, deadline, evidence.\n\n"
            "Rules:\n"
            "- Do not copy the key list as placeholder content.\n"
            "- Never output placeholder values like \"string\", \"owner\", \"task\", \"deadline\", or \"evidence\".\n"
            "- Decisions are final choices or agreed outcomes only; assignments and responsibilities are action_items, not decisions.\n"
            "- If no decision, question, or blocker is mentioned, use an empty array for that field.\n"
            "- If an action owner is missing, use \"not mentioned\".\n"
            "- If an action deadline is missing, use \"not mentioned\".\n"
            "- Do not omit action items just because they are phrased as responsibilities, takeaways, or goals.\n"
            "- Preserve ASR wording where relevant; do not silently fix names or facts.\n\n"
            f"Transcript:\n{transcript}"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

    def _notes_from_llm_text(self, text: str, fallback: MeetingNotes) -> MeetingNotes:
        try:
            payload = self._json_payload(text)
        except ValueError:
            fallback.backend = f"{self.backend_name}_fallback_parse_failed"
            return fallback

        decisions = self._string_list(payload, "decisions", fallback.decisions)
        if not fallback.decisions:
            decisions = []
        notes = MeetingNotes(
            summary=self._string_field(payload, "summary", fallback.summary),
            important_points=self._string_list(payload, "important_points", fallback.important_points),
            decisions=decisions,
            action_items=self._action_items_from_payload(payload, fallback.action_items),
            open_questions=self._string_list(payload, "open_questions", fallback.open_questions),
            risks_blockers=self._string_list(payload, "risks_blockers", fallback.risks_blockers),
            follow_up_email=self._string_field(payload, "follow_up_email", fallback.follow_up_email),
            transcript_reference=self._string_list(payload, "transcript_reference", fallback.transcript_reference),
            backend=self.backend_name,
        )
        if not notes.summary or notes.summary == "not mentioned":
            notes.summary = fallback.summary
        if not notes.action_items and fallback.action_items:
            notes.action_items = fallback.action_items
            notes.backend = f"{self.backend_name}_fallback_actions"
        return notes

    def _json_payload(self, text: str) -> dict[str, object]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        if start == -1:
            raise ValueError("No JSON object found in Qwen output.")
        candidates = [self._repair_json_suffix(cleaned[start:])]
        end = cleaned.rfind("}")
        if end != -1 and end > start:
            candidates.append(self._repair_json_suffix(cleaned[start : end + 1]))
        payload = None
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            raise ValueError("Invalid JSON from Qwen output.")
        if not isinstance(payload, dict):
            raise ValueError("Qwen output JSON was not an object.")
        return payload

    def _repair_json_suffix(self, text: str) -> str:
        balance = 0
        in_string = False
        escaped = False
        for char in text:
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                balance += 1
            elif char == "}":
                balance -= 1
        if balance > 0:
            return text + ("}" * balance)
        return text

    def _string_field(self, payload: dict[str, object], key: str, fallback: str) -> str:
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and not self._is_placeholder(value):
            return value.strip()
        return fallback

    def _string_list(self, payload: dict[str, object], key: str, fallback: list[str]) -> list[str]:
        value = payload.get(key)
        if isinstance(value, str):
            return [] if self._is_placeholder(value) else [value.strip()]
        if not isinstance(value, list):
            return fallback
        results = [str(item).strip() for item in value if str(item).strip() and not self._is_placeholder(str(item))]
        return results

    def _action_items_from_payload(
        self,
        payload: dict[str, object],
        fallback: list[ActionItem],
    ) -> list[ActionItem]:
        raw_items = payload.get("action_items")
        if not isinstance(raw_items, list):
            return fallback
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            owner = str(raw.get("owner") or "not mentioned").strip() or "not mentioned"
            task = str(raw.get("task") or "").strip()
            deadline = str(raw.get("deadline") or "not mentioned").strip() or "not mentioned"
            evidence = str(raw.get("evidence") or "not mentioned").strip() or "not mentioned"
            if task and task.lower() != "not mentioned" and not self._is_placeholder(task):
                if self._is_placeholder(owner):
                    owner = "not mentioned"
                if self._is_placeholder(deadline):
                    deadline = "not mentioned"
                if self._is_placeholder(evidence):
                    evidence = "not mentioned"
                items.append(ActionItem(owner=owner, task=task, deadline=deadline, evidence=evidence))
        return items

    def _is_placeholder(self, value: str) -> bool:
        return value.strip().lower() in {
            "string",
            "owner",
            "task",
            "deadline",
            "evidence",
            "array",
            "object",
            "not mentioned",
        }

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["QAIRT_HOME"] = str(self.qairt_home)
        env["Path"] = (
            str(self.qairt_home / "bin" / "aarch64-windows-msvc")
            + os.pathsep
            + str(self.qairt_home / "lib" / "aarch64-windows-msvc")
            + os.pathsep
            + env.get("Path", "")
        )
        env["ADSP_LIBRARY_PATH"] = str(self.qairt_home / "lib" / "hexagon-v73" / "unsigned")
        return env

    def _extract_output(self, stdout: str) -> str:
        if "[BEGIN]:" in stdout:
            stdout = stdout.split("[BEGIN]:", 1)[1]
        end_index = stdout.find("[END")
        if end_index != -1:
            stdout = stdout[:end_index]
        stdout = re.sub(r"<think>.*?</think>", "", stdout, flags=re.DOTALL).strip()
        if stdout:
            return stdout
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        return lines[-1] if lines else ""
