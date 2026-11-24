"""Settings, API keys and saved chats for the Linux port."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "glass"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "glass"
CHATS = DATA / "chats"

try:  # use the desktop keyring (GNOME Keyring / KWallet) when available
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None

DEFAULTS = {
    "provider": "anthropic",
    "model": "claude-sonnet-5-5",
    "base_url": "https://api.openai.com/v1",
    "system_prompt": "You are Glass, a sharp, friendly assistant that lives in a sidebar. Be concise and use Markdown when it helps.",
    "sensitivity": 1,
    "tint": "#5C5E64",          # semi-gray
    "tint_strength": 0.42,
    "blur": 18,
    "speak_replies": False,
    "recent_models": [],
}


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class Settings:
    def __init__(self) -> None:
        self.path = CONFIG / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(self.path.read_text("utf-8")))
        except Exception:
            pass
        self._file_keys: dict = self.data.pop("keys", {}) or {}

    def __getattr__(self, name):
        if name in ("data", "path", "_file_keys"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(name) from None

    def set(self, **kw) -> None:
        self.data.update(kw)

    def save(self) -> None:
        out = dict(self.data)
        if self._file_keys:
            out["keys"] = self._file_keys
        _write_private(self.path, json.dumps(out, indent=2))

    # ---- keys: one per provider
    def key_for(self, provider: str) -> str:
        if keyring is not None:
            try:
                v = keyring.get_password("glass", provider)
                if v:
                    return v
            except Exception:
                pass
        return self._file_keys.get(provider, "")

    def set_key(self, provider: str, value: str) -> None:
        if keyring is not None:
            try:
                if value:
                    keyring.set_password("glass", provider, value)
                else:
                    try:
                        keyring.delete_password("glass", provider)
                    except Exception:
                        pass
                self._file_keys.pop(provider, None)
                return
            except Exception:
                pass  # no keyring daemon: fall back to the private settings file
        if value:
            self._file_keys[provider] = value
        else:
            self._file_keys.pop(provider, None)

    @property
    def api_key(self) -> str:
        return self.key_for(self.provider)

    def has_key(self, provider: str) -> bool:
        return bool(self.key_for(provider))

    def keyed_providers(self) -> list[str]:
        return [p for p in ("anthropic", "gemini", "groq", "openai") if self.has_key(p)]

    def remember_model(self, model: str) -> None:
        tag = f"{self.provider}|{model}"
        rec = [r for r in self.data.get("recent_models", []) if r != tag]
        self.data["recent_models"] = [tag] + rec[:7]


# ---------------------------------------------------------------- chats

def new_chat() -> dict:
    return {"id": uuid.uuid4().hex, "title": "New chat", "smart_titled": False, "pinned": False,
            "updated": time.time(), "provider": "", "model": "", "messages": []}


def load_chats() -> list[dict]:
    out = []
    if CHATS.exists():
        for f in CHATS.glob("*.json"):
            try:
                c = json.loads(f.read_text("utf-8"))
                if c.get("messages"):
                    out.append(c)
            except Exception:
                continue
    return sort_chats(out)


def sort_chats(chats: list[dict]) -> list[dict]:
    return sorted(chats, key=lambda c: (not c.get("pinned"), -c.get("updated", 0)))


def save_chat(c: dict, touch: bool = True) -> None:
    if touch:
        c["updated"] = time.time()
    _write_private(CHATS / f"{c['id']}.json", json.dumps(c))


def delete_chat(c: dict) -> None:
    try:
        (CHATS / f"{c['id']}.json").unlink()
    except FileNotFoundError:
        pass


def make_title(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return "New chat"
    return t if len(t) <= 42 else t[:40].rstrip() + "…"


def relative(ts: float) -> str:
    s = time.time() - ts
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{int(s // 60)}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    if s < 172800:
        return "Yesterday"
    if s < 604800:
        return f"{int(s // 86400)}d ago"
    return time.strftime("%b %d", time.localtime(ts))


def bucket(c: dict) -> str:
    if c.get("pinned"):
        return "Pinned"
    day = time.localtime(c.get("updated", 0))
    now = time.localtime()
    days = (time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1)) -
            time.mktime((day.tm_year, day.tm_mon, day.tm_mday, 0, 0, 0, 0, 0, -1))) / 86400
    if days < 1:
        return "Today"
    if days < 2:
        return "Yesterday"
    if days < 7:
        return "Previous 7 days"
    return "Older"


def export_markdown(c: dict, label) -> str:
    out = [f"# {c['title']}\n"]
    for m in c["messages"]:
        who = "**You**" if m["role"] == "user" else f"**{label(m.get('provider', ''))}**"
        out.append(who + "\n")
        for a in m.get("attachments", []):
            out.append(f"> 📎 {a['name']}")
        out.append((m.get("content") or "") + "\n\n---\n")
    return "\n".join(out)
