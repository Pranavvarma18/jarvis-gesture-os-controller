"""Temporal arm/hand motion detection."""

from collections import deque


class MotionDetector:
    def __init__(
        self,
        distance_threshold=0.22,
        vertical_threshold=0.20,
        min_duration=0.12,
        max_duration=0.65,
        cooldown=0.85,
    ):
        self.distance_threshold = distance_threshold
        self.vertical_threshold = vertical_threshold
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.cooldown = cooldown

        self.history = deque(maxlen=20)
        self.last_trigger_time = 0.0

    def reset(self):
        self.history.clear()

    def update(self, x, y, now, enabled=True):
        """
        Return LEFT, RIGHT, UP, DOWN, or None.

        Coordinates are normalized to 0..1.
        Call while a stable open palm is visible.
        """
        if not enabled:
            self.reset()
            return None

        self.history.append((now, x, y))

        if len(self.history) < 4:
            return None

        # Find a recent starting point. The current hand position is
        # compared with older positions to detect intentional movement.
        current_t, current_x, current_y = self.history[-1]

        for start_t, start_x, start_y in self.history:
            duration = current_t - start_t

            if duration < self.min_duration:
                continue

            if duration > self.max_duration:
                continue

            dx = current_x - start_x
            dy = current_y - start_y

            if abs(dx) >= self.distance_threshold:
                if current_t - self.last_trigger_time < self.cooldown:
                    return None

                self.last_trigger_time = current_t
                self.reset()

                return "RIGHT" if dx > 0 else "LEFT"

            if abs(dy) >= self.vertical_threshold:
                if current_t - self.last_trigger_time < self.cooldown:
                    return None

                self.last_trigger_time = current_t
                self.reset()

                return "DOWN" if dy > 0 else "UP"

        # Keep a limited motion window so old positions don't accumulate.
        while (
            len(self.history) > 2
            and current_t - self.history[0][0] > self.max_duration
        ):
            self.history.popleft()

        return None