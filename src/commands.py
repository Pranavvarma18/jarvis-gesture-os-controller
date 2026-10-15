
"""Natural-language command routing to explicit, allowlisted desktop skills."""

import os
import re
import shutil
import subprocess
import urllib.parse
import webbrowser

import pyautogui


# Only these applications may be launched through voice commands.
APP_ALLOWLIST = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "command prompt": ["cmd.exe"],
    "vscode": ["code"],
    "visual studio code": ["code"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "telegram": ["telegram"],
}


def normalize(text):
    """Normalize text for case-insensitive command matching."""
    return re.sub(r"\s+", " ", str(text).lower().strip())


def _open_url_or_search(text):
    """Open a URL or search Google for the supplied phrase."""
    value = text.strip()

    if not value:
        return "Tell me what website or topic to open."

    if re.match(r"^https?://", value, re.IGNORECASE):
        url = value
    elif (
        re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", value, re.IGNORECASE)
        and " " not in value
    ):
        url = "https://" + value
    else:
        url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(value)
        )

    webbrowser.open(url)
    return f"Opened: {value}"


def _open_site(site, query=None):
    """Open a known website or search within it."""
    sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "spotify": "https://open.spotify.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "netflix": "https://www.netflix.com",
        "chatgpt": "https://chatgpt.com",
        "whatsapp": "https://web.whatsapp.com",
        "instagram": "https://www.instagram.com",
        "linkedin": "https://www.linkedin.com",
        "stackoverflow": "https://stackoverflow.com",
    }
    base = sites[site]
    if query:
        if site == "youtube":
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        elif site == "spotify":
            url = "https://open.spotify.com/search/" + urllib.parse.quote(query)
        elif site == "netflix":
            url = "https://www.netflix.com/search?q=" + urllib.parse.quote_plus(query)
        else:
            url = base
    else:
        url = base
    webbrowser.open(url)
    return f"Opening {site.title()}" + (f" and searching for {query}." if query else ".")


def _launch_app(name):
    """Launch a known app without passing arbitrary speech to a shell."""
    normalized = normalize(name)
    if normalized == "spotify":
        # Prefer the registered Spotify URI; fall back to Spotify Web.
        try:
            os.startfile("spotify:")  # Windows opens the installed Spotify app if registered.
            return "Opening Spotify."
        except OSError:
            webbrowser.open("https://open.spotify.com")
            return "Opening Spotify Web because the desktop app could not be launched."

    if normalized in ("chrome", "google chrome", "google chrome browser"):
        candidates = [
            shutil.which("chrome"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                subprocess.Popen([path])
                return "Opening Google Chrome."
        webbrowser.open("https://www.google.com")
        return "Opened your default browser. Chrome was not found at its usual install locations."

    if normalized in ("edge", "microsoft edge"):
        candidates = [
            shutil.which("msedge"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                subprocess.Popen([path])
                return "Opening Microsoft Edge."
        webbrowser.open("https://www.google.com")
        return "Opened your default browser. Edge was not found at its usual install locations."

    command = APP_ALLOWLIST.get(normalized)
    if command:
        try:
            subprocess.Popen(command)
            return f"Launching {normalized}."
        except (OSError, FileNotFoundError):
            if normalized == "vscode" or normalized == "visual studio code":
                return "VS Code could not be found. Check that the 'code' command is enabled in PATH."
            if normalized in ("discord", "telegram"):
                webbrowser.open("https://discord.com/app" if normalized == "discord" else "https://web.telegram.org")
                return f"Opening {normalized.title()} Web because the desktop app was not found."
            return f"I couldn't launch {normalized}. It may not be installed."
    return f"I don't have a launcher configured for {normalized}."




def _play_youtube(query):
    """Resolve the first YouTube search result to a watch URL when yt-dlp is installed."""
    query = str(query).strip()
    if not query:
        return "Tell me which song or video to play."
    try:
        import yt_dlp
        options = {"quiet": True, "no_warnings": True, "skip_download": True,
                   "extract_flat": True, "default_search": "ytsearch1", "noplaylist": True}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info("ytsearch1:" + query, download=False)
        entries = info.get("entries") or []
        if entries:
            video = entries[0]
            video_id = video.get("id")
            if video_id:
                url = "https://www.youtube.com/watch?v=" + video_id
                webbrowser.open(url)
                return "Opening the top YouTube match for " + query + ". If autoplay is blocked by your browser, press Play."
    except Exception:
        pass
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    webbrowser.open(url)
    return "I opened YouTube search results for " + query + ". Install yt-dlp to enable automatic top-result resolution."


def _play_spotify(query):
    """Open Spotify's in-app search for a track/artist; does not bypass login or subscription controls."""
    query = str(query).strip()
    if not query:
        return "Tell me which song or artist to search for on Spotify."
    encoded = urllib.parse.quote(query, safe="")
    try:
        if os.name == "nt":
            os.startfile("spotify:search:" + encoded)
        else:
            webbrowser.open("https://open.spotify.com/search/" + encoded)
    except Exception:
        webbrowser.open("https://open.spotify.com/search/" + encoded)
    return "I opened Spotify search for " + query + ". Choose the exact track if several matches appear; Spotify requires its own player/login to start playback reliably."


def execute_agent_action(plan, app=None):
    """Execute one validated allowlisted skill and return a structured result.

    `ok` means the local action was accepted/dispatched. It does not prove that
    a remote site finished loading or that media actually started playing.
    """
    if not isinstance(plan, dict):
        return {"ok": False, "message": "Invalid action plan; nothing was executed."}

    action = str(plan.get("action", "unsupported")).strip().lower()
    target = str(plan.get("target", "")).strip()
    query = str(plan.get("query", "")).strip()

    def result(ok, message):
        return {"ok": bool(ok), "message": str(message)}

    if action == "open_app":
        aliases = {
            "chrome": "chrome", "google chrome": "chrome", "browser": "chrome",
            "edge": "edge", "microsoft edge": "edge", "spotify": "spotify",
            "vscode": "vscode", "vs code": "vscode", "visual studio code": "vscode",
            "notepad": "notepad", "calculator": "calculator", "calc": "calculator",
            "file explorer": "file explorer", "explorer": "file explorer",
            "paint": "paint", "discord": "discord", "telegram": "telegram",
        }
        key = normalize(target)
        if key not in aliases:
            return result(False, "No approved launcher is configured for " + (target or "that application") + ".")
        message = _launch_app(aliases[key])
        ok = not any(token in message.lower() for token in ("couldn't", "could not", "not found", "don't have"))
        return result(ok, message)

    if action == "open_site":
        site = normalize(target)
        known = {"youtube", "google", "spotify", "github", "gmail", "netflix", "chatgpt",
                 "whatsapp", "instagram", "linkedin", "stackoverflow"}
        if site not in known:
            return result(False, "That website is not on the approved site list.")
        message = _open_site(site, query or None)
        return result(True, message + " The browser was asked to open it; page loading was not independently verified.")

    if action == "search_web":
        query = query or target
        if not query:
            return result(False, "Tell me what you want to search for.")
        opened = webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
        return result(bool(opened), "Opened a Google search for " + query + "." if opened else "I could not confirm that the browser opened the Google search for " + query + ".")

    if action == "search_youtube":
        query = query or target
        if not query:
            return result(False, "Tell me what to search for on YouTube.")
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        opened = webbrowser.open(url)
        return result(bool(opened), "Opened YouTube search results for " + query + "." if opened else "I could not confirm that YouTube search opened. Playback has not been verified.")

    if action == "search_netflix":
        query = query or target
        if not query:
            return result(False, "Tell me which movie or show to search for on Netflix.")
        url = "https://www.netflix.com/search?q=" + urllib.parse.quote_plus(query)
        opened = webbrowser.open(url)
        if opened:
            return result(True, "Opened Netflix search for " + query + ". Sign-in, regional availability, and playback may require your input.")
        return result(False, "I could not confirm that the browser opened Netflix search.")

    if action == "play_youtube":
        query = query or target
        if not query:
            return result(False, "Tell me which video or song to find on YouTube.")
        message = _play_youtube(query)
        # The helper opens a direct top match when yt-dlp resolves one, otherwise search.
        return result(True, message + " I cannot verify that playback actually started.")

    if action == "play_spotify":
        query = query or target
        if not query:
            return result(False, "Tell me which track or artist to find on Spotify.")
        message = _play_spotify(query)
        return result(True, message + " Playback itself is not verified.")

    if action == "media_control":
        controls = {
            "play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack",
            "volume_up": "volumeup", "volume_down": "volumedown", "mute": "volumemute",
        }
        key = normalize(target)
        if key not in controls:
            return result(False, "Unsupported media-control shortcut; nothing was sent.")
        try:
            pyautogui.press(controls[key], presses=3 if key in ("volume_up", "volume_down") else 1, interval=0.05)
        except Exception as exc:
            return result(False, "Could not send the media shortcut: " + str(exc))
        return result(True, "Sent the media shortcut: " + key.replace("_", " ") + ". The active player response was not verified.")

    if action == "unsupported":
        return result(False, "This task is not safely integrated yet. I have not performed it.")

    return result(False, "Unknown action. Nothing was executed.")


def execute_voice_command(raw_text, app):
    """
    Execute a supported voice command.

    Parameters
    ----------
    raw_text : str
        The recognized speech.
    app : JarvisApp
        The running dashboard/controller instance.

    Returns
    -------
    str
        A message describing the action or explaining why it was rejected.
    """
    text = normalize(raw_text)

    if not text:
        return "I didn't receive a command."

    # ---------------------------------------------------------
    # WHATSAPP MESSAGE: draft first, then ask for explicit confirmation.
    # Requires a full international phone number; contact-name lookup is not
    # implemented because WhatsApp does not expose a stable local contacts API.
    # ---------------------------------------------------------
    whatsapp_patterns = (
        r"^\s*(?:jarvis[,:]?\s+)?(?:please\s+)?(?:send|text|message)\s+(?:a\s+)?(?:whats\s*app(?:\s+message)?|message\s+(?:on\s+)?whats\s*app)\s+to\s+(.+?)\s+(?:saying|that\s+says|with\s+message)\s+(.+?)\s*$",
        r"^\s*(?:jarvis[,:]?\s+)?(?:please\s+)?(?:send|text)\s+(.+?)\s+a\s+whats\s*app\s+(?:message\s+)?saying\s+(.+?)\s*$",
    )
    for pattern in whatsapp_patterns:
        match = re.match(pattern, str(raw_text), re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        recipient = match.group(1).strip().strip(".,;:")
        message_body = match.group(2).strip().strip('"“”')
        digits = "".join(ch for ch in recipient if ch.isdigit())
        if not 11 <= len(digits) <= 15:
            return ("For safety, say the full international WhatsApp number including country code, "
                    "then say the message after the word 'saying'. Example: send WhatsApp to plus nine one ... saying Hello.")
        if not message_body:
            return "Tell me the exact message to send after the word 'saying'."
        if len(message_body) > 1500:
            return "That message is too long for this voice workflow. Please keep it under 1500 characters."
        return app.request_whatsapp_message(recipient, message_body)

    # ---------------------------------------------------------
    # SAFETY AND CONTROLLER COMMANDS
    # ---------------------------------------------------------
    emergency_phrases = (
        "emergency stop",
        "stop all controls",
        "disable controls",
        "stop jarvis controls",
        "shut down control",
    )

    if any(phrase in text for phrase in emergency_phrases):
        app.emergency_stop()
        return "Emergency stop activated."

    if text in (
        "enable controls",
        "activate controls",
        "enable jarvis controls",
    ):
        app.enable_controls()
        return "Controls enabled. Show an open palm to arm gestures."

    # ---------------------------------------------------------
    # PROFILE SWITCHING
    # ---------------------------------------------------------
    profiles = {
        "browser": "Browser",
        "media": "Media",
        "presentation": "Presentation",
        "accessibility": "Accessibility",
    }

    for keyword, profile in profiles.items():
        if text in (
            f"{keyword} mode",
            f"switch to {keyword}",
            f"activate {keyword} mode",
            f"switch to {keyword} mode",
            f"open {keyword} mode",
        ):
            app.set_profile(profile)
            return f"{profile} profile activated."

    # ---------------------------------------------------------
    # NETFLIX TITLE SEARCH: opening a title search is supported; automatic
    # playback is not claimed because login, region, and subscription matter.
    # ---------------------------------------------------------
    netflix_match = re.match(
        r"^(?:please\s+)?(?:search for|find|look for|play)\s+(.+?)\s+on\s+netflix$",
        text,
    )
    if netflix_match:
        title = netflix_match.group(1).strip(" .!?")
        if title:
            return _open_site("netflix", title) + " I opened title search; playback was not verified."

    # ---------------------------------------------------------
    # PLAY A SONG / VIDEO: YouTube resolves to a direct watch URL when yt-dlp
    # is installed; Spotify opens its own in-app search (login/player required).
    # ---------------------------------------------------------
    media_match = re.match(
        r"^(?:please\s+)?(?:play|search for)\s+(.+?)\s+on\s+(youtube|you tube|spotify)$",
        text,
    )
    if media_match:
        query = media_match.group(1).strip(" .!?")
        platform = media_match.group(2).replace(" ", "")
        if query:
            return _play_youtube(query) if platform == "youtube" else _play_spotify(query)
    media_match = re.match(r"^(?:please\s+)?play\s+(.+)$", text)
    if media_match and not text.endswith(" on netflix") and not any(token in text for token in ("pause music", "play pause", "next song", "previous song")):
        query = media_match.group(1).strip(" .!?")
        if query and query not in ("music", "a song", "something"):
            return _play_youtube(query)

    # ---------------------------------------------------------
    # DIRECT WEBSITE SHORTCUTS
    # ---------------------------------------------------------
    site_aliases = {
        "youtube": ("youtube", "you tube"),
        "google": ("google",),
        "github": ("github", "git hub"),
        "gmail": ("gmail", "google mail"),
        "netflix": ("netflix",),
        "chatgpt": ("chatgpt", "chat gpt"),
        "whatsapp": ("whatsapp", "whats app"),
        "instagram": ("instagram",),
        "linkedin": ("linkedin", "linked in"),
        "stackoverflow": ("stackoverflow", "stack overflow"),
    }
    for site, aliases in site_aliases.items():
        if text in (f"open {alias}" for alias in aliases) or text in (f"launch {alias}" for alias in aliases) or text in (f"start {alias}" for alias in aliases):
            return _open_site(site)

    # ---------------------------------------------------------
    # WEB SEARCH
    # Examples:
    # "Search for Python tutorials"
    # "Google machine learning"
    # "Look up OpenCV hand tracking"
    # ---------------------------------------------------------
    search_prefixes = (
        "search the web for ",
        "search for ",
        "search ",
        "google ",
        "look up ",
        "find information about ",
    )

    for prefix in search_prefixes:
        if text.startswith(prefix):
            query = raw_text.strip()[len(prefix):].strip()
            return _open_url_or_search(query)

    # ---------------------------------------------------------
    # WEBSITE NAVIGATION
    # Examples:
    # "Open site youtube.com"
    # "Go to github.com"
    # "Navigate to stackoverflow.com"
    # ---------------------------------------------------------
    navigation_prefixes = (
        "open website ",
        "open site ",
        "go to ",
        "navigate to ",
        "visit ",
    )

    for prefix in navigation_prefixes:
        if text.startswith(prefix):
            destination = raw_text.strip()[len(prefix):].strip()
            return _open_url_or_search(destination)

    if text in (
        "open browser",
        "launch browser",
        "start browser",
        "open google",
        "launch web browser",
    ):
        webbrowser.open("https://www.google.com")
        return "Opened your browser."

    # ---------------------------------------------------------
    # LAUNCH ALLOWLISTED DESKTOP APPLICATIONS
    # ---------------------------------------------------------
    app_aliases = {
        "chrome": ("chrome", "google chrome", "google chrome browser"),
        "edge": ("edge", "microsoft edge"),
        "spotify": ("spotify",),
        "discord": ("discord",),
        "telegram": ("telegram",),
        "notepad": ("notepad",),
        "calculator": ("calculator", "calc"),
        "paint": ("paint", "microsoft paint"),
        "file explorer": ("file explorer", "explorer", "files"),
        "command prompt": ("command prompt", "cmd"),
        "vscode": ("vscode", "vs code", "visual studio code", "code editor"),
    }
    for app_name, aliases in app_aliases.items():
        if any(text in (f"open {alias}", f"launch {alias}", f"start {alias}") for alias in aliases):
            return _launch_app(app_name)

    # ---------------------------------------------------------
    # MEDIA PLAYBACK
    # ---------------------------------------------------------
    if any(
        phrase in text
        for phrase in (
            "pause music",
            "play music",
            "play pause",
            "play or pause",
            "toggle playback",
            "pause video",
            "resume video",
            "play pause music",
            "toggle music",
        )
    ):
        pyautogui.press("playpause")
        return "Toggled playback."

    if any(
        phrase in text
        for phrase in (
            "next track",
            "next song",
            "skip song",
            "next music",
            "play next song",
        )
    ):
        pyautogui.press("nexttrack")
        return "Next track."

    if any(
        phrase in text
        for phrase in (
            "previous track",
            "previous song",
            "go back a song",
            "play previous song",
        )
    ):
        pyautogui.press("prevtrack")
        return "Previous track."

    # ---------------------------------------------------------
    # VOLUME
    # ---------------------------------------------------------
    if any(
        phrase in text
        for phrase in (
            "mute volume",
            "mute sound",
            "toggle mute",
            "mute my computer",
        )
    ):
        pyautogui.press("volumemute")
        return "Toggled mute."

    if any(
        phrase in text
        for phrase in (
            "volume up",
            "increase volume",
            "make it louder",
            "turn it up",
            "increase the sound",
        )
    ):
        pyautogui.press("volumeup", presses=3, interval=0.05)
        return "Volume increased."

    if any(
        phrase in text
        for phrase in (
            "volume down",
            "decrease volume",
            "make it quieter",
            "turn it down",
            "lower the sound",
        )
    ):
        pyautogui.press("volumedown", presses=3, interval=0.05)
        return "Volume decreased."

    # ---------------------------------------------------------
    # BROWSER TABS
    # ---------------------------------------------------------
    if any(
        phrase in text
        for phrase in (
            "next tab",
            "switch tab right",
            "switch to next tab",
        )
    ):
        pyautogui.hotkey("ctrl", "tab")
        return "Switched to next tab."

    if any(
        phrase in text
        for phrase in (
            "previous tab",
            "switch tab left",
            "last tab",
            "switch to previous tab",
        )
    ):
        pyautogui.hotkey("ctrl", "shift", "tab")
        return "Switched to previous tab."

    # ---------------------------------------------------------
    # PRESENTATION SLIDES
    # ---------------------------------------------------------
    if any(
        phrase in text
        for phrase in (
            "next slide",
            "advance slide",
            "next presentation slide",
        )
    ):
        pyautogui.press("right")
        return "Next slide."

    if any(
        phrase in text
        for phrase in (
            "previous slide",
            "go back a slide",
            "previous presentation slide",
        )
    ):
        pyautogui.press("left")
        return "Previous slide."

    # ---------------------------------------------------------
    # SCROLLING
    # ---------------------------------------------------------
    if text in (
        "scroll up",
        "page up",
        "scroll upward",
    ):
        pyautogui.scroll(5)
        return "Scrolled up."

    if text in (
        "scroll down",
        "page down",
        "scroll downward",
    ):
        pyautogui.scroll(-5)
        return "Scrolled down."

    # ---------------------------------------------------------
    # TYPE TEXT INTO THE CURRENTLY FOCUSED APPLICATION
    # Example: "Type text Hello, how are you?"
    # ---------------------------------------------------------
    type_prefix = "type text "

    if text.startswith(type_prefix):
        payload = raw_text.strip()[len(type_prefix):]

        if not payload:
            return "Tell me what text to type."

        pyautogui.write(payload, interval=0.015)
        return "Typed the requested text into the focused application."

    # ---------------------------------------------------------
    # UNKNOWN COMMAND
    # Do not interpret arbitrary speech as a shell command.
    # ---------------------------------------------------------
    # None means this was not a registered desktop skill. app.py routes it
    # to the conversational AI instead of rejecting ordinary questions.
    return None
