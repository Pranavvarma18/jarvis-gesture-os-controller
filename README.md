# JARVIS Gesture OS Controller

A Python-based, webcam-powered desktop control system that uses real-time hand tracking and custom gestures to interact with a Windows computer.

The project combines computer vision, gesture recognition, mouse and keyboard automation, and an extensible architecture for AI voice-assistant integration.

## Features

- **Real-time hand tracking:** Detect and track hand landmarks using OpenCV and MediaPipe.
- **Gesture-based interaction:** Map hand poses to desktop actions.
- **Air mouse:** Control cursor movement using hand motion.
- **Pinch-to-click:** Use thumb–index finger distance to trigger mouse interactions.
- **Desktop shortcuts:** Support gesture-driven scrolling, browser navigation, and media controls.
- **Customizable controls:** Tune gesture thresholds, confirmation frames, and action mappings.
- **Testing:** Automated tests for supported gesture and pinch-detection behavior.
- **Voice-assistant integration:** Designed to work alongside the broader JARVIS assistant project.

## Technology Stack

- Python
- OpenCV
- MediaPipe
- NumPy
- PyAutoGUI
- pytest

## Project Structure

```text
gesture-os-controller/
├── app.py
├── src/
├── tests/
├── diagnostics/
├── requirements.txt
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Windows 10 or Windows 11
- Python version compatible with the installed dependencies
- Git
- A working webcam

### 1. Clone the repository

```bash
git clone https://github.com/Pranavvarma18/jarvis-gesture-os-controller.git
cd jarvis-gesture-os-controller
```

### 2. Create a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Dependency compatibility should be verified for your Python version and operating system.

### 4. Run the application

```powershell
python app.py
```

Allow webcam access if Windows requests permission.

### 5. Run the tests

```powershell
python -m pytest tests -q
```

Review any failing tests before relying on the corresponding feature.

## Safety Notes

- Review the gesture-to-action mappings before use.
- Mouse and keyboard automation may affect whichever application is currently focused.
- Keep the emergency-stop control accessible.
- Do not commit API keys, passwords, personal recordings, or other sensitive data.
- Use a controlled environment when testing automated mouse and keyboard actions.

## Current Status

This project is under active development. Gesture accuracy, click responsiveness, and application compatibility depend on lighting, camera placement, hardware, and software configuration.

## Future Improvements

- More reliable pinch detection and drag-and-drop
- Neutral-pose rearming and improved accidental-trigger prevention
- Gesture calibration and performance measurements
- Improved gesture classification and automated regression testing
- Deeper integration between voice commands and gesture controls

## Author

**Pranav Varma Alluri**

GitHub: [@Pranavvarma18](https://github.com/Pranavvarma18)

## License

A license has not yet been selected. Please check the repository's licensing terms before reusing or redistributing this project.