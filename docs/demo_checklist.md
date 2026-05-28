# Demo Checklist

Use this before a live Snapdragon / Qualcomm NPU demo.

## Hardware And Runtime

- Confirm the machine is a Snapdragon X / Qualcomm NPU device.
- Open Task Manager -> Performance and confirm an NPU graph is visible.
- Confirm Python 3.12 is available for the app.
- Confirm Python 3.11 is available for the Whisper Windows sample environment.
- Confirm QAIRT 2.45.x is installed.
- Confirm the Qwen3-4B Genie bundle is present outside Git under `models/`.

## Runtime Check

Run:

```powershell
offline-note-taker doctor
offline-note-taker doctor --json
```

Expected:

- Whisper Windows app: pass
- Whisper encoder/decoder ONNX: pass
- Whisper Python environment: pass
- QAIRT 2.45.x: pass
- Genie runner: pass
- Qwen3 bundle files: pass
- ADSP path: pass or warning if the app can set it internally
- NPU device: pass or warning depending on Windows device query visibility

If doctor fails, do not start the live demo until the missing item is fixed.

If paths are missing in the GUI, click `Setup`, browse to the local Qualcomm paths, save, and rerun `Runtime Check`.

## Sample Flow

Run:

```powershell
offline-note-taker smoke
```

Expected:

- Exports are created under `exports/`.
- A diagnostics JSON file is created under `logs/`.
- No Qualcomm runtime is required for this sample fallback path.
- The session appears in the left meeting-history sidebar.

## Recording Flow

1. Launch:

   ```powershell
   offline-note-taker
   ```

2. Click `Runtime Check`.
3. Select the microphone from the input dropdown.
4. Click `Record`.
5. Confirm the recording timer and input level meter move.
6. Speak for 30-60 seconds.
7. Click `Stop`.
8. Confirm transcript appears before notes.
9. Watch Task Manager NPU utilization during Whisper/Qwen.
10. Confirm final notes include summary, important points, decisions, action items, owners, deadlines, evidence, and backend.
11. Ask a Q&A question such as:

   ```text
   What are the action items and owners?
   ```

12. Click `Review Notes`, make a tiny Markdown edit, and save.
13. Export notes and verify Markdown, TXT, JSON, SRT, and VTT files.
14. Reopen the meeting from the sidebar.

## Expected Fallback Behavior

The app should never sit silently forever.

- During Qwen extraction, the notes panel should show progress updates.
- If Qwen exceeds the configured timeout, the app should render transcript-grounded fallback notes.
- If Qwen returns invalid JSON, the app should render fallback notes and record the fallback reason in diagnostics.
- If the user clicks `Cancel Notes`, the app should stop the Genie process and render fallback notes.

## Privacy Checks

- Disable Wi-Fi if the demo needs a visible offline proof.
- Confirm transcript and notes still work with local assets.
- Confirm no browser or cloud service is required during record, transcribe, summarize, Q&A, or export.
