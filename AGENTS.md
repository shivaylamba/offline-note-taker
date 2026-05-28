# AGENTS.md

## Project: Offline Meeting Notes on Windows with Whisper + Qwen on Qualcomm NPU

Build a Windows desktop application that records or imports meeting audio, transcribes it locally using a Qualcomm NPU-supported Whisper path, and generates offline meeting notes using an on-device LLM such as Qwen3-4B from Qualcomm AI Hub.

The application should follow the on-device voice-agent pattern described by PyTorch ExecuTorch: voice workloads such as transcription, streaming, diarization, voice activity detection, and translation should run natively across device hardware including CPU, GPU, and NPU. ExecuTorch is positioned as a PyTorch-native inference platform for exporting voice models directly from PyTorch and running them across Linux, macOS, Windows, Android, and iOS. For the practical Windows MVP baseline, use Qualcomm AI Hub's Whisper Windows app and Whisper-Base model path.

---

## Core Goal

Create a fully offline meeting assistant for Windows on Snapdragon X / Qualcomm NPU devices.

The corrected baseline architecture is:

```text
Whisper Windows / Whisper-Base on Snapdragon NPU
        ->
Transcript
        ->
Qwen3-4B ready-made Snapdragon X Elite Genie bundle
        ->
CPU fallback only if the local Genie runtime is unavailable
        ->
Meeting Notes
```

The full application pipeline:

```text
Microphone / Audio File
        ->
Audio Preprocessing
        ->
Whisper ASR on Snapdragon NPU
        ->
Raw Transcript
        ->
Transcript Chunking
        ->
On-device LLM summarization
        ->
Meeting Summary + Decisions + Action Items
        ->
Export Notes
```

---

## Target Use Case

The primary use case is offline meeting notes.

The user should be able to:

1. Record a meeting locally.
2. Upload an existing audio file.
3. Generate a timestamped transcript.
4. Generate structured meeting notes.
5. Extract action items, owners, deadlines, blockers, and decisions.
6. Ask questions about the meeting transcript.
7. Export notes as Markdown, TXT, JSON, and optionally SRT or VTT.

---

## Source Model References

### Whisper Reference

For the Windows speech-to-text baseline, use Qualcomm AI Hub's Whisper Windows app, which demonstrates on-device speech-to-text inference with OpenAI Whisper through the ONNX Runtime execution provider, leveraging the Snapdragon NPU for low-latency transcription.

Primary app reference:
https://aihub.qualcomm.com/apps/whisper_windows_py

Compatible model reference:
https://aihub.qualcomm.com/compute/models/whisper_base

Optional model references:
https://aihub.qualcomm.com/models/whisper_small
https://aihub.qualcomm.com/models/whisper_large_v3_turbo

Implementation notes:

- Use Whisper Windows + Whisper-Base as the first working Windows Snapdragon NPU baseline.
- Preserve a backend abstraction so a later ExecuTorch + Qualcomm QNN implementation can be added without redesigning the app.
- Support CPU fallback if NPU execution is unavailable.
- Never upload audio or transcript data to the cloud.

### ExecuTorch Reference

ExecuTorch should remain an important future runtime path for a PyTorch-native implementation. PyTorch describes ExecuTorch as supporting export of voice models directly from PyTorch and execution across CPU, GPU, and NPU on Windows and other platforms.

The Qualcomm backend documentation states that Qualcomm AI Engine Direct is also referred to as QNN in ExecuTorch documentation, and the flow covers lowering and deploying a model for Qualcomm AI Engine Direct.

The Qualcomm ExecuTorch examples require setting up ExecuTorch, setting up the QNN backend, and configuring `QNN_SDK_ROOT`.

References:

- https://pytorch.org/blog/building-voice-agents-with-executorch-a-cross-platform-foundation-for-on-device-audio/
- https://docs.pytorch.org/executorch/stable/backends-qualcomm.html
- https://github.com/pytorch/executorch/blob/main/examples/qualcomm/README.md

### Qwen Reference

Use Qualcomm Qwen3-4B as the target model for meeting summarization and action-item extraction.

Reference:
https://aihub.qualcomm.com/models/qwen3_4b
https://huggingface.co/qualcomm/Qwen3-4B
https://github.com/qualcomm/ai-hub-apps/tree/main/tutorials/llm_on_genie

Important implementation note:

The Qualcomm LLM on Genie tutorial uses Qwen3-4B as its running example. For Snapdragon X Elite, use the ready-made `GENIE w4a16` asset from the Qualcomm Qwen3-4B Hugging Face page instead of running a large local LLM export job. The Qwen3-4B Snapdragon X Elite asset is built for QAIRT 2.45.x, so the local QAIRT runtime must match.

Fallback options:

- Use CPU summarization only as a temporary development fallback while keeping Whisper on NPU.
- Do not run huge local LLM export jobs unless the user explicitly chooses that path.

Because the Qwen3-4B page lists context lengths up to `4096`, the app must use transcript chunking and map-reduce summarization for long meetings.

---

## Agents

### 1. Audio Capture Agent

Responsible for recording or importing meeting audio.

Tasks:

- Capture microphone input.
- Import `.wav`, `.mp3`, `.m4a`, and `.flac`.
- Convert audio to mono.
- Resample to 16 kHz.
- Normalize audio.
- Save temporary chunks locally.
- Never upload audio to the cloud.

Inputs:

```json
{
  "source": "microphone | file",
  "path": "optional file path",
  "sample_rate": 16000
}
```

Outputs:

```json
{
  "audio_path": "local path",
  "duration_seconds": 0,
  "format": "wav",
  "sample_rate": 16000
}
```

---

### 2. Whisper Transcription Agent

Responsible for converting speech to text using Whisper locally, preferably on the Snapdragon NPU.

Tasks:

- Load the Qualcomm AI Hub Whisper Windows app/model path for the Windows MVP.
- Use Whisper-Base as the compatible baseline model.
- Run transcription locally.
- Return text with timestamps.
- Support CPU fallback if NPU execution is unavailable.
- Track latency and real-time factor.
- Keep the runtime interface open for a later ExecuTorch + Qualcomm QNN backend.

Expected output:

```json
{
  "segments": [
    {
      "start": "00:00:01.200",
      "end": "00:00:07.800",
      "text": "Let's discuss the launch timeline."
    }
  ],
  "full_transcript": "Let's discuss the launch timeline...",
  "backend": "qualcomm_npu | cpu",
  "latency_ms": 0,
  "real_time_factor": 0.0
}
```

Implementation notes:

- Preferred MVP path: Qualcomm AI Hub Whisper Windows app using ONNX Runtime execution provider on Snapdragon NPU.
- Preferred future PyTorch-native path: ExecuTorch + Qualcomm QNN backend.
- The runtime layer should report which backend actually ran inference.
- The runtime layer must not silently send data to a remote service.

---

### 3. Transcript Cleanup Agent

Responsible for making the raw transcript usable before sending it to the LLM.

Tasks:

- Remove filler repetition only when safe.
- Preserve technical terms.
- Preserve speaker names if available.
- Fix casing and punctuation.
- Do not invent missing words.
- Mark uncertain segments.

Input:

```json
{
  "raw_transcript": "...",
  "segments": []
}
```

Output:

```json
{
  "clean_transcript": "...",
  "uncertain_segments": []
}
```

---

### 4. Chunking Agent

Responsible for splitting the transcript for the on-device LLM.

Reason:

Qwen3-4B lists context lengths up to `4096`, so long meeting transcripts must be chunked before summarization.

Tasks:

- Split transcript into semantic chunks.
- Prefer speaker/topic boundaries.
- Keep chunks below safe token limits.
- Add timestamps to each chunk.
- Preserve chunk ordering.

Output:

```json
{
  "chunks": [
    {
      "chunk_id": 1,
      "start": "00:00:00",
      "end": "00:05:00",
      "text": "..."
    }
  ]
}
```

---

### 5. Meeting Summary Agent

Responsible for generating summaries from transcript chunks using the selected on-device LLM.

Tasks:

- Summarize each chunk.
- Extract key discussion points.
- Preserve factual grounding.
- Avoid hallucinating owners, dates, or decisions.
- If information is missing, say `not mentioned`.

Prompt template:

```text
You are an offline meeting notes assistant.

Summarize the following transcript chunk.

Return:
1. Short summary
2. Important points
3. Decisions mentioned
4. Action items mentioned
5. Open questions
6. Risks or blockers

Rules:
- Do not invent names, deadlines, or decisions.
- If something is not mentioned, write "not mentioned".
- Keep the output concise and structured.

Transcript chunk:
{{chunk_text}}
```

---

### 6. Meeting Synthesis Agent

Responsible for combining chunk summaries into final meeting notes.

Tasks:

- Merge duplicate points.
- Produce final summary.
- Extract global action items.
- Extract decisions.
- Extract blockers.
- Generate follow-up email draft.
- Generate Markdown output.

Final output format:

```markdown
# Meeting Notes

## Summary

## Key Decisions

## Action Items

| Owner | Task | Deadline | Evidence |
|---|---|---|---|

## Open Questions

## Risks / Blockers

## Follow-Up Email Draft

## Transcript Reference
```

---

### 7. Meeting Q&A Agent

Responsible for allowing users to ask questions over the transcript.

Example questions:

- "What did we decide about the launch?"
- "Who owns the demo?"
- "What were the blockers?"
- "Did anyone mention the deadline?"
- "Summarize only the engineering discussion."

Rules:

- Answer only from the transcript.
- Cite timestamps when possible.
- If not found, say the transcript does not mention it.
- Do not use external knowledge.

---

### 8. Export Agent

Responsible for saving outputs.

Supported exports:

- `.md`
- `.txt`
- `.json`
- `.srt`
- `.vtt`

Output files:

```text
meeting_transcript.txt
meeting_transcript.srt
meeting_transcript.vtt
meeting_notes.md
meeting_summary.json
```

---

## Windows GUI Requirements

Build a simple Windows GUI.

Recommended options:

- WinUI 3
- WPF
- Qt
- Electron + native inference bridge

Preferred architecture:

```text
Windows GUI
   ->
Native Inference Bridge
   ->
Whisper Runner
   ->
LLM Runner
   ->
Local Storage
```

GUI sections:

```text
[ Record Meeting ] [ Stop ] [ Upload Audio ]

Backend:
[ Qualcomm NPU ] [ CPU Fallback ]

Transcript Panel:
--------------------------------
Live / generated transcript
--------------------------------

Meeting Notes Panel:
--------------------------------
Summary
Decisions
Action Items
Open Questions
--------------------------------

[ Export Markdown ] [ Export TXT ] [ Export JSON ]
```

---

## Runtime Requirements

### Whisper Runtime

Preferred Windows MVP:

```text
Qualcomm AI Hub Whisper Windows app
Whisper-Base model
ONNX Runtime execution provider
Snapdragon NPU
```

Future PyTorch-native path:

```text
ExecuTorch + Qualcomm QNN backend
```

Alternative baseline:

```text
CPU fallback
```

### Qwen / LLM Runtime

Target:

```text
Qualcomm Qwen3-4B ready-made Snapdragon X Elite Genie bundle
```

The app should support:

```text
Prompt Processor
Token Generator
Streaming output
Local model files
No cloud calls
```

Required verification before production commitment:

- Download the Snapdragon X Elite `GENIE w4a16` asset.
- Install matching QAIRT 2.45.x.
- Confirm `genie_config.json` and QNN binaries are present.
- Confirm `genie-t2t-run.exe` can answer a short prompt.
- Confirm token streaming and profile output.

Fallback:

- CPU summarization fallback for development only.

---

## Non-Negotiable Constraints

1. The app must work offline.
2. Audio must never leave the device.
3. Transcript must never leave the device.
4. LLM inference must run locally.
5. CPU fallback is allowed, but the primary demo path should be Qualcomm NPU for Whisper.
6. Long transcripts must be chunked.
7. The LLM must not invent action items, deadlines, or owners.
8. Every generated note should be traceable to transcript timestamps where possible.
9. Qwen3-4B must use a local ready-made Genie bundle and matching QAIRT runtime before it is represented as the production NPU path.

---

## Suggested Folder Structure

```text
offline-meeting-notes/
+-- AGENTS.md
+-- README.md
+-- app/
|   +-- windows-gui/
|   +-- native-bridge/
|   +-- assets/
+-- models/
|   +-- whisper/
|   +-- qwen/
+-- src/
|   +-- audio/
|   +-- transcription/
|   +-- llm/
|   +-- chunking/
|   +-- summarization/
|   +-- qa/
|   +-- export/
+-- prompts/
|   +-- summarize_chunk.txt
|   +-- synthesize_notes.txt
|   +-- meeting_qa.txt
+-- tests/
|   +-- sample_audio/
|   +-- test_transcription.py
|   +-- test_chunking.py
|   +-- test_summary_quality.py
+-- docs/
    +-- architecture.md
    +-- model_setup.md
    +-- demo_script.md
```

---

## MVP Milestones

### Milestone 1: Audio + GUI

- Build Windows GUI.
- Add record button.
- Add audio upload.
- Save audio locally.
- Display waveform or duration.

### Milestone 2: Whisper Transcription

- Integrate Qualcomm AI Hub Whisper Windows path.
- Use Whisper-Base as the first compatible baseline model.
- Run local transcription.
- Display transcript.
- Add backend indicator.
- Add latency metrics.
- Preserve runtime interface for ExecuTorch + QNN.

### Milestone 3: On-Device Meeting Notes

- Download and configure the Qwen3-4B Snapdragon X Elite ready-made Genie bundle.
- Install matching QAIRT 2.45.x.
- Add transcript chunking.
- Generate summaries.
- Generate action items.
- Generate decisions.
- Support CPU summarization only as a development fallback.

### Milestone 4: Meeting Q&A

- Add chat interface.
- Ask questions over transcript.
- Return timestamp-grounded answers.

### Milestone 5: Export + Demo Polish

- Export Markdown.
- Export TXT.
- Export JSON.
- Export SRT or VTT.
- Add demo sample meeting.
- Add performance dashboard.

---

## Demo Script

Title:

```text
Offline Meeting Notes on Windows using Whisper + Qwen on Qualcomm NPU
```

Demo flow:

1. Open the Windows app.
2. Click "Record Meeting."
3. Speak for 30-60 seconds.
4. Stop recording.
5. Run Whisper transcription locally using the Whisper Windows / Whisper-Base Snapdragon NPU path.
6. Show transcript.
7. Run local meeting summarization using Qwen3-4B through Genie.
8. Show:
   - Summary
   - Decisions
   - Action items
   - Open questions
9. Ask:
   - "What were the action items?"
   - "What deadline was mentioned?"
10. Export Markdown notes.

---

## Example Meeting Notes Prompt

```text
You are an offline meeting notes assistant running locally on a Windows device.

Given the transcript below, generate structured meeting notes.

Return:

# Meeting Notes

## Summary
A concise summary of the meeting.

## Key Decisions
Only include decisions that were explicitly made.

## Action Items
For each action item, include:
- Owner
- Task
- Deadline
- Evidence from transcript

If owner or deadline is not mentioned, write "not mentioned".

## Open Questions
Questions that were raised but not answered.

## Risks / Blockers
Risks, delays, dependencies, or blockers discussed.

## Follow-Up Email Draft
A short professional follow-up email.

Rules:
- Do not invent facts.
- Do not invent names.
- Do not invent deadlines.
- Use only the transcript.
- Preserve technical terms.
- Cite transcript timestamps where possible.

Transcript:
{{transcript}}
```

---

## Success Criteria

The project is successful if:

- A user can record a meeting offline.
- Whisper generates a usable transcript locally.
- The first Windows demo path uses Whisper Windows / Whisper-Base on Snapdragon NPU.
- The app can generate structured meeting notes locally.
- The app runs on Windows Snapdragon / Qualcomm NPU hardware.
- The app provides CPU fallback.
- The final notes contain no hallucinated action items.
- The demo clearly shows the privacy and latency benefits of on-device AI.
- Qwen3-4B Genie support is verified with the matching QAIRT runtime before it is presented as the production NPU path.

---

## Positioning

This project demonstrates:

```text
Private voice AI
Offline productivity
On-device LLM workflows
Windows on Snapdragon AI PCs
ExecuTorch voice model deployment path
Qualcomm AI Hub model deployment
NPU-accelerated meeting transcription
Local meeting intelligence
```

The strongest narrative:

> "Instead of sending meeting audio to the cloud, we run the complete voice-to-notes pipeline locally: Whisper transcribes the meeting, an on-device LLM understands it, and the user gets private meeting notes directly on a Windows AI PC."

---

## References

1. PyTorch ExecuTorch voice agents blog: https://pytorch.org/blog/building-voice-agents-with-executorch-a-cross-platform-foundation-for-on-device-audio/
2. Qualcomm AI Hub Whisper Windows app: https://aihub.qualcomm.com/apps/whisper_windows_py
3. Qualcomm AI Hub Whisper-Base model: https://aihub.qualcomm.com/compute/models/whisper_base
4. Qualcomm AI Hub Whisper-Small model: https://aihub.qualcomm.com/models/whisper_small
5. Qualcomm AI Hub Whisper Large v3 Turbo model: https://aihub.qualcomm.com/models/whisper_large_v3_turbo
6. Qualcomm AI Hub Qwen3-4B: https://aihub.qualcomm.com/models/qwen3_4b
7. Qualcomm AI Hub Get Started: https://aihub.qualcomm.com/get-started
8. ExecuTorch Qualcomm backend docs: https://docs.pytorch.org/executorch/stable/backends-qualcomm.html
9. ExecuTorch Qualcomm examples: https://github.com/pytorch/executorch/blob/main/examples/qualcomm/README.md
