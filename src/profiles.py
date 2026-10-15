"""Context-aware motion profiles."""

PROFILES = {
    "Browser": {
        "LEFT": "previous_tab",
        "RIGHT": "next_tab",
        "UP": "scroll_up",
        "DOWN": "scroll_down",
    },
    "Media": {
        "LEFT": "previous_track",
        "RIGHT": "next_track",
        "UP": "volume_up",
        "DOWN": "volume_down",
    },
    "Presentation": {
        "LEFT": "previous_slide",
        "RIGHT": "next_slide",
        "UP": "volume_up",
        "DOWN": "volume_down",
    },
    "Accessibility": {
        "LEFT": "scroll_left",
        "RIGHT": "scroll_right",
        "UP": "scroll_up",
        "DOWN": "scroll_down",
    },
}


def get_profile_action(profile_name, direction):
    """Return an action identifier for the selected profile."""
    profile = PROFILES.get(profile_name, PROFILES["Browser"])
    return profile.get(direction)