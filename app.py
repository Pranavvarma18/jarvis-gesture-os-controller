"""JARVIS OS 2.0 — wake word, gesture control, air mouse and dashboard."""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import re
import cv2
import mediapipe as mp
import pyautogui
from PIL import Image, ImageTk

from src.actions import adjust_volume, execute_action, execute_named_action
from src.commands import execute_voice_command
from src.ai_brain_fast import JarvisAI
from src.agent import IntentRouter
from src.commands import execute_agent_action
from src.whatsapp import open_whatsapp_draft, send_if_whatsapp_window_focused
from src.screen_awareness import get_screen_context
from src.tts import SpeechOutput
from src.gestures import classify_gesture, get_finger_states
from src.motion import MotionDetector
from src.profiles import PROFILES, get_profile_action
from src.pinch import PinchDetector
from src.voice import WakeWordListener


CAMERA_INDEX = 0
FRAME_WIDTH = 960
FRAME_HEIGHT = 540
STABLE_FRAMES = 4
VOLUME_REPEAT_SECONDS = 0.18
ACTION_COOLDOWN_SECONDS = 0.65
VOLUME_GESTURES = {"THREE_FINGERS", "FOUR_FINGERS"}
NEUTRAL_GESTURES = {"OPEN_PALM", "UNKNOWN", "NO HAND"}
MOUSE_SMOOTHING = 0.42
MOUSE_MARGIN = 0.08

DARK = "#0b1220"
PANEL = "#111c2e"
PANEL_LIGHT = "#1a2940"
TEXT = "#e6eefc"
MUTED = "#91a4c3"
CYAN = "#5ee7ff"
GREEN = "#48e0a4"
RED = "#ff637d"
PURPLE = "#a9a0ff"


class JarvisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JARVIS OS 2.0 | Desktop Skills")
        self.root.geometry("1320x850")
        self.root.minsize(1050, 700)
        self.root.configure(bg=DARK)

        self.running = True
        self.controls_enabled = False
        self.mouse_mode = False
        self.armed = False
        self.profile = "Browser"

        self.candidate_gesture = "UNKNOWN"
        self.stable_gesture = "UNKNOWN"
        self.candidate_frames = 0
        self.active_volume_gesture = None
        self.last_volume_time = 0.0
        self.last_action_time = 0.0
        self.last_action = "Starting JARVIS"
        self.action_count = 0
        self.mouse_position = None
        self.motion = MotionDetector()
        self.pinch = PinchDetector()
        self.mouse_button_down = False
        self.events = queue.Queue()
        self.stop_voice = threading.Event()
        # Pause wake-word detection while JARVIS is thinking/speaking, so it
        # does not mistake its own voice for a new command.
        self.voice_pause = threading.Event()
        self.ai = JarvisAI()
        self.intent_router = IntentRouter()
        self.whatsapp_pending = None
        self.whatsapp_pending_lock = threading.Lock()
        self.speech = SpeechOutput(
            on_error=lambda message: self.events.put(("voice_error", message))
        )
        self.voice_status = "Starting wake-word engine"
        self.voice_score = 0.0
        self.fps = 0.0
        self.previous_frame_time = time.time()

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            self.camera.release()
            self.camera = cv2.VideoCapture(CAMERA_INDEX)
        if not self.camera.isOpened():
            raise RuntimeError("Could not open webcam. Check camera permissions.")

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=1,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.65,
        )

        self.build_ui()
        self.root.bind_all("<KeyPress>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.voice_thread = WakeWordListener(
            self.events, self.stop_voice, pause_event=self.voice_pause
        )
        self.voice_thread.start()
        self.root.after(20, self.process_frame)

    def build_ui(self):
        header = tk.Frame(self.root, bg=DARK)
        header.pack(fill="x", padx=18, pady=14)
        tk.Label(header, text="JARVIS", font=("Segoe UI", 27, "bold"),
                 fg=CYAN, bg=DARK).pack(side="left")
        tk.Label(header, text="VOICE • VISION • MOTION • DESKTOP SKILLS",
                 font=("Segoe UI", 10, "bold"), fg=MUTED, bg=DARK).pack(
                     side="left", padx=16, pady=(10, 0))
        self.badge = tk.Label(header, text="● STANDBY", bg=PANEL, fg=RED,
                              padx=12, pady=8, font=("Segoe UI", 10, "bold"))
        self.badge.pack(side="right")

        body = tk.Frame(self.root, bg=DARK)
        body.pack(fill="both", expand=True, padx=18, pady=4)
        left = tk.Frame(body, bg=DARK)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = tk.Frame(body, bg=DARK, width=350)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        camera_card = self.card(left, "LIVE VISION FEED")
        self.camera_label = tk.Label(camera_card, bg="#050a12", fg=MUTED,
                                     text="Initializing camera...")
        self.camera_label.pack(fill="both", expand=True)
        self.vision_line = tk.Label(camera_card, text="Waiting for hand landmarks",
                                    bg=PANEL, fg=TEXT, anchor="w")
        self.vision_line.pack(fill="x", pady=(8, 0))

        profile_card = self.card(right, "CONTROL PROFILE")
        self.profile_var = tk.StringVar(value=self.profile)
        self.profile_combo = ttk.Combobox(
            profile_card, textvariable=self.profile_var,
            values=list(PROFILES.keys()), state="readonly"
        )
        self.profile_combo.pack(fill="x")
        self.profile_combo.bind("<<ComboboxSelected>>",
                                lambda _e: self.set_profile(self.profile_var.get()))
        for i, name in enumerate(PROFILES, 1):
            tk.Button(profile_card, text=f"{i}  {name}",
                      command=lambda n=name: self.set_profile(n),
                      bg=PANEL_LIGHT, fg=TEXT, relief="flat", pady=5).pack(
                          fill="x", pady=2)

        status = self.card(right, "SYSTEM STATUS")
        self.status_controls = self.row(status, "Desktop controls", "DISABLED")
        self.status_mode = self.row(status, "Mode", "Gesture")
        self.status_gesture = self.row(status, "Gesture", "UNKNOWN")
        self.status_motion = self.row(status, "Motion", "None")
        self.status_voice = self.row(status, "Wake word", self.voice_status)
        self.status_action = self.row(status, "Last action", self.last_action)

        buttons = self.card(right, "COMMAND CENTER")
        self.enable_button = self.button(buttons, "ENABLE CONTROLS  [E]",
                                          self.toggle_controls, GREEN)
        self.mouse_button = self.button(buttons, "AIR MOUSE  [M]",
                                         self.toggle_mouse, CYAN)
        self.button(buttons, "EMERGENCY STOP  [X]",
                    self.emergency_stop, RED)
        tk.Label(buttons, text='Say "Hey Jarvis" to speak hands-free',
                 bg=PANEL, fg=PURPLE, wraplength=300,
                 font=("Segoe UI", 9, "bold")).pack(fill="x", pady=6)

        log_card = self.card(right, "ACTIVITY LOG")
        self.log_box = tk.Listbox(log_card, height=9, bg="#080e19", fg=TEXT,
                                  relief="flat", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True)

        tk.Label(self.root, text="E: Controls   M: Air mouse   X: Emergency stop   ESC: Interrupt speech   Q: Quit",
                 bg=DARK, fg=MUTED, font=("Segoe UI", 10)).pack(fill="x", pady=10)

    def card(self, parent, title):
        frame = tk.Frame(parent, bg=PANEL, padx=12, pady=10)
        frame.pack(fill="both" if parent == self.root else "x",
                   expand=(parent != self.root), pady=(0, 10))
        tk.Label(frame, text=title, bg=PANEL, fg=CYAN,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        return frame

    def row(self, parent, name, value):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=name, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        label = tk.Label(row, text=value, bg=PANEL, fg=TEXT,
                         font=("Segoe UI", 9, "bold"), wraplength=180)
        label.pack(side="right")
        return label

    def button(self, parent, text, command, color):
        button = tk.Button(parent, text=text, command=command, bg=PANEL_LIGHT,
                           fg=color, activebackground=color,
                           activeforeground=DARK, relief="flat",
                           font=("Segoe UI", 10, "bold"), pady=8)
        button.pack(fill="x", pady=4)
        return button

    def log(self, message):
        stamp = time.strftime("%H:%M:%S")
        self.last_action = message
        self.log_box.insert(0, f"{stamp}  {message}")
        while self.log_box.size() > 12:
            self.log_box.delete(tk.END)

    def set_profile(self, name):
        if name not in PROFILES:
            return
        self.profile = name
        self.profile_var.set(name)
        self.motion.reset()
        self.log(f"Profile: {name}")

    def _release_mouse_button(self):
        """Never leave the OS mouse button held after a mode switch or tracking loss."""
        if self.mouse_button_down:
            try:
                pyautogui.mouseUp()
            except Exception:
                pass
            self.mouse_button_down = False

    def _reset_pinch(self):
        self._release_mouse_button()
        self.pinch.reset()

    def enable_controls(self):
        self.controls_enabled = True
        self.mouse_mode = False
        self.armed = False
        self.active_volume_gesture = None
        self._reset_pinch()
        self.log("Controls enabled; show open palm to arm")

    def toggle_controls(self):
        if self.controls_enabled:
            self.emergency_stop()
        else:
            self.enable_controls()

    def emergency_stop(self):
        self.controls_enabled = False
        self.mouse_mode = False
        self.armed = False
        self.active_volume_gesture = None
        self.mouse_position = None
        self.motion.reset()
        self._reset_pinch()
        self.log("EMERGENCY STOP — desktop controls disabled")

    def toggle_mouse(self):
        if not self.controls_enabled:
            self.log("Enable controls before starting air mouse")
            return
        self.mouse_mode = not self.mouse_mode
        self.armed = False
        self.active_volume_gesture = None
        self.mouse_position = None
        self._reset_pinch()
        self.log("Air mouse enabled" if self.mouse_mode else "Gesture mode enabled")

    
    def handle_voice(self, text):
        normalized_voice = " ".join(str(text).lower().split())
        if normalized_voice in {"stop speaking", "be quiet", "stop talking", "interrupt", "jarvis stop"}:
            self.speech.interrupt()
            self.voice_pause.clear()
            self.log("Speech interrupted by user")
            return
        self.voice_pause.set()
        self.log(f'Heard: "{text}"')

        if normalized_voice in {"what is on my screen", "what's on my screen", "describe my screen", "what window is open", "which app is open"}:
            screen = get_screen_context()
            self.ai.remember_exchange(text, screen)
            self.log(screen.replace("\n", " | "))
            self.speech.speak(screen, pause_event=self.voice_pause)
            return

        if " ".join(str(text).lower().split()) in {
            "forget our conversation", "clear conversation", "clear chat history",
            "reset conversation memory", "forget conversation history",
        }:
            self.ai.clear_history()
            message = "Conversation memory cleared."
            self.log(message)
            self.speech.speak(message, pause_event=self.voice_pause)
            return

        try:
            result = execute_voice_command(text, self)

            if result is not None:
                self.log(result)
                self.ai.remember_exchange(text, result)

                if result.strip():
                    self.speech.speak(
                         result,
                         pause_event=self.voice_pause, )
                else:
                    self.voice_pause.clear()

                return

            self.log("JARVIS is interpreting the request...")
            threading.Thread(
                target=self._route_request,
                args=(text,),
                name="JarvisIntentRouter",
                daemon=True,
            ).start()

        except pyautogui.FailSafeException:
              self.emergency_stop()
              self.log("PyAutoGUI safety stop triggered")
              self.speech.speak(
            "Safety stop activated.",
            pause_event=self.voice_pause,
        )

        except Exception as exc:
            self.log(f"Voice command error: {exc}")
            self.speech.speak(
            "Sorry, that command failed.",
            pause_event=self.voice_pause,
        )


    def request_whatsapp_message(self, phone, message):
        """Prepare a WhatsApp draft, then ask for explicit GUI confirmation."""
        phone = str(phone).strip()
        message = str(message).strip()
        with self.whatsapp_pending_lock:
            if self.whatsapp_pending is not None:
                return "A WhatsApp message is already awaiting confirmation. Finish or cancel that prompt first."
            pending = {"phone": phone, "message": message, "token": time.time_ns()}
            self.whatsapp_pending = pending

        def prepare():
            try:
                normalized_phone = open_whatsapp_draft(phone, message)
                pending["phone"] = normalized_phone
                # Give WhatsApp Web time to load so the user can inspect the draft.
                time.sleep(5.0)
                self.events.put(("whatsapp_confirm", pending.copy()))
            except Exception as exc:
                with self.whatsapp_pending_lock:
                    if self.whatsapp_pending and self.whatsapp_pending.get("token") == pending["token"]:
                        self.whatsapp_pending = None
                self.events.put(("whatsapp_result", "I couldn't prepare the WhatsApp draft: " + str(exc)))

        threading.Thread(target=prepare, name="JarvisWhatsAppDraft", daemon=True).start()
        return "Preparing the WhatsApp draft. I'll ask you to confirm the exact recipient and message before sending."

    def _confirm_whatsapp_message(self, pending):
        """Run on Tk's UI thread, so the confirmation dialog is reliable."""
        with self.whatsapp_pending_lock:
            current = self.whatsapp_pending
        if not current or current.get("token") != pending.get("token"):
            return
        preview = str(pending.get("message", ""))
        if len(preview) > 1000:
            preview = preview[:1000] + "… [preview shortened]"
        approved = messagebox.askyesno(
            "Confirm WhatsApp message",
            ("WhatsApp draft should now be open.\n\n"
             "Recipient number: +{phone}\n\n"
             "Exact message:\n{message}\n\n"
             "Check the recipient and draft in WhatsApp.\n"
             "Click Yes only if you want JARVIS to press Enter to send it.").format(
                phone=pending.get("phone", ""), message=preview
            ),
            parent=self.root,
            icon="warning",
        )
        if not approved:
            with self.whatsapp_pending_lock:
                if self.whatsapp_pending and self.whatsapp_pending.get("token") == pending.get("token"):
                    self.whatsapp_pending = None
            self.log("WhatsApp send cancelled; nothing was sent by JARVIS.")
            self.speech.speak("Cancelled. I did not send the WhatsApp message.", pause_event=self.voice_pause)
            return

        self.voice_pause.set()
        self.log("WhatsApp send approved by user; verifying the WhatsApp window.")
        threading.Thread(
            target=self._send_confirmed_whatsapp,
            args=(pending.copy(),),
            name="JarvisWhatsAppSend",
            daemon=True,
        ).start()

    def _send_confirmed_whatsapp(self, pending):
        try:
            ok, message = send_if_whatsapp_window_focused()
            if not ok:
                message = "Not sent automatically. " + message
        except Exception as exc:
            message = "Not sent automatically; the WhatsApp draft remains open. " + str(exc)
        finally:
            with self.whatsapp_pending_lock:
                if self.whatsapp_pending and self.whatsapp_pending.get("token") == pending.get("token"):
                    self.whatsapp_pending = None
        self.events.put(("whatsapp_result", message))

    @staticmethod
    def _is_conversation_or_question(text):
        """Fast local routing: avoid an extra LLM call for ordinary conversation."""
        value = " ".join(str(text).lower().strip().split())
        prefixes = (
            "what is ", "what are ", "what was ", "what were ", "what's ", "whats ",
            "why ", "how ", "who ", "when ", "where ", "which ", "is ", "are ",
            "can you explain ", "could you explain ", "explain ", "tell me about ",
            "define ", "compare ", "summarize ", "should i ", "do you think ",
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "thanks", "thank you", "how are you", "who are you", "what can you do",
        )
        if any(value.startswith(p) for p in prefixes if p not in ("hi", "hello", "hey", "thanks", "thank you")):
            return True
        return value in {"hi", "hello", "hey", "thanks", "thank you"} or any(
            value.startswith(p + " ") for p in ("hi", "hello", "hey", "thanks", "thank you")
        )

    def _route_request(self, text):
        """Route conversation or plan a validated desktop action off the UI thread."""
        try:
            if self._is_conversation_or_question(text):
                self._answer_with_ai(text)
                return

            context = self.ai.get_recent_context()
            try:
                context += "\nCURRENT SCREEN CONTEXT (observed, may be incomplete):\n" + get_screen_context()
            except Exception:
                pass
            plan = self.intent_router.route(text, context=context)
            action = plan.get("action", "answer")
            if action == "answer":
                self._answer_with_ai(text)
            else:
                # Keep the original request so the completed action becomes
                # useful context for follow-up commands such as "open that".
                plan["_user_text"] = text
                self.events.put(("agent_action", plan))
        except Exception as exc:
            message = f"I couldn't process that request: {exc}"
            self.events.put(("assistant_response", message))
            self.speech.speak(message, pause_event=self.voice_pause)

    def _execute_agent_plan(self, plan):
        """Execute a bounded action plan; stop on the first failed step."""
        original_request = str(plan.get("_user_text", "")).strip()
        action = str(plan.get("action", "unsupported")).strip().lower()
        steps = plan.get("steps", []) if action == "sequence" else [plan]
        results = []

        try:
            if not isinstance(steps, list) or not 1 <= len(steps) <= 4:
                raise ValueError("The action plan must contain between one and four steps.")

            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    raise ValueError("The action plan contained an invalid step.")
                step_action = str(step.get("action", "unsupported")).strip().lower()
                if step_action in {"answer", "sequence"}:
                    raise ValueError("Nested or conversational steps cannot be executed as desktop actions.")

                outcome = execute_agent_action(step, self)
                if not isinstance(outcome, dict) or "ok" not in outcome or "message" not in outcome:
                    results.append(f"Step {index}: invalid result from the action handler; stopping.")
                    break

                message = str(outcome["message"])
                results.append(f"Step {index} {'completed' if outcome['ok'] else 'failed'}: {message}")
                if not outcome["ok"]:
                    results.append("Stopped the plan after the first failed step; later steps were not run.")
                    break

                # A small gap lets the OS dispatch each operation before the next.
                if index < len(steps):
                    time.sleep(0.25)

            summary = " ".join(results).strip() or "No desktop action was performed."
            if original_request:
                self.ai.remember_exchange(original_request, summary)
            self.events.put(("agent_result", summary))
        except Exception as exc:
            message = f"Action plan failed safely: {exc}"
            if original_request:
                self.ai.remember_exchange(original_request, message)
            self.events.put(("agent_result", message))

    

    def _answer_with_ai(self, text):
        """Stream Ollama output into ordered speech chunks off the UI thread."""
        pause_event = self.voice_pause
        self.speech.begin_stream(pause_event)

        buffer = ""
        queued_any = False

        def queue_sentence(sentence):
            nonlocal queued_any
            sentence = str(sentence).strip()
            if sentence:
                self.speech.speak_stream_chunk(
                    sentence,
                    pause_event=pause_event,
                )
                queued_any = True

        def on_chunk(chunk):
            """Buffer streamed tokens until a sentence or safe chunk is ready."""
            nonlocal buffer

            if not chunk:
                return

            buffer += str(chunk)

            # Emit complete sentences while retaining the unfinished tail.
            parts = re.split(r"(?<=[.!?])\s+", buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    queue_sentence(sentence)
                buffer = parts[-1]

            # Avoid waiting too long if the model produces a long sentence
            # or a response without punctuation.
            while len(buffer) >= 240:
                cut = buffer.rfind(" ", 0, 200)
                if cut < 80:
                    cut = min(200, len(buffer))
                queue_sentence(buffer[:cut])
                buffer = buffer[cut:].lstrip()

        try:
            # Give the conversational model grounded foreground-window context.
            try:
                screen_context = get_screen_context()
            except Exception:
                screen_context = "Screen context unavailable."
            contextual_prompt = (
                "Current Windows screen context (best-effort; OCR can be imperfect):\n"
                + screen_context + "\n\nUser's actual request: " + str(text)
            )
            answer = self.ai.reply(contextual_prompt, on_chunk=on_chunk)
            answer = str(answer or "").strip()

            # Flush any remaining text that did not end in punctuation.
            queue_sentence(buffer)
            buffer = ""

            # Some implementations may return a full answer but fail to call
            # the callback. Speak the returned answer in that case.
            if not queued_any and answer:
                queue_sentence(answer)

            if not queued_any and not answer:
                queue_sentence("I couldn't generate a response for that.")

            self.events.put(("assistant_response", answer or
                             "I couldn't generate a response for that."))

        except Exception as exc:
            # Deterministic offline fallback: do not pretend a model answered.
            queue_sentence(buffer)
            buffer = ""
            try:
                screen = get_screen_context()
                window_line = screen.splitlines()[0] if screen else "Active window unavailable."
            except Exception:
                window_line = "Active window unavailable."
            lowered = str(text).lower().strip()
            if any(k in lowered for k in ("what is on my screen", "what's on my screen", "describe my screen", "which app is open", "what window is open")):
                fallback = window_line + ". My local language model is offline, so I can only report the active window title right now."
            elif any(k in lowered for k in ("hello", "hi jarvis", "hey jarvis", "how are you")):
                fallback = "I'm here. My local language model is unavailable, but direct desktop commands are still available."
            else:
                fallback = "My local AI model is unavailable, so I can't answer that reliably. Direct commands for opening apps, searching websites, media controls, and confirmed WhatsApp drafts remain available."
            try:
                self.ai.remember_exchange(str(text), fallback)
            except Exception:
                pass
            self.events.put(("assistant_response", fallback))
            self.speech.speak_stream_chunk(fallback, pause_event=pause_event)

        finally:
            # FIFO order means the pause is released only after all chunks
            # have finished speaking.
            self.speech.end_stream(pause_event)

    def process_events(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "voice_status":
                self.voice_status = payload
            elif kind == "voice_error":
                self.voice_status = "Needs attention"
                self.log(payload)
            elif kind == "interrupt_speech":
                self.speech.interrupt()
                self.voice_pause.clear()
                self.voice_status = "Voice interruption detected"
                self.log("Voice interruption: listening for the new command")
            elif kind == "wake_detected":
                self.voice_status = "Wake word detected"
                self.log(f"Wake word detected ({float(payload):.2f})")
            elif kind == "wake_score":
                self.voice_score = float(payload)
            elif kind == "voice_text":
                self.voice_status = "Command received"
                self.handle_voice(payload)
            elif kind == "assistant_response":
                self.log(f"JARVIS: {payload}")
                self.voice_status = "Response ready"
            elif kind == "agent_action":
                threading.Thread(
                    target=self._execute_agent_plan,
                    args=(payload,),
                    name="JarvisActionPlan",
                    daemon=True,
                ).start()
            elif kind == "agent_result":
                self.log("JARVIS: " + str(payload))
                self.speech.speak(str(payload), pause_event=self.voice_pause)
            elif kind == "whatsapp_confirm":
                self._confirm_whatsapp_message(payload)
            elif kind == "whatsapp_result":
                self.log("JARVIS: " + str(payload))
                self.speech.speak(str(payload), pause_event=self.voice_pause)

    def move_cursor(self, hand):
        tip = hand.landmark[8]
        sw, sh = pyautogui.size()
        x = max(0.0, min(1.0, (tip.x - MOUSE_MARGIN) / (1 - 2 * MOUSE_MARGIN)))
        y = max(0.0, min(1.0, (tip.y - MOUSE_MARGIN) / (1 - 2 * MOUSE_MARGIN)))
        target = (x * sw, y * sh)
        if self.mouse_position is None:
            smooth = target
        else:
            px, py = self.mouse_position
            smooth = (px + MOUSE_SMOOTHING * (target[0] - px),
                      py + MOUSE_SMOOTHING * (target[1] - py))
        pyautogui.moveTo(int(smooth[0]), int(smooth[1]))
        self.mouse_position = smooth

    def handle_motion(self, x, y, now):
        direction = self.motion.update(x, y, now, enabled=True)
        if not direction:
            return
        self.status_motion.config(text=direction, fg=CYAN)
        action = get_profile_action(self.profile, direction)
        if action:
            result = execute_named_action(action)
            self.action_count += 1
            self.last_action_time = now
            self.log(f"{self.profile} swipe {direction}: {result}")

    def process_frame(self):
        if not self.running:
            return
        self.process_events()

        ok, frame = self.camera.read()
        if not ok:
            self.root.after(100, self.process_frame)
            return

        frame = cv2.flip(frame, 1)
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        result = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        detected = "NO HAND"
        states = {}
        hand = None
        x = y = 0.5

        if result.multi_hand_landmarks:
            hand = result.multi_hand_landmarks[0]
            states = get_finger_states(hand)
            detected = classify_gesture(hand)
            lm = hand.landmark
            indices = (0, 5, 9, 13, 17)
            x = sum(lm[i].x for i in indices) / len(indices)
            y = sum(lm[i].y for i in indices) / len(indices)
            self.mp_drawing.draw_landmarks(frame, hand, self.mp_hands.HAND_CONNECTIONS)

        if detected == self.candidate_gesture:
            self.candidate_frames += 1
        else:
            self.candidate_gesture = detected
            self.candidate_frames = 1
        if self.candidate_frames >= STABLE_FRAMES:
            self.stable_gesture = self.candidate_gesture

        now = time.time()
        dt = now - self.previous_frame_time
        if dt > 0:
            instant = 1.0 / dt
            self.fps = instant if self.fps == 0 else 0.85 * self.fps + 0.15 * instant
        self.previous_frame_time = now

        if not self.controls_enabled:
            self.armed = False
            self.mouse_mode = False
            self.active_volume_gesture = None
            self.mouse_position = None
            self.motion.reset()
            self._reset_pinch()

        elif self.mouse_mode:
            self.armed = False
            self.active_volume_gesture = None
            self.motion.reset()
            if hand is None:
                self.mouse_position = None
                self._reset_pinch()
            else:
                try:
                    self.move_cursor(hand)
                    click_event, ratio, pinch_status = self.pinch.update(hand)
                    if click_event and not self.mouse_button_down:
                        pyautogui.mouseDown()
                        self.mouse_button_down = True
                        self.action_count += 1
                        self.log("Pinch press — release to click, hold to drag")
                    if self.pinch.release_event:
                        self._release_mouse_button()
                        self.log("Pinch released")
                except pyautogui.FailSafeException:
                    self.emergency_stop()
                    self.log("PyAutoGUI safety stop triggered")
                except Exception as exc:
                    self.log(f"Air mouse error: {exc}")

        else:
            self._reset_pinch()
            self.mouse_position = None
            if self.stable_gesture == "OPEN_PALM":
                self.active_volume_gesture = None
                self.armed = True
                self.handle_motion(x, y, now)
            else:
                self.motion.reset()

            if self.active_volume_gesture and self.stable_gesture != self.active_volume_gesture:
                self.active_volume_gesture = None

            if self.stable_gesture in VOLUME_GESTURES:
                if self.active_volume_gesture == self.stable_gesture:
                    if now - self.last_volume_time >= VOLUME_REPEAT_SECONDS:
                        direction = "up" if self.stable_gesture == "THREE_FINGERS" else "down"
                        self.last_action = adjust_volume(direction)
                        self.last_volume_time = now
                        self.action_count += 1
                elif self.armed:
                    direction = "up" if self.stable_gesture == "THREE_FINGERS" else "down"
                    self.last_action = adjust_volume(direction)
                    self.last_volume_time = now
                    self.active_volume_gesture = self.stable_gesture
                    self.armed = False
                    self.action_count += 1
            elif (
                self.armed
                and self.stable_gesture not in NEUTRAL_GESTURES
                and now - self.last_action_time >= ACTION_COOLDOWN_SECONDS
            ):
                try:
                    self.last_action = execute_action(self.stable_gesture, x, y)
                    self.last_action_time = now
                    self.action_count += 1
                    self.armed = False
                    self.log(self.last_action)
                except pyautogui.FailSafeException:
                    self.emergency_stop()

        finger_text = " ".join(
            f"{name[0].upper()}:{'1' if value is True else '0' if value is False else '?'}"
            for name, value in states.items()
        ) or "No hand"
        ratio = self.pinch.smoothed_ratio if self.pinch.smoothed_ratio is not None else 0.0
        lines = [
            f"JARVIS OS 2.0 | {self.profile.upper()}",
            f"Controls: {'ON' if self.controls_enabled else 'OFF'} | "
            f"{'AIR MOUSE' if self.mouse_mode else 'GESTURE MODE'}",
            f"Detected: {detected} | Stable: {self.stable_gesture}",
            f"Fingers: {finger_text}",
            f"Pinch: {self.pinch.status} | Ratio: {ratio:.3f}",
            f"Wake score: {self.voice_score:.2f} | FPS: {self.fps:.1f} | Actions: {self.action_count}",
        ]
        yy = 25
        for line in lines:
            cv2.putText(frame, line, (12, yy), cv2.FONT_HERSHEY_SIMPLEX,
                        0.52, (100, 240, 255), 1, cv2.LINE_AA)
            yy += 24

        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image = image.resize((800, 450), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image=image)
        self.camera_label.configure(image=photo, text="")
        self.camera_label.image = photo
        self.vision_line.config(
            text=f"{self.fps:.1f} FPS  |  {self.stable_gesture}  |  "
                 f"Pinch {self.pinch.status} ({ratio:.2f})"
        )

        self.status_controls.config(
            text="ENABLED" if self.controls_enabled else "DISABLED",
            fg=GREEN if self.controls_enabled else RED
        )
        self.status_mode.config(text="Air mouse" if self.mouse_mode else "Gesture + voice")
        self.status_gesture.config(text=self.stable_gesture)
        self.status_voice.config(text=self.voice_status, fg=PURPLE)
        self.status_action.config(text=self.last_action[:36])
        self.badge.config(
            text="● ACTIVE" if self.controls_enabled else "● STANDBY",
            fg=GREEN if self.controls_enabled else RED
        )
        self.enable_button.config(
            text="DISABLE CONTROLS  [E]" if self.controls_enabled
            else "ENABLE CONTROLS  [E]"
        )
        self.mouse_button.config(
            text="EXIT AIR MOUSE  [M]" if self.mouse_mode
            else "AIR MOUSE  [M]"
        )

        self.root.after(15, self.process_frame)

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "q":
            self.close()
        elif key == "e":
            self.toggle_controls()
        elif key == "m":
            self.toggle_mouse()
        elif key == "x":
            self.emergency_stop()
        elif key == "escape":
            self.speech.interrupt()
            self.voice_pause.clear()
            self.log("Speech interrupted; wake-word listening resumed")
        elif key in ("1", "2", "3", "4"):
            self.set_profile(list(PROFILES.keys())[int(key) - 1])

    def close(self):
        if not self.running:
            return
        self.running = False
        self.controls_enabled = False
        self._release_mouse_button()
        self.stop_voice.set()
        self.voice_pause.set()
        try:
            self.speech.close()
            self.camera.release()
            self.hands.close()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    try:
        JarvisApp(root)
    except Exception as exc:
        root.destroy()
        messagebox.showerror("JARVIS OS startup error", str(exc))
        return
    root.mainloop()


if __name__ == "__main__":
    main()
