JARVIS FINAL UPGRADE — REPLACEMENT PACKAGE

Copy app.py into the project root, then replace the files inside src/ with the matching files in this package.
Keep your existing .venv, model downloads, and other project files.

Install any missing voice dependencies in PowerShell from the project root:
  .\.venv\Scripts\python.exe -m pip install -r requirements-jarvis-final.txt

Compile check:
  .\.venv\Scripts\python.exe -m compileall -q app.py src

Run:
  .\.venv\Scripts\python.exe app.py

Wake word: Hey Jarvis. ESC interrupts speech. E enables/disables controls; M toggles air mouse; X emergency stop; Q quits.
Screen OCR is optional. For OCR, install Tesseract OCR separately and `pytesseract` in the venv. Without it, active-window title awareness still works.
Ollama remains the primary conversational/planning model; if it is unavailable, JARVIS gives a deterministic offline fallback and keeps direct command skills available.
WhatsApp sending still requires the explicit confirmation dialog. Review recipient and message before approving.
