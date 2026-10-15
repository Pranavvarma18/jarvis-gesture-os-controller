from types import SimpleNamespace
from src.pinch import PinchDetector

def hand(gap):
    points = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    points[4] = SimpleNamespace(x=0.5-gap/2, y=0.5)
    points[8] = SimpleNamespace(x=0.5+gap/2, y=0.5)
    points[5] = SimpleNamespace(x=0.0, y=0.0)
    points[17] = SimpleNamespace(x=1.0, y=0.0)
    return SimpleNamespace(landmark=points)

def test_click_after_two_pinched_frames_and_only_once_until_release():
    d = PinchDetector(start_ratio=0.36, release_ratio=0.55, smoothing=1.0, history_size=1)
    assert d.update(hand(0.2))[0] is False
    assert d.update(hand(0.2))[0] is True
    assert d.update(hand(0.2))[0] is False
    d.update(hand(0.8)); d.update(hand(0.8))
    assert d.is_pinched is False
    assert d.update(hand(0.2))[0] is False
    assert d.update(hand(0.2))[0] is True

def test_reset_clears_state():
    d = PinchDetector(smoothing=1.0, history_size=1)
    d.update(hand(0.2)); d.update(hand(0.2))
    assert d.is_pinched
    d.reset()
    assert not d.is_pinched and d.status == "READY"
