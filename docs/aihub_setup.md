# Qualcomm AI Hub Runtime Setup

The app is intended to run:

1. Qualcomm AI Hub Whisper Windows for speech-to-text.
2. Qualcomm Qwen3-4B ready-made Snapdragon X Elite Genie bundle for meeting notes.

## Whisper Windows

Qualcomm's Whisper Windows app demonstrates on-device Whisper speech-to-text with ONNX Runtime and the Snapdragon NPU.

Run:

```powershell
.\scripts\setup_qualcomm_whisper_windows.ps1
```

The script clones Qualcomm's app into `external\ai-hub-apps`, creates a repo-local Python 3.11 environment, installs the Whisper-Base AI Hub package, installs `onnxruntime-qnn`, downloads the precompiled Snapdragon X Elite ONNX/QNN assets, and expands them.

Default paths:

```powershell
C:\Users\Admin\Documents\executorch-voice-agent\external\ai-hub-apps\apps\whisper_windows_py
C:\Users\Admin\Documents\executorch-voice-agent\external\aihub-whisper-venv311\Scripts\python.exe
C:\Users\Admin\Documents\executorch-voice-agent\external\ai-hub-apps\apps\whisper_windows_py\export_assets\whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite\HfWhisperEncoder.onnx
C:\Users\Admin\Documents\executorch-voice-agent\external\ai-hub-apps\apps\whisper_windows_py\export_assets\whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite\HfWhisperDecoder.onnx
```

The app auto-detects those paths. Override only if your assets are somewhere else:

```powershell
$env:OFFLINE_NOTES_WHISPER_APP_DIR = "C:\path\to\ai-hub-apps\apps\whisper_windows_py"
$env:OFFLINE_NOTES_WHISPER_PYTHON = "C:\path\to\python.exe"
$env:OFFLINE_NOTES_WHISPER_ENCODER_PATH = "C:\path\to\HfWhisperEncoder.onnx"
$env:OFFLINE_NOTES_WHISPER_DECODER_PATH = "C:\path\to\HfWhisperDecoder.onnx"
```

## Qwen3-4B Genie

Qualcomm's LLM on Genie tutorial uses Qwen3-4B as the running example. For Snapdragon X Elite, the Qwen3-4B Hugging Face model card publishes ready-made Genie assets, so this project uses that download path instead of exporting huge ONNX split artifacts locally.

Run:

```powershell
.\scripts\setup_qwen3_4b_genie.ps1
```

The script downloads `qwen3_4b-genie-w4a16-qualcomm_snapdragon_x_elite.zip` from Qualcomm public assets and expands it under `models\qwen3_4b\genie_bundle`.

The expected config path is:

```text
C:\Users\Admin\Documents\executorch-voice-agent\models\qwen3_4b\genie_bundle\genie_config.json
```

Set this only if your bundle is somewhere else:

```powershell
$env:OFFLINE_NOTES_QWEN3_GENIE_CONFIG = "C:\path\to\genie_config.json"
```

QAIRT must be available for local Genie execution. Qwen3-4B Snapdragon X Elite ready-made assets are built for QAIRT 2.45.x:

```powershell
$env:QAIRT_HOME = "C:\Qualcomm\AIStack\QAIRT\2.45.0.260326"
$env:Path = "$env:QAIRT_HOME\bin\aarch64-windows-msvc;$env:QAIRT_HOME\lib\aarch64-windows-msvc;$env:Path"
$env:ADSP_LIBRARY_PATH = "$env:QAIRT_HOME\lib\hexagon-v73\unsigned"
```

If local Genie execution fails after export, verify that the QAIRT version matches the generated bundle requirements.

This repo includes a helper that checks for the expected QAIRT 2.45 install and launches the installer if you have already downloaded it:

```powershell
.\scripts\setup_qairt_245.ps1
```

The expected installer name is:

```text
C:\Users\Admin\Downloads\Qualcomm_AI_Runtime_SDK.2.45.0.260326.Windows-AnyCPU.exe
```

Qualcomm Software Center gates SDK downloads behind login/license approval. The AI Hub API token is sufficient for model/API access, but it does not authorize the QAIRT SDK download endpoint.

## References

- https://aihub.qualcomm.com/apps/whisper_windows_py
- https://aihub.qualcomm.com/models/qwen3_4b
- https://huggingface.co/qualcomm/Qwen3-4B
- https://github.com/qualcomm/ai-hub-apps/tree/main/tutorials/llm_on_genie
