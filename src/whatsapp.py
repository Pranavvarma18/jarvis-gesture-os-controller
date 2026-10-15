"""WhatsApp Web draft and explicit-confirmation helpers for Windows JARVIS.

This is browser UI automation, not an official WhatsApp API. The user must
review the recipient and exact message in the confirmation dialog. After they
approve, the helper sends Enter only if it can focus a window titled WhatsApp.
"""

import ctypes
import os
import time
import urllib.parse
import webbrowser

import pyautogui


def normalize_phone(phone):
    """Return digits-only international number; reject ambiguous/local numbers."""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    # Require an international-style number with country code; do not guess it.
    if not 11 <= len(digits) <= 15:
        raise ValueError(
            "Use the full international phone number, including country code "
            "(for example, +91 followed by the number)."
        )
    return digits


def open_whatsapp_draft(phone, message):
    """Open WhatsApp Web with the recipient and message prefilled."""
    phone = normalize_phone(phone)
    message = str(message).strip()
    if not message:
        raise ValueError("The message cannot be empty.")
    if len(message) > 1500:
        raise ValueError("Keep WhatsApp messages to 1500 characters or fewer for this voice workflow.")
    url = "https://web.whatsapp.com/send?phone={}&text={}".format(
        phone, urllib.parse.quote(message, safe="")
    )
    opened = webbrowser.open(url, new=2)
    if not opened:
        raise RuntimeError("Windows did not confirm that it opened WhatsApp Web.")
    return phone


def send_if_whatsapp_window_focused():
    """Focus a visible WhatsApp-titled Windows window and press Enter.

    Fail closed when a WhatsApp window cannot be identified. This still depends
    on WhatsApp Web being logged in and the draft having loaded correctly.
    """
    if os.name != "nt":
        return False, "Automatic sending is supported only on Windows. The draft remains open; click Send manually."

    user32 = ctypes.windll.user32
    matches = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if "whatsapp" in title.lower():
            matches.append((hwnd, title))
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
    except Exception as exc:
        return False, "I couldn't safely identify the WhatsApp window. The draft remains open; click Send manually."

    if not matches:
        return False, "I couldn't verify a WhatsApp window. The draft remains open; click Send manually."

    # Prefer a title that is simply WhatsApp or contains WhatsApp and a browser name.
    hwnd, title = matches[0]
    try:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.7)
        foreground = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(foreground)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(foreground, buffer, length + 1)
        active_title = buffer.value.strip()
        if foreground != hwnd or "whatsapp" not in active_title.lower():
            return False, "Windows would not focus WhatsApp safely. The draft remains open; click Send manually."
        pyautogui.press("enter")
        time.sleep(0.35)
        return True, "JARVIS pressed Enter in the focused WhatsApp window. Check WhatsApp to verify delivery."
    except Exception:
        return False, "I couldn't send safely. The draft remains open; click Send manually."
