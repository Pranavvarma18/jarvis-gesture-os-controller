
from types import SimpleNamespace

from src.gestures import classify_gesture


def make_hand(extended_fingers):
    """Create synthetic landmarks for an upright hand."""
    points = [
        SimpleNamespace(x=0.5, y=0.5)
        for _ in range(21)
    ]

    # Default: curled fingers have tips below their PIP joints.
    pairs = [(8, 6), (12, 10), (16, 14), (20, 18)]

    for tip_id, pip_id in pairs:
        points[tip_id].y = 0.8
        points[pip_id].y = 0.6

    # Extended fingers have tips above their PIP joints.
    for finger_index in extended_fingers:
        tip_id, pip_id = pairs[finger_index]
        points[tip_id].y = 0.3
        points[pip_id].y = 0.6

    # Keep the synthetic thumb curled.
    points[4].x = points[3].x
    points[2].x = points[3].x

    return SimpleNamespace(landmark=points)


def test_fist():
    assert classify_gesture(make_hand([])) == "FIST"


def test_one_finger():
    assert classify_gesture(make_hand([0])) == "ONE_FINGER"


def test_two_fingers():
    assert classify_gesture(make_hand([0, 1])) == "TWO_FINGERS"


def test_three_fingers():
    assert classify_gesture(make_hand([0, 1, 2])) == "THREE_FINGERS"


def test_four_fingers():
    assert classify_gesture(make_hand([0, 1, 2, 3])) == "FOUR_FINGERS"


def test_missing_hand():
    assert classify_gesture(None) == "UNKNOWN"
