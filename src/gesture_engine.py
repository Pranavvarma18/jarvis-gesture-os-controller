
"""Stable gesture confirmation and one-shot command triggering."""

from dataclasses import dataclass


NEUTRAL_GESTURES = {"OPEN_PALM"}
INVALID_GESTURES = {"UNKNOWN", "NO HAND"}


@dataclass
class GestureUpdate:
    """Result returned by the gesture gate."""

    stable_gesture: str
    should_trigger: bool
    armed: bool


class GestureGate:
    """
    Require stable frames and a neutral pose between commands.

    A command gesture triggers once. Showing an open palm
    consistently re-arms the controller for the next command.
    """

    def __init__(
        self,
        stable_frames: int = 5,
        neutral_frames: int = 4,
    ):
        if stable_frames < 1 or neutral_frames < 1:
            raise ValueError("Frame thresholds must be positive.")

        self.stable_frames = stable_frames
        self.neutral_frames = neutral_frames

        self._candidate = None
        self._candidate_count = 0
        self._neutral_count = 0
        self._armed = True

    def update(self, gesture: str) -> GestureUpdate:
        """Process one frame's gesture label."""
        if gesture in INVALID_GESTURES:
            self._candidate = None
            self._candidate_count = 0
            self._neutral_count = 0

            return GestureUpdate(
                stable_gesture="UNKNOWN",
                should_trigger=False,
                armed=self._armed,
            )

        if gesture in NEUTRAL_GESTURES:
            self._candidate = None
            self._candidate_count = 0
            self._neutral_count += 1

            if self._neutral_count >= self.neutral_frames:
                self._armed = True

            return GestureUpdate(
                stable_gesture="OPEN_PALM",
                should_trigger=False,
                armed=self._armed,
            )

        # A command gesture breaks the neutral-pose streak.
        self._neutral_count = 0

        if gesture == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = gesture
            self._candidate_count = 1

        stable = self._candidate_count >= self.stable_frames
        should_trigger = stable and self._armed

        if should_trigger:
            self._armed = False

        return GestureUpdate(
            stable_gesture=(
                gesture if stable else "DETECTING..."
            ),
            should_trigger=should_trigger,
            armed=self._armed,
        )
