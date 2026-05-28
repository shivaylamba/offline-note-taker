# Offline Note Taker: Private Meeting Intelligence on Snapdragon X Elite with Whisper, Qwen, and Qualcomm NPU

In the era of cloud-based AI assistants, meeting notes have become almost magically convenient. Record a call, upload the audio, wait a few seconds, and a polished summary appears.

But there is a catch.

Your meeting audio, transcript, action items, deadlines, and decisions often leave your machine.

For personal notes, that may be fine. For product reviews, engineering discussions, customer calls, hiring loops, legal conversations, or internal roadmap meetings, it becomes a real privacy and trust problem.

That is the motivation behind **Offline Note Taker**, a Windows desktop app that runs the complete meeting-notes workflow locally on a Snapdragon X / Qualcomm NPU machine.

The goal is simple:

> Instead of sending meeting audio to the cloud, run transcription and meeting intelligence directly on the AI PC.

Offline Note Taker records or imports meeting audio, transcribes it locally with Qualcomm AI Hub's Whisper Windows path, generates structured notes with Qwen3-4B through Qualcomm Genie / QAIRT, answers questions from the transcript, and exports Markdown, JSON, TXT, SRT, and VTT files.

No cloud transcription.

No cloud summarization.

No telemetry.

No uploaded meeting data.

## The Vision: Local-First Meeting AI

Most AI meeting assistants are built around cloud APIs. That makes them easy to ship, but it also introduces a few uncomfortable tradeoffs:

- audio leaves the device
- transcripts leave the device
- inference depends on network availability
- latency and cost are controlled by a remote service
- users need to trust that sensitive conversations are handled correctly elsewhere

Offline Note Taker flips that model.

It treats the Windows AI PC as the inference platform.

The machine records the meeting, runs speech-to-text locally, chunks and cleans the transcript, runs a local LLM for notes, validates the output, and keeps the final session on disk.

On Snapdragon X Elite, this becomes especially interesting because the device is not just a laptop CPU. It includes Qualcomm's heterogeneous AI stack: CPU, GPU, and Hexagon NPU. That makes it a strong target for private voice AI workflows.

## Architecture Overview

Offline Note Taker follows a transcript-first pipeline.

```text
Microphone / Audio File
        ->
Audio Metadata + WAV Recording
        ->
Qualcomm AI Hub Whisper Windows / Whisper-Base
        ->
Timestamped Transcript
        ->
Cleanup + Chunking
        ->
Grounded Extraction
        ->
Qwen3-4B via Genie / QAIRT
        ->
Validated Meeting Notes
        ->
Q&A + Exports + Local Session Library
```

The current demo beta uses:

- **Whisper path:** Qualcomm AI Hub Whisper Windows app with Whisper-Base ONNX/QNN assets.
- **LLM path:** Qwen3-4B ready-made Snapdragon X Elite Genie bundle with QAIRT 2.45.x.
- **Fallback path:** deterministic transcript-grounded extraction when the local LLM times out, is cancelled, or returns invalid structured output.
- **Runtime proof:** a doctor command and GUI panel that validate local model/runtime paths and NPU visibility.
- **Quality proof:** golden transcript evals for action items, owners, deadlines, decisions, and citation coverage.

This is not just a wrapper around a model. The app is designed around reliability, debuggability, and trust.

## Why Snapdragon X Elite?

For this project, Snapdragon X Elite matters for three reasons.

First, it gives Windows laptops an on-device AI story that is not theoretical. The Qualcomm AI Hub Whisper Windows sample demonstrates a practical path for running Whisper locally through ONNX Runtime and Snapdragon acceleration.

Second, QAIRT and Genie provide a realistic route for running local LLM workloads such as Qwen3-4B on Snapdragon-class devices.

Third, the hardware itself is a compelling demo surface. When the app runs, Windows Task Manager can show NPU utilization, and the app's own Performance panel reports which backend ran, how long it took, and whether fallback was used.

That combination creates a strong product story:

> An AI PC should not just call cloud APIs faster. It should make private local AI workflows possible.

## Technical Deep Dive: How It Works

### 1. Recording And Import

The app supports local microphone recording and audio upload.

For live recording, the GUI includes:

- microphone input selection
- recording timer
- pause and resume
- input level meter
- local WAV output

For imports, the app accepts common meeting audio formats such as `.wav`, `.mp3`, `.m4a`, and `.flac`, while preserving a local-only workflow.

### 2. Local Whisper Transcription

The transcription layer is built behind a runner abstraction.

The current practical Windows path is Qualcomm AI Hub's Whisper Windows app with Whisper-Base assets. The app detects:

- Whisper Windows app path
- `demo.py`
- Whisper Python environment
- encoder ONNX model
- decoder ONNX model
- Snapdragon NPU visibility where Windows exposes it

If the runtime is not configured, the app tells the user exactly what is missing instead of failing silently.

The transcript appears before notes generation starts. That design choice is intentional. In a real meeting product, users should see what the speech model heard before trusting the summary.

### 3. Chunking And Grounded Extraction

Long meetings cannot simply be thrown into a fixed-context LLM prompt.

Offline Note Taker chunks the transcript and keeps timestamp references attached. It also runs deterministic extraction to identify likely:

- action items
- owners
- deadlines
- decisions
- risks
- blockers
- open questions

This grounded extraction layer is not a replacement for the LLM. It is a guardrail.

It gives the app a transcript-backed baseline that can be used when the model output is incomplete, malformed, or unsupported.

### 4. Qwen3-4B Through Genie / QAIRT

For local meeting intelligence, the app uses Qwen3-4B through Qualcomm Genie / QAIRT.

The prompt asks for compact structured JSON:

- summary
- important points
- decisions
- action items
- owners
- deadlines
- evidence
- open questions
- risks and blockers
- follow-up email

The app does not directly trust raw model text.

Instead, it validates the response:

- output must parse as structured JSON
- placeholder values are rejected
- unsupported decisions are removed
- unsupported action items are dropped
- citation coverage is measured
- fallback notes are preserved if Qwen output is invalid

This matters because meeting notes are only useful if users can trust them.

### 5. Performance And Local Proof

One of my favorite parts of the app is the Performance tab.

After a run, it reports:

- Whisper backend
- Whisper latency
- Whisper real-time factor
- notes backend
- Qwen elapsed time
- fallback reason, if any
- NPU detection status
- diagnostics path
- local session path
- citation coverage
- unsupported decision count
- grounding status for action items

There is also a **Copy Proof** button that copies a concise report.

This turns the demo from "trust me, it is local" into something measurable and inspectable.

## Local Meeting Library

Each meeting is saved locally under:

```text
%LOCALAPPDATA%\OfflineNoteTaker\sessions\<session_id>\
```

A session contains:

```text
audio.wav or audio.<source-format>
session.json
transcript.json
notes.json
diagnostics.json
exports\
```

The desktop app includes a sidebar for local meeting history, search, reopen, export, and delete.

This makes the app feel less like a one-off demo and more like a real productivity tool.

## Evaluation: Measuring The Notes

A good AI project should not only generate outputs. It should evaluate them.

Offline Note Taker includes:

```powershell
offline-note-taker eval
offline-note-taker eval --json
```

The eval suite uses golden transcript fixtures covering:

- clear owners and deadlines
- ambiguous owners
- no action-item meetings
- decisions vs suggestions
- noisy ASR wording
- longer transcript-style meetings

Current deterministic fixture results:

| Fixture | Expected Actions | Extracted | Owner Acc. | Deadline Acc. | Citation Coverage | Unsupported Decisions |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_owner | 2 | 2 | 100% | 100% | 100% | 0 |
| clear_owners_deadlines | 2 | 2 | 100% | 100% | 100% | 0 |
| decisions_vs_suggestions | 1 | 1 | 100% | 100% | 100% | 0 |
| long_transcript | 2 | 2 | 100% | 100% | 100% | 0 |
| no_action_items | 0 | 0 | 100% | 100% | 100% | 0 |
| noisy_asr | 2 | 2 | 100% | 100% | 100% | 0 |
| **Total** | 9 | 9 | 100% | 100% | 100% | 0 |

This is a small fixture set, not a claim of universal accuracy. But it shows the engineering posture: define expected behavior, measure it, and make regressions visible.

## Privacy: Your Meeting, Your Machine

The privacy story is the core reason this project exists.

Offline Note Taker is designed so that:

- meeting audio stays local
- transcripts stay local
- LLM prompts stay local
- notes stay local
- diagnostics stay local
- exports stay local

Runtime assets are intentionally external and not bundled in GitHub because Qualcomm SDK/model files are large and may have licensing or access constraints.

The portable beta package includes the app, launcher, docs, tests, and sample data, but excludes:

- `external/`
- `models/`
- `recordings/`
- `exports/`
- `logs/`
- build artifacts
- caches

## What I Learned

The hardest part was not just calling Whisper or Qwen.

The harder part was making the system feel trustworthy:

- detecting runtime assets reliably
- explaining missing setup clearly
- showing transcript before notes
- validating LLM output
- preserving fallback notes
- grounding action items in timestamps
- keeping diagnostics local
- evaluating extraction behavior
- making the demo reproducible

That is the difference between a model demo and an AI product.

## Running The Demo

Install:

```powershell
python -m pip install -e ".[gui,dev]"
```

Check runtime:

```powershell
python -m offline_meeting_notes doctor
```

Run evals:

```powershell
python -m offline_meeting_notes eval
```

Launch:

```powershell
.\run_offline_note_taker.ps1
```

Or:

```powershell
python -m offline_meeting_notes
```

## Conclusion

Offline Note Taker is a glimpse of what local AI productivity apps can look like on modern AI PCs.

The point is not just that Whisper can transcribe audio or Qwen can summarize text.

The point is that the full workflow can become private, inspectable, measurable, and useful on the user's own machine.

That is the future I want from AI PCs:

local models, local data, local control, and product experiences that earn user trust.

Repository:

https://github.com/shivaylamba/offline-note-taker
