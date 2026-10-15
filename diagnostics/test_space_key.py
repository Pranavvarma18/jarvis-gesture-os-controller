
"""Diagnostic: test whether PyAutoGUI can send a Space keypress."""

import time

import pyautogui

pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True


def main():
    print("\n=== SPACE KEY DIAGNOSTIC ===")
    print("1. Open a YouTube video or Notepad.")
    print("2. You have 5 seconds to focus the target window.")
    print("3. This script will send ONE Space keypress.")
    print("Move the mouse to the top-left corner to abort.\n")

    for remaining in range(5, 0, -1):
        print(f"Sending Space in {remaining}...")
        time.sleep(1)

    try:
        print("Sending Space now...")
        pyautogui.press("space")
        print("RESULT: PyAutoGUI sent the Space key without an exception.")

    except pyautogui.FailSafeException:
        print("RESULT: Aborted by PyAutoGUI's safety mechanism.")

    except Exception as exc:
        print(f"RESULT: ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
