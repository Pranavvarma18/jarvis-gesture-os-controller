"""Hands-free 'Hey Jarvis' listener.

Wake-word detection runs locally using openWakeWord. The follow-up speech
is transcribed with Google's online SpeechRecognition service.
"""

import queue
import threading
import time
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from openwakeword.model import Model


class WakeWordListener(threading.Thread):
    def __init__(self, event_queue, stop_event, threshold=0.48):
        super().__init__(daemon=True)
        self.events = event_queue
        self.stop_event = stop_event
        self.threshold = threshold
        self.audio_queue = queue.Queue(maxsize=80)
        self.recognizer = sr.Recognizer()

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.events.put(("voice_status", f"Microphone: {status}"))
        try:
            self.audio_queue.put_nowait(indata.copy().reshape(-1))
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(indata.copy().reshape(-1))
            except queue.Empty:
                pass

    @staticmethod
    def _rms(audio):
        if len(audio) == 0:
            return 0.0
        samples = audio.astype(np.float32)
        return float(np.sqrt(np.mean(samples * samples)))

    def _capture_command(self):
        """Capture speech until silence follows the command."""
        chunks = []
        started = False
        silence_seconds = 0.0
        total_seconds = 0.0
        self.events.put(("voice_status", "Listening for command..."))

        while not self.stop_event.is_set() and total_seconds < 8.0:
            try:
                chunk = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            chunks.append(chunk)
            energy = self._rms(chunk)
            duration = len(chunk) / 16000.0
            total_seconds += duration

            if energy > 240:
                started = True
                silence_seconds = 0.0
            elif started:
                silence_seconds += duration

            if started and silence_seconds >= 0.85 and total_seconds >= 0.65:
                break

        if not chunks or not started:
            return None

        audio = np.concatenate(chunks).astype(np.int16).tobytes()
        return sr.AudioData(audio, 16000, 2)

    def run(self):
        self.events.put(("voice_status", "Loading local wake-word model..."))
        try:
            model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        except Exception as exc:
            self.events.put(("voice_error", f"Wake-word model failed: {exc}"))
            return

        self.events.put(("voice_status", 'Listening for "Hey Jarvis"...'))
        last_trigger = 0.0

        try:
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=1280,  # 80 ms frames
                callback=self._callback,
            ):
                while not self.stop_event.is_set():
                    try:
                        chunk = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    prediction = model.predict(chunk)
                    score = max(
                        [float(value) for value in prediction.values()],
                        default=0.0,
                    )
                    self.events.put(("wake_score", score))

                    now = time.time()
                    if score >= self.threshold and now - last_trigger > 2.5:
                        last_trigger = now
                        # Clear buffered audio so the wake phrase isn't transcribed.
                        while not self.audio_queue.empty():
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                break

                        self.events.put(("wake_detected", score))
                        audio = self._capture_command()
                        if audio is None:
                            self.events.put(("voice_error", "I heard the wake word, but no command followed."))
                            self.events.put(("voice_status", 'Listening for "Hey Jarvis"...'))
                            continue

                        self.events.put(("voice_status", "Transcribing command..."))
                        try:
                            transcript = self.recognizer.recognize_google(audio, language="en-IN")
                            self.events.put(("voice_text", transcript))
                        except sr.UnknownValueError:
                            self.events.put(("voice_error", "I couldn't understand that. Try speaking clearly."))
                        except sr.RequestError:
                            self.events.put(("voice_error", "Speech transcription service unavailable; check internet."))
                        self.events.put(("voice_status", 'Listening for "Hey Jarvis"...'))

        except Exception as exc:
            self.events.put(("voice_error", f"Voice listener stopped: {exc}"))
