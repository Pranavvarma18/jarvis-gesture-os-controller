"""Conversational JARVIS brain backed by local Ollama, with safe context memory."""

import json
import socket
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """You are JARVIS, a helpful, natural voice assistant on a Windows PC.
Be calm, capable, friendly, and concise. For voice replies, lead with the answer
and usually use 1-3 short sentences unless the user asks for detail.
Use recent conversation context to understand follow-up questions such as 'why?',
'what about the second one?', or 'open that'. If a reference is ambiguous, ask a
short clarifying question instead of inventing details.
Never claim a computer action succeeded unless the app reports its result. You
cannot see the user's screen or files unless supplied. Do not claim to have sent
messages, changed settings, deleted files, made purchases, or performed any action
that the desktop controller has not explicitly reported. Your name is JARVIS."""


class JarvisAI:
    """Thread-safe Ollama conversational client with bounded in-memory history."""

    def __init__(
        self,
        model=DEFAULT_MODEL,
        history_turns=6,
        timeout=60,
        keep_alive="20m",
        num_predict=180,
        num_ctx=3072,
        temperature=0.4,
    ):
        self.model = str(model)
        self.history_turns = max(1, int(history_turns))
        self.timeout = max(5, int(timeout))
        self.keep_alive = keep_alive
        self.num_predict = max(32, int(num_predict))
        self.num_ctx = max(1024, int(num_ctx))
        self.temperature = float(temperature)
        self.history = []
        self._history_lock = threading.RLock()

    def get_recent_context(self, max_chars=2400):
        """Return a compact, read-only text summary for the intent planner."""
        with self._history_lock:
            recent = list(self.history[-8:])
        lines = []
        for item in recent:
            role = item.get("role", "").upper()
            content = " ".join(str(item.get("content", "")).split())
            if not content:
                continue
            lines.append(f"{role}: {content}")
        context = "\n".join(lines)
        return context[-max(0, int(max_chars)):]

    def remember_exchange(self, user_text, assistant_text):
        """Add a completed desktop interaction to context for later follow-ups."""
        user_text = str(user_text).strip()
        assistant_text = str(assistant_text).strip()
        if not user_text or not assistant_text:
            return
        with self._history_lock:
            self.history.extend([
                {"role": "user", "content": user_text[:1000]},
                {"role": "assistant", "content": assistant_text[:1600]},
            ])
            self.history = self.history[-(self.history_turns * 2):]

    def reply(self, user_text, on_chunk: Optional[Callable[[str], None]] = None):
        """Return a full answer, optionally streaming text through on_chunk."""
        text = str(user_text).strip()
        if not text:
            return "I didn't catch a question. Please try again."

        with self._history_lock:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(dict(item) for item in self.history)
        messages.append({"role": "user", "content": text})

        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
            },
        }).encode("utf-8")
        request = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        pieces = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    try:
                        packet = json.loads(raw_line.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if packet.get("error"):
                        raise RuntimeError(f"Ollama: {packet['error']}")
                    chunk = packet.get("message", {}).get("content", "")
                    if chunk:
                        pieces.append(chunk)
                        if on_chunk is not None:
                            on_chunk(chunk)
                    if packet.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 404:
                raise RuntimeError(
                    f"Ollama model '{self.model}' was not found. Run: ollama pull {self.model}"
                ) from exc
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise RuntimeError(
                "Ollama is not reachable or took too long at "
                "http://127.0.0.1:11434. Start Ollama and verify the model is installed."
            ) from exc

        answer = "".join(pieces).strip()
        if not answer:
            raise RuntimeError("Ollama returned an empty answer.")

        self.remember_exchange(text, answer)
        return answer

    def clear_history(self):
        """Forget the current in-memory conversation."""
        with self._history_lock:
            self.history.clear()
