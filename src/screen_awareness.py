"""Best-effort Windows foreground-window and visible-text awareness."""
import os


def get_screen_context(max_chars=1800):
    """Return active window title and optional OCR text; never raises to caller."""
    title = "Unknown window"
    try:
        if os.name == "nt":
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip() or "Untitled window"
    except Exception:
        pass

    lines = [f"Active window: {title}"]
    # OCR is optional: if Tesseract is installed/configured, include a short text sample.
    try:
        import pyautogui
        import pytesseract
        image = pyautogui.screenshot()
        visible_text = " ".join(pytesseract.image_to_string(image).split())
        if visible_text:
            lines.append("Visible screen text (OCR, may be imperfect): " + visible_text[:1200])
    except Exception:
        pass
    return "\n".join(lines)[:max_chars]
