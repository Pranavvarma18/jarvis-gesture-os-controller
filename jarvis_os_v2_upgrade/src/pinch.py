"""Robust adaptive pinch detector for air-mouse clicking."""

from collections import deque


class PinchDetector:
    """
    Hysteresis + smoothing + frame confirmation.
    The ratio is thumb-index distance divided by palm width.
    """

    def __init__(
        self,
        start_ratio=0.30,
        release_ratio=0.48,
        confirm_frames=3,
        release_frames=3,
        smoothing=0.45,
        history_size=5,
    ):
        self.start_ratio = start_ratio
        self.release_ratio = release_ratio
        self.confirm_frames = confirm_frames
        self.release_frames_required = release_frames
        self.smoothing = smoothing
        self.history = deque(maxlen=history_size)
        self.smoothed_ratio = None
        self.down_frames = 0
        self.up_frames = 0
        self.is_pinched = False
        self.status = "READY"

    @staticmethod
    def measure(hand_landmarks):
        lm = hand_landmarks.landmark
        thumb, index = lm[4], lm[8]
        index_base, pinky_base = lm[5], lm[17]

        tip_distance = ((thumb.x - index.x) ** 2 + (thumb.y - index.y) ** 2) ** 0.5
        palm_width = ((index_base.x - pinky_base.x) ** 2 + (index_base.y - pinky_base.y) ** 2) ** 0.5
        return tip_distance / max(palm_width, 0.001)

    def update(self, hand_landmarks):
        raw = self.measure(hand_landmarks)
        self.history.append(raw)
        average = sum(self.history) / len(self.history)

        if self.smoothed_ratio is None:
            self.smoothed_ratio = average
        else:
            a = self.smoothing
            self.smoothed_ratio = a * average + (1 - a) * self.smoothed_ratio

        ratio = self.smoothed_ratio
        click_event = False

        if not self.is_pinched:
            self.up_frames = 0
            if ratio <= self.start_ratio:
                self.down_frames += 1
                self.status = "PINCH DETECTING"
            else:
                self.down_frames = 0
                self.status = "READY"

            if self.down_frames >= self.confirm_frames:
                self.is_pinched = True
                self.down_frames = 0
                self.status = "CLICK"
                click_event = True
        else:
            self.down_frames = 0
            if ratio >= self.release_ratio:
                self.up_frames += 1
                self.status = "RELEASING"
            else:
                self.up_frames = 0
                self.status = "PINCHED - HOLD"

            if self.up_frames >= self.release_frames_required:
                self.is_pinched = False
                self.up_frames = 0
                self.status = "READY"

        return click_event, ratio, self.status

    def reset(self):
        self.history.clear()
        self.smoothed_ratio = None
        self.down_frames = 0
        self.up_frames = 0
        self.is_pinched = False
        self.status = "READY"
