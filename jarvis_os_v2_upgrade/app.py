"""JARVIS OS 2.0 — wake word, gesture control, air mouse and dashboard."""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import mediapipe as mp
import pyautogui
from PIL import Image, ImageTk

from src.actions import adjust_volume, execute_action, execute_named_action
from src.commands import execute_voice_command
from src.gestures import classify_gesture, get_finger_states
from src.motion import MotionDetector
from src.profiles import PROFILES, get_profile_action
from src.pinch import PinchDetector
from src.voice import WakeWordListener


CAMERA_INDEX = 0
FRAME_WIDTH = 960
FRAME_HEIGHT = 540
STABLE_FRAMES = 6
VOLUME_REPEAT_SECONDS = 0.18
ACTION_COOLDOWN_SECONDS = 0.65
VOLUME_GESTURES = {"THREE_FINGERS", "FOUR_FINGERS"}
NEUTRAL_GESTURES = {"OPEN_PALM", "UNKNOWN", "NO HAND"}
MOUSE_SMOOTHING = 0.32
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
        self.root.title("JARVIS OS 2.0 | Multimodal Control")
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
        self.events = queue.Queue()
        self.stop_voice = threading.Event()
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

        self.voice_thread = WakeWordListener(self.events, self.stop_voice)
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

        tk.Label(self.root, text="E: Controls   M: Air mouse   X: Emergency stop   Q: Quit",
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

    def enable_controls(self):
        self.controls_enabled = True
        self.mouse_mode = False
        self.armed = False
        self.active_volume_gesture = None
        self.pinch.reset()
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
        self.pinch.reset()
        self.log("EMERGENCY STOP — desktop controls disabled")

    def toggle_mouse(self):
        if not self.controls_enabled:
            self.log("Enable controls before starting air mouse")
            return
        self.mouse_mode = not self.mouse_mode
        self.armed = False
        self.active_volume_gesture = None
        self.mouse_position = None
        self.pinch.reset()
        self.log("Air mouse enabled" if self.mouse_mode else "Gesture mode enabled")

    def handle_voice(self, text):
        self.log(f'Heard: "{text}"')
        try:
            result = execute_voice_command(text, self)
            self.log(result)
        except pyautogui.FailSafeException:
            self.emergency_stop()
            self.log("PyAutoGUI safety stop triggered")
        except Exception as exc:
            self.log(f"Voice command error: {exc}")

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
            elif kind == "wake_detected":
                self.voice_status = "Wake word detected"
                self.log(f"Wake word detected ({float(payload):.2f})")
            elif kind == "wake_score":
                self.voice_score = float(payload)
            elif kind == "voice_text":
                self.voice_status = "Command received"
                self.handle_voice(payload)

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
            self.pinch.reset()

        elif self.mouse_mode:
            self.armed = False
            self.active_volume_gesture = None
            self.motion.reset()
            if hand is None:
                self.mouse_position = None
                self.pinch.reset()
            else:
                try:
                    self.move_cursor(hand)
                    click_event, ratio, pinch_status = self.pinch.update(hand)
                    if click_event:
                        pyautogui.click()
                        self.action_count += 1
                        self.log("Air mouse click")
                except pyautogui.FailSafeException:
                    self.emergency_stop()
                    self.log("PyAutoGUI safety stop triggered")
                except Exception as exc:
                    self.log(f"Air mouse error: {exc}")

        else:
            self.pinch.reset()
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
        elif key in ("1", "2", "3", "4"):
            self.set_profile(list(PROFILES.keys())[int(key) - 1])

    def close(self):
        if not self.running:
            return
        self.running = False
        self.controls_enabled = False
        self.stop_voice.set()
        try:
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
