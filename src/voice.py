
"""Diagnostic Hey Jarvis wake-word listener for Windows.

Wake-word detection: local openWakeWord model.
Speech-to-text: Google's online SpeechRecognition service.
Expected by app.py: WakeWordListener(event_queue, stop_event).
"""

import queue
import threading
import time

import numpy as np
import sounddevice as sd
import speech_recognition as sr
from openwakeword.model import Model


SAMPLE_RATE = 16000
FRAME_SIZE = 1280
WAKE_THRESHOLD = 0.30


class WakeWordListener(threading.Thread):
    def __init__(self, event_queue, stop_event, threshold=WAKE_THRESHOLD, pause_event=None):
        super().__init__(daemon=True)
        self.events = event_queue
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.threshold = float(threshold)
        self.audio_queue = queue.Queue(maxsize=100)
        self.recognizer = sr.Recognizer()

    def _status(self, message):
        print("[JARVIS VOICE]", message, flush=True)
        self.events.put(("voice_status", message))

    def _error(self, message):
        print("[JARVIS VOICE ERROR]", message, flush=True)
        self.events.put(("voice_error", message))

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.events.put(("voice_status", f"Microphone warning: {status}"))

        # InputStream is configured for int16 mono audio.
        frame = np.asarray(indata[:, 0], dtype=np.int16).copy()

        try:
            self.audio_queue.put_nowait(frame)
        except queue.Full:
            # Discard the oldest frame if processing falls behind.
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self.audio_queue.put_nowait(frame)
            except queue.Full:
                pass

    @staticmethod
    def _rms(frame):
        samples = np.asarray(frame, dtype=np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples * samples)))

    @staticmethod
    def _prediction_score(predictions):
        """Return the highest scalar score produced by the model."""
        scores = []

        for value in predictions.values():
            values = np.asarray(value).reshape(-1)
            if values.size:
                scores.append(float(values[-1]))

        return max(scores, default=0.0)

    def _clear_audio_queue(self):
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _capture_command(self):
        """Record speech after the wake phrase until silence."""
        chunks = []
        speech_started = False
        speech_seconds = 0.0
        silence_seconds = 0.0
        total_seconds = 0.0

        self._status("Wake word detected. Speak your command now.")

        # A short grace period lets the user start speaking.
        wait_until = time.monotonic() + 3.0

        while not self.stop_event.is_set() and total_seconds < 8.0:
            if self.pause_event is not None and self.pause_event.is_set():
                self._clear_audio_queue()
                time.sleep(0.05)
                continue
            try:
                frame = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                if not speech_started and time.monotonic() > wait_until:
                    break
                continue

            duration = len(frame) / SAMPLE_RATE
            total_seconds += duration
            energy = self._rms(frame)
            chunks.append(frame)

            # Int16 microphone samples are measured on a 0-32768 scale.
            if energy > 180:
                speech_started = True
                speech_seconds += duration
                silence_seconds = 0.0
            elif speech_started:
                silence_seconds += duration

            if (
                speech_started
                and speech_seconds >= 0.25
                and silence_seconds >= 0.8
            ):
                break

        if not chunks or not speech_started:
            return None

        pcm = np.concatenate(chunks).astype(np.int16)
        return sr.AudioData(pcm.tobytes(), SAMPLE_RATE, 2)

    def run(self):
        self._status("Checking microphone...")

        try:
            input_device = sd.query_devices(kind="input")
            device_name = input_device.get("name", "Default input device")
            self._status(f"Microphone selected: {device_name}")
        except Exception as exc:
            self._error(
                f"No usable default microphone was found: {exc}. "
                "Check Windows microphone permissions and input settings."
            )
            return

        self._status("Loading Hey Jarvis model...")

        try:
            model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
            )
        except Exception as exc:
            self._error(
                f"Could not load the Hey Jarvis model: {exc}. "
                "Run the openWakeWord model download command first."
            )
            return

        self._status(
            f"Wake-word model loaded. Listening for Hey Jarvis "
            f"(threshold={self.threshold:.2f})."
        )

        last_trigger = 0.0
        last_debug = 0.0
        last_score = 0.0
        last_rms = 0.0

        try:
            with sd.InputStream(
                device=None,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SIZE,
                callback=self._audio_callback,
            ):
                while not self.stop_event.is_set():
                    try:
                        frame = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    if len(frame) != FRAME_SIZE:
                        # The model is most reliable with 1280-sample frames.
                        continue

                    # Keep wake-word detection active during TTS for voice barge-in.
                    # A higher threshold reduces (but cannot completely eliminate) speaker echo triggers.
                    speaking_now = self.pause_event is not None and self.pause_event.is_set()
                    last_rms = self._rms(frame)

                    predictions = model.predict(frame)
                    score = self._prediction_score(predictions)
                    last_score = score

                    # app.py already displays this score.
                    self.events.put(("wake_score", score))

                    now = time.monotonic()

                    # Print diagnostics once per second, not every frame.
                    if now - last_debug >= 1.0:
                        print(
                            f"[JARVIS VOICE] "
                            f"mic_RMS={last_rms:.0f}, "
                            f"wake_score={last_score:.3f}, "
                            f"threshold={self.threshold:.2f}",
                            flush=True,
                        )
                        last_debug = now

                    active_threshold = min(0.95, self.threshold + 0.22) if speaking_now else self.threshold
                    if score >= active_threshold and now - last_trigger >= 2.5:
                        last_trigger = now
                        if speaking_now and self.pause_event is not None:
                            self.pause_event.clear()
                            self.events.put(("interrupt_speech", score))
                        self.events.put(("wake_detected", score))

                        # Clear stale frames; the user should speak after
                        # hearing/seeing that the wake word was detected.
                        self._clear_audio_queue()

                        audio = self._capture_command()

                        if audio is None:
                            self._error(
                                "Wake word detected, but no command speech "
                                "was captured. Say Hey Jarvis, pause, "
                                "then speak your command."
                            )
                            self._status(
                                "Listening for Hey Jarvis..."
                            )
                            continue

                        self._status("Transcribing your command...")

                        try:
                            transcript = self.recognizer.recognize_google(
                                audio,
                                language="en-IN",
                            )

                            print(
                                f"[JARVIS HEARD] {transcript}",
                                flush=True,
                            )
                            if self.pause_event is not None:
                                self.pause_event.set()

                            self._clear_audio_queue()
                            self.events.put(("voice_text", transcript))


                        except sr.UnknownValueError:
                            self._error(
                                "Speech was recorded but not understood. "
                                "Speak clearly and try again."
                            )
                        except sr.RequestError as exc:
                            self._error(
                                f"Online speech recognition failed: {exc}. "
                                "Check your internet connection."
                            )

                        self._status("Listening for Hey Jarvis...")

        except Exception as exc:
            self._error(
                f"Microphone listener stopped: {type(exc).__name__}: {exc}"
            )
