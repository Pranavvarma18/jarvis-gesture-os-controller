# JARVIS OS 2.0 Upgrade

This package is designed to be copied into your existing project:
`C:\PROJECTS\gesture-os-controller`

## What's included
- `app.py`: dashboard + gesture controller + wake-word listener integration
- `src/voice.py`: local "Hey Jarvis" wake-word detection; online speech transcription
- `src/commands.py`: flexible phrase matching and allowlisted desktop skills
- `src/pinch.py`: smoothed pinch detector with hysteresis and frame confirmation
- `requirements-jarvis.txt`: additional/known dependency pins
- `src/motion.py` and `src/profiles.py` are imported from your existing project.
- `src/gestures.py` and `src/actions.py` are also imported from your existing project.

## 1. Back up first
Copy your current `app.py` to `app_backup.py` before replacing it.

## 2. Copy files
Extract this archive into the project root and allow the included files to replace:
- `app.py`
- `src/__init__.py`
- `src/voice.py`

Add:
- `src/commands.py`
- `src/pinch.py`

Keep your working `src/gestures.py`, `src/actions.py`, `src/motion.py`, and `src/profiles.py`.

## 3. Install packages
In PowerShell, from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-jarvis.txt
```

Download the openWakeWord models once:

```powershell
.\.venv\Scripts\python.exe -c "from openwakeword.utils import download_models; download_models()"
```

## 4. Launch
```powershell
.\.venv\Scripts\python.exe app.py
```

The first startup can take longer while the local wake-word model loads. Say "Hey Jarvis", pause briefly, then say your command. Wake-word detection is local; transcription uses Google's online speech recognition and therefore needs internet.

## Commands currently supported
- "Hey Jarvis, open browser"
- "Hey Jarvis, search for MediaPipe hand tracking"
- "Hey Jarvis, go to github.com"
- "Hey Jarvis, open Notepad / Calculator / Paint / File Explorer / VS Code"
- "Hey Jarvis, pause music / next song / previous song"
- "Hey Jarvis, volume up / volume down / mute sound"
- "Hey Jarvis, next tab / previous tab"
- "Hey Jarvis, next slide / previous slide"
- "Hey Jarvis, scroll up / scroll down"
- "Hey Jarvis, switch to browser / media / presentation / accessibility"
- "Hey Jarvis, emergency stop"
- "Hey Jarvis, type text followed by the text to type"

Only explicitly implemented skills are executed. Unknown requests are not converted into arbitrary terminal commands.

## If the wake word doesn't trigger
- Confirm Windows microphone permission is enabled.
- Use "Hey Jarvis" clearly and pause briefly before the command.
- Adjust `threshold=0.48` in `app.py` when creating `WakeWordListener`.
  - Lower (e.g. 0.40): more sensitive, more false activations.
  - Higher (e.g. 0.60): fewer false activations, may miss your voice.
- Check that no other app has exclusive microphone access.

## Pinch tuning
`src/pinch.py` defaults:
- start ratio 0.30
- release ratio 0.48
- confirm 3 frames
- release 3 frames

The camera HUD displays the current pinch ratio. Pinch when the ratio drops below the start threshold; open fingers until it rises above the release threshold. If the ratio never falls below 0.30, try 0.34. If false clicks occur, try 0.25.

## Safety notes
- The voice listener uses a microphone continuously for local wake-word detection.
- After wake-word activation, speech transcription is sent to Google's recognition service.
- `type text ...` types into the currently focused application. Make sure the correct app has focus.
- Desktop actions are allowlisted; this project does not execute arbitrary shell commands.
- Emergency stop disables this app's controls, but cannot undo an OS action already sent.
