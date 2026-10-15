"""Threaded Windows SAPI speech with ordered streaming and interruption."""
import queue
import threading


class SpeechOutput:
    def __init__(self, on_error=None, rate=185, volume=1.0):
        self.on_error = on_error
        self.rate = int(rate)
        self.volume = max(0.0, min(1.0, float(volume)))
        self._queue = queue.Queue()
        self._closed = threading.Event()
        self._engine = None
        self._engine_lock = threading.RLock()
        self._active_pause_events = set()
        self._thread = threading.Thread(target=self._run, name="JarvisSpeechOutput", daemon=True)
        self._thread.start()

    def _report_error(self, message):
        if self.on_error:
            try: self.on_error(f"Text-to-speech: {message}")
            except Exception: pass

    @staticmethod
    def _release(pause_event):
        if pause_event is not None: pause_event.clear()

    def speak(self, text, pause_event=None):
        text = str(text).strip()
        if self._closed.is_set() or not text:
            self._release(pause_event); return
        if pause_event is not None:
            pause_event.set(); self._active_pause_events.add(pause_event)
        self._queue.put(("speak", text, pause_event))

    def begin_stream(self, pause_event=None):
        if self._closed.is_set(): return
        if pause_event is not None:
            pause_event.set(); self._active_pause_events.add(pause_event)
        self._queue.put(("stream_begin", "", pause_event))

    def speak_stream_chunk(self, text, pause_event=None):
        text = str(text).strip()
        if self._closed.is_set() or not text: return
        if pause_event is not None:
            pause_event.set(); self._active_pause_events.add(pause_event)
        self._queue.put(("stream_chunk", text, pause_event))

    def end_stream(self, pause_event=None):
        if self._closed.is_set(): self._release(pause_event); return
        self._queue.put(("stream_end", "", pause_event))

    def interrupt(self):
        """Stop current speech, discard queued chunks, and resume wake listening."""
        try:
            with self._engine_lock:
                if self._engine is not None:
                    self._engine.stop()
        except Exception:
            pass
        while True:
            try: self._queue.get_nowait()
            except queue.Empty: break
        for event in list(self._active_pause_events):
            self._release(event)
        self._active_pause_events.clear()

    def _run(self):
        engine = None
        try:
            import pyttsx3
            engine = pyttsx3.init("sapi5")
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)
            with self._engine_lock: self._engine = engine
        except Exception as exc:
            self._report_error(f"Could not initialize Windows speech: {exc}")

        while True:
            item = self._queue.get()
            if item is None: break
            kind, text, pause_event = item
            if kind == "stream_begin": continue
            if kind == "stream_end":
                self._release(pause_event)
                if pause_event in self._active_pause_events: self._active_pause_events.discard(pause_event)
                continue
            try:
                if engine is None:
                    self._report_error("Speech engine unavailable; response remains in the activity log.")
                else:
                    engine.say(text)
                    engine.runAndWait()
            except Exception as exc:
                self._report_error(str(exc))
            finally:
                if kind == "speak":
                    self._release(pause_event)
                    if pause_event in self._active_pause_events: self._active_pause_events.discard(pause_event)
        if engine is not None:
            try: engine.stop()
            except Exception: pass

    def close(self):
        if self._closed.is_set(): return
        self._closed.set(); self.interrupt(); self._queue.put(None)
