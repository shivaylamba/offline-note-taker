# Offline Note Taker

A Windows desktop app for private, offline meeting notes on Snapdragon X / Qualcomm NPU machines.

The app records or imports meeting audio, transcribes it locally with Qualcomm AI Hub Whisper Windows, generates structured notes with Qwen3-4B through Qualcomm Genie / QAIRT, supports transcript-grounded Q&A, and exports the results without sending audio or text to the cloud.

## What It Does

- Records microphone audio locally.
- Imports `.wav`, `.mp3`, `.m4a`, and `.flac` files.
- Runs Whisper-Base through Qualcomm AI Hub's Whisper Windows app on Snapdragon NPU.
- Shows the transcript as soon as speech-to-text completes.
- Runs Qwen3-4B locally through Genie for structured meeting notes.
- Extracts summaries, important points, decisions, action items, owners, deadlines, risks, blockers, and evidence.
- Answers questions from the transcript and generated notes.
- Exports Markdown, TXT, JSON, SRT, and VTT.
- Keeps all audio, transcripts, model execution, notes, and exports local.

## Architecture

```text
Microphone / Audio File
        ->
Audio Metadata + WAV Recording
        ->
Qualcomm AI Hub Whisper Windows / Whisper-Base
        ->
Timestamped Transcript
        ->
Transcript Cleanup + Chunking
        ->
Qwen3-4B Genie / QAIRT on Snapdragon X Elite
        ->
Structured Meeting Notes + Q&A
        ->
Local Exports
```

The current production path is:

- **ASR:** Qualcomm AI Hub Whisper Windows app with Whisper-Base ONNX/QNN assets.
- **LLM:** Qualcomm Qwen3-4B ready-made Snapdragon X Elite Genie bundle with QAIRT 2.45.x.
- **Fallback:** deterministic transcript-grounded extraction if the local LLM output is invalid or times out.

ExecuTorch is kept in the project guidance as a future PyTorch-native runtime path, but the runnable MVP uses the practical Qualcomm AI Hub Windows samples and Genie path.

## Current Status

This is a runnable MVP, not a packaged installer.

Working locally:

- Python Qt desktop UI.
- Audio recording.
- Audio import validation.
- Qualcomm Whisper Windows runner hook.
- Qwen3-4B Genie runner hook.
- Transcript-first UI flow.
- Structured JSON notes parsing from Qwen.
- Progress updates during local LLM extraction.
- Timeout fallback if Qwen takes too long.
- Q&A over generated action items and transcript evidence.
- Export writers.
- Unit test coverage for chunking, export formats, Q&A, and summary extraction behavior.

Large runtime assets are intentionally ignored by Git:

- `external/`
- `models/`
- `recordings/`
- `exports/`
- `logs/`

## Repository Layout

```text
.
+-- AGENTS.md
+-- README.md
+-- docs/
|   +-- aihub_setup.md
+-- scripts/
|   +-- setup_qairt_245.ps1
|   +-- setup_qualcomm_whisper_windows.ps1
|   +-- setup_qwen3_4b_genie.ps1
+-- src/
|   +-- offline_meeting_notes/
|       +-- audio.py
|       +-- transcription.py
|       +-- summarization.py
|       +-- qa.py
|       +-- gui.py
|       +-- pipeline.py
|       +-- exporters.py
+-- tests/
```

## Requirements

- Windows on ARM / Snapdragon X class machine for the Qualcomm NPU path.
- Python 3.12 for the app.
- Python 3.11 for the Qualcomm Whisper Windows sample environment.
- Qualcomm AI Hub access for model assets.
- Qualcomm AI Runtime / QAIRT 2.45.x for the Qwen3-4B Genie bundle.
- A working microphone if using recording.

The app can run its UI and test suite without the Qualcomm model assets, but real transcription and local LLM notes require the runtime setup below.

## Install

From the repository root:

```powershell
python -m pip install -e ".[gui,dev]"
```

If PowerShell does not recognize `offline-note-taker` after install, either use
`python -m offline_meeting_notes ...` or add the Python user Scripts folder to
`PATH`. On Windows ARM64 that is commonly:

```powershell
$env:Path += ";$env:APPDATA\Python\Python312-arm64\Scripts"
```

For tests only:

```powershell
python -m pip install -e ".[dev]"
```

## Run

Recommended demo-beta flow:

```powershell
offline-note-taker doctor
offline-note-taker smoke
offline-note-taker
```

Launch the desktop app:

```powershell
python -m offline_meeting_notes
```

or, after installing the package:

```powershell
offline-note-taker
```

Check local Qualcomm runtime configuration:

```powershell
offline-note-taker doctor
```

Run a local CLI smoke test:

```powershell
offline-note-taker smoke
```

Process one audio file from the command line:

```powershell
offline-note-taker process --audio "C:\path\to\meeting.wav" --export-dir exports
```

## Qualcomm Runtime Setup

Detailed setup notes live in [docs/aihub_setup.md](docs/aihub_setup.md).

### Whisper Windows

Set up the Qualcomm AI Hub Whisper Windows sample:

```powershell
.\scripts\setup_qualcomm_whisper_windows.ps1
```

The app auto-detects the default local setup under `external/ai-hub-apps`.

Override paths only if your assets live somewhere else:

```powershell
$env:OFFLINE_NOTES_WHISPER_APP_DIR = "C:\path\to\ai-hub-apps\apps\whisper_windows_py"
$env:OFFLINE_NOTES_WHISPER_PYTHON = "C:\path\to\python.exe"
$env:OFFLINE_NOTES_WHISPER_ENCODER_PATH = "C:\path\to\HfWhisperEncoder.onnx"
$env:OFFLINE_NOTES_WHISPER_DECODER_PATH = "C:\path\to\HfWhisperDecoder.onnx"
```

References:

- [Qualcomm AI Hub Whisper Windows](https://aihub.qualcomm.com/apps/whisper_windows_py)
- [Qualcomm AI Hub Whisper-Base](https://aihub.qualcomm.com/compute/models/whisper_base)

### QAIRT

Install Qualcomm AI Runtime SDK 2.45.x.

If you have already downloaded the Windows installer, run:

```powershell
.\scripts\setup_qairt_245.ps1
```

Expected default install:

```powershell
$env:QAIRT_HOME = "C:\Qualcomm\AIStack\QAIRT\2.45.0.260326"
$env:Path = "$env:QAIRT_HOME\bin\aarch64-windows-msvc;$env:QAIRT_HOME\lib\aarch64-windows-msvc;$env:Path"
$env:ADSP_LIBRARY_PATH = "$env:QAIRT_HOME\lib\hexagon-v73\unsigned"
```

Qualcomm SDK downloads may require Qualcomm Software Center access. An AI Hub API token is not the same thing as SDK download authorization.

### Qwen3-4B Genie

Download and prepare the ready-made Qwen3-4B Snapdragon X Elite Genie bundle:

```powershell
.\scripts\setup_qwen3_4b_genie.ps1
```

The expected local bundle contains:

```text
genie_config.json
tokenizer.json
qwen3_4b_w4a16_part_1_of_4.bin
qwen3_4b_w4a16_part_2_of_4.bin
qwen3_4b_w4a16_part_3_of_4.bin
qwen3_4b_w4a16_part_4_of_4.bin
```

Override the config path only if needed:

```powershell
$env:OFFLINE_NOTES_QWEN3_GENIE_CONFIG = "C:\path\to\genie_config.json"
```

References:

- [Qualcomm AI Hub Qwen3-4B](https://aihub.qualcomm.com/models/qwen3_4b)
- [Qualcomm Qwen3-4B Hugging Face model](https://huggingface.co/qualcomm/Qwen3-4B)
- [Qualcomm LLM on Genie tutorial](https://github.com/qualcomm/ai-hub-apps/tree/main/tutorials/llm_on_genie)

## How Notes Are Generated

The app follows a transcript-first UX:

1. Whisper finishes and the transcript appears immediately.
2. Qwen3-4B runs locally on Genie / QAIRT.
3. The app requests compact structured JSON for:
   - summary
   - important points
   - decisions
   - action items
   - owners
   - deadlines
   - evidence
   - open questions
   - risks and blockers
4. The parser validates the JSON, repairs common truncated-output cases, and rejects placeholder values.
5. If Qwen fails or times out, deterministic local extraction produces grounded fallback notes.

The app does not hardcode names such as `Simon`, `Jack`, or `Sam`. Those names only appear in tests as sample transcript content.

## Runtime Check And Logs

The demo beta includes a runtime doctor in both CLI and GUI form.

The doctor validates:

- Whisper Windows app and `demo.py`
- Whisper Python environment
- Whisper encoder/decoder ONNX files
- QAIRT 2.45.x
- `genie-t2t-run.exe`
- Qwen3 Genie config and model parts
- `ADSP_LIBRARY_PATH`
- NPU device availability when Windows exposes it

Run logs are stored locally under `logs/` and are ignored by Git. Logs include audio duration, Whisper backend/latency, Qwen backend/latency, fallback reason, and export paths. No telemetry is sent anywhere.

## Exports

The export action writes:

```text
meeting_transcript.txt
meeting_transcript.srt
meeting_transcript.vtt
meeting_notes.md
meeting_summary.json
```

Exports are written locally to the folder selected in the app.

## Test

```powershell
python -m pytest -p no:cacheprovider
```

Current coverage includes:

- audio sample creation
- transcript chunking
- timestamp-preserving exports
- Q&A behavior
- action item extraction
- Qwen JSON parsing and validation
- fallback behavior

## Privacy

The project is designed for offline operation:

- No cloud transcription.
- No cloud summarization.
- No telemetry.
- No uploading audio.
- No uploading transcripts.
- Model outputs remain on device.

## Troubleshooting

If the app says the microphone is unavailable:

- Confirm Windows microphone permissions.
- Confirm the machine has an enabled input device.
- Try uploading a WAV file instead.

If the transcript appears but notes take time:

- Qwen3-4B is running through Genie on the NPU.
- The app shows progress messages while extraction runs.
- If Qwen takes too long, the app falls back to transcript-grounded notes.
- Use `Cancel Notes` to stop a long notes run and render fallback notes.

If Qwen does not run:

- Confirm `QAIRT_HOME`.
- Confirm `ADSP_LIBRARY_PATH`.
- Confirm `genie-t2t-run.exe` exists under QAIRT.
- Confirm the Qwen3-4B Genie bundle matches QAIRT 2.45.x.

For live demo preparation, use [docs/demo_checklist.md](docs/demo_checklist.md).

## License

MIT
