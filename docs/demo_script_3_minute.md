# Three-Minute Demo Script

Title: Offline Meeting Notes on Snapdragon X using Whisper and Qwen

## 0:00-0:30 Runtime Proof

1. Open the app.
2. Click `Runtime Check`.
3. Show pass checks for Whisper Windows, Whisper ONNX files, QAIRT, Genie, Qwen3 bundle files, and Hexagon NPU.
4. Point out the `Offline: network not required` badge.
5. Run `offline-note-taker eval` beforehand and keep the benchmark table ready.

## 0:30-1:20 Capture And Transcript

1. Select the microphone.
2. Click `Record`.
3. Speak a short meeting with owners, deadlines, and one blocker.
4. Show the timer and input level meter.
5. Click `Stop`.
6. Show the transcript appearing before notes.

## 1:20-2:20 Local Notes And Grounding

1. Show Qwen3 Genie running locally.
2. Watch NPU utilization in Task Manager if available.
3. Show validated final notes.
4. Click or point to timestamp citations in the transcript panel.
5. Open `Performance` and show Whisper latency, real-time factor, Qwen elapsed time, citation coverage, and NPU status.
6. Click `Copy Proof`.
7. Ask: `What are the action items?`
8. Ask: `Who owns the launch task?`

## 2:20-3:00 Export And Local Library

1. Export Markdown and JSON.
2. Show the session in the local meeting history sidebar.
3. Reopen the session.
4. Show diagnostics path and explain that SDK/model assets are external and no meeting data is uploaded.

## Backup Path

If Qwen takes too long, click `Cancel Notes`. The app should terminate Genie and render transcript-grounded fallback notes with a visible fallback reason.
