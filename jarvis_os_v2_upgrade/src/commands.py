"""Natural-language command routing to explicit, allowlisted desktop skills."""

import os
import re
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import pyautogui


# Extend this map with applications installed on your own computer.
APP_ALLOWLIST = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "command prompt": ["cmd.exe"],
    "vscode": ["code"],
    "visual studio code": ["code"],
}


def normalize(text):
    return re.sub(r"\s+", " ", text.lower().strip())


def _open_url_or_search(text):
    value = text.strip()
    if not value:
        return "Tell me what website or topic to open."

    # Explicit URLs only; otherwise search the phrase.
    if re.match(r"^https?://", value, re.I):
        url = value
    elif re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", value, re.I) and " " not in value:
        url = "https://" + value
    else:
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(value)

    webbrowser.open(url)
    return f"Opened: {value}"


def execute_voice_command(raw_text, app):
    """
    Execute supported intents. Unknown requests are rejected safely.
    'app' is the dashboard/controller instance.
    """
    text = normalize(raw_text)
    if not text:
        return "I didn't receive a command."

    # Controller safety commands are always available.
    if any(phrase in text for phrase in (
        "emergency stop", "stop all controls", "disable controls",
        "stop jarvis controls", "shut down control",
    )):
        app.emergency_stop()
        return "Emergency stop activated."

    if text in ("enable controls", "activate controls", "enable jarvis controls"):
        app.enable_controls()
        return "Controls enabled. Show an open palm to arm gestures."

    # Profiles
    profiles = {
        "browser": "Browser",
        "media": "Media",
        "presentation": "Presentation",
        "accessibility": "Accessibility",
    }
    for keyword, profile in profiles.items():
        if text in (f"{keyword} mode", f"switch to {keyword}", f"activate {keyword} mode"):
            app.set_profile(profile)
            return f"{profile} profile activated."

    # Browser/search commands
    for prefix in ("search the web for ", "search for ", "google ", "look up "):
        if text.startswith(prefix):
            return _open_url_or_search(raw_text[len(prefix):])

    for prefix in ("open website ", "open site ", "go to ", "navigate to "):
        if text.startswith(prefix):
            return _open_url_or_search(raw_text[len(prefix):])

    if text in ("open browser", "launch browser", "start browser", "open google"):
        webbrowser.open("https://www.google.com")
        return "Opened your browser."

    # Launch only named, allowlisted applications.
    for name, command in APP_ALLOWLIST.items():
        if text in (f"open {name}", f"launch {name}", f"start {name}"):
            try:
                subprocess.Popen(command)
                return f"Launching {name}."
            except Exception as exc:
                return f"Could not launch {name}: {exc}"

    # Common media/browser actions
    if any(p in text for p in ("pause music", "play music", "play pause", "toggle playback", "pause video", "resume video")):
        pyautogui.press("playpause")
        return "Toggled playback."

    if any(p in text for p in ("next track", "next song", "skip song", "next music")):
        pyautogui.press("nexttrack")
        return "Next track."

    if any(p in text for p in ("previous track", "previous song", "go back a song")):
        pyautogui.press("prevtrack")
        return "Previous track."

    if any(p in text for p in ("mute volume", "mute sound", "toggle mute")):
        pyautogui.press("volumemute")
        return "Toggled mute."

    if any(p in text for p in ("volume up", "increase volume", "make it louder", "turn it up")):
        pyautogui.press("volumeup", presses=3, interval=0.05)
        return "Volume increased."

    if any(p in text for p in ("volume down", "decrease volume", "make it quieter", "turn it down")):
        pyautogui.press("volumedown", presses=3, interval=0.05)
        return "Volume decreased."

    if any(p in text for p in ("next tab", "switch tab right")):
        pyautogui.hotkey("ctrl", "tab")
        return "Switched to next tab."

    if any(p in text for p in ("previous tab", "switch tab left", "last tab")):
        pyautogui.hotkey("ctrl", "shift", "tab")
        return "Switched to previous tab."

    if any(p in text for p in ("next slide", "advance slide", "next presentation slide")):
        pyautogui.press("right")
        return "Next slide."

    if any(p in text for p in ("previous slide", "go back a slide", "previous presentation slide")):
        pyautogui.press("left")
        return "Previous slide."

    if text in ("scroll up", "page up"):
        pyautogui.scroll(5)
        return "Scrolled up."

    if text in ("scroll down", "page down"):
        pyautogui.scroll(-5)
        return "Scrolled down."

    # Deliberate text-entry command. The text is typed into the focused app.
    if text.startswith("type text "):
        payload = raw_text.strip()[len("type text "):]
        if not payload:
            return "Tell me what text to type."
        pyautogui.write(payload, interval=0.015)
        return "Typed the requested text into the focused application."

    # No arbitrary shell commands or destructive actions.
    return (
        "I don't have a skill for that request yet. "
        "I haven't executed it. Add a dedicated skill for this action."
    )
