
"""Low-latency pinch detector with hysteresis and drag support."""
from collections import deque
import math
import time


class PinchDetector:
    """Detect pinch press/release events.

    update(hand) returns:
        (press_event, smoothed_ratio, status)

    press_event: press the mouse button.
    release_event: release the mouse button.
    Holding a pinch supports drag-and-drop.
    """

    def __init__(
        self,
        start_ratio=0.34,
        release_ratio=0.52,
        confirm_frames=2,
        release_frames=2,
        smoothing=0.72,
        history_size=3,
        click_cooldown=0.0,
    ):
        if start_ratio <= 0 or release_ratio <= start_ratio:
            raise ValueError("Require 0 < start_ratio < release_ratio.")
        if confirm_frames < 1 or release_frames < 1:
            raise ValueError("Frame thresholds must be positive.")
        if not 0 < smoothing <= 1:
            raise ValueError("smoothing must be in (0, 1].")
        if history_size < 1 or click_cooldown < 0:
            raise ValueError("Invalid history size or click cooldown.")

        self.start_ratio = float(start_ratio)
        self.release_ratio = float(release_ratio)
        self.confirm_frames = int(confirm_frames)
        self.release_frames_required = int(release_frames)
        self.smoothing = float(smoothing)
        self.history = deque(maxlen=int(history_size))
        self.click_cooldown = float(click_cooldown)

        self.last_press_time = 0.0
        self.smoothed_ratio = None
        self.down_frames = 0
        self.up_frames = 0
        self.is_pinched = False
        self.release_event = False
        self.status = "READY"

    @staticmethod
    def _distance(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    @classmethod
    def measure(cls, hand_landmarks):
        if hand_landmarks is None:
            raise ValueError("hand_landmarks cannot be None")

        landmarks = getattr(hand_landmarks, "landmark", hand_landmarks)

        if len(landmarks) < 21:
            raise ValueError("Expected at least 21 hand landmarks.")

        pinch_distance = cls._distance(landmarks[4], landmarks[8])
        palm_width = max(cls._distance(landmarks[5], landmarks[17]), 0.001)

        return pinch_distance / palm_width

    def update(self, hand_landmarks):
        self.release_event = False

        raw_ratio = self.measure(hand_landmarks)
        self.history.append(raw_ratio)

        average_ratio = sum(self.history) / len(self.history)

        if self.smoothed_ratio is None:
            self.smoothed_ratio = average_ratio
        else:
            self.smoothed_ratio = (
                self.smoothing * average_ratio
                + (1.0 - self.smoothing) * self.smoothed_ratio
            )

        ratio = self.smoothed_ratio
        press_event = False
        now = time.monotonic()

        if not self.is_pinched:
            self.up_frames = 0

            if ratio <= self.start_ratio:
                self.down_frames += 1
                self.status = "PINCH DETECTING"
            else:
                self.down_frames = 0
                self.status = "READY"

            cooldown_elapsed = (
                self.click_cooldown <= 0
                or now - self.last_press_time >= self.click_cooldown
            )

            if (
                self.down_frames >= self.confirm_frames
                and cooldown_elapsed
            ):
                self.is_pinched = True
                self.down_frames = 0
                self.last_press_time = now
                self.status = "PRESSED / DRAG"
                press_event = True

        else:
            self.down_frames = 0

            if ratio >= self.release_ratio:
                self.up_frames += 1
                self.status = "RELEASING"
            else:
                self.up_frames = 0
                self.status = "PRESSED / DRAG"

            if self.up_frames >= self.release_frames_required:
                self.is_pinched = False
                self.up_frames = 0
                self.down_frames = 0
                self.status = "READY"
                self.release_event = True

        return press_event, ratio, self.status

    def reset(self):
        """Reset detector state. Release any held OS mouse button first."""
        self.history.clear()
        self.smoothed_ratio = None
        self.down_frames = 0
        self.up_frames = 0
        self.is_pinched = False
        self.release_event = False
        self.status = "READY"
        self.last_press_time = 0.0
