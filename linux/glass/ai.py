"""Streaming AI clients for Claude, Gemini, Groq and any OpenAI-compatible server (stdlib only)."""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from typing import Callable, Iterable

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_BASE = "https://api.groq.com/openai/v1"
ANTHROPIC_DEFAULT = "claude-sonnet-5-5"
GEMINI_DEFAULT = "gemini-4-hydrogen"
CLAUDE_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]

LABELS = {"anthropic": "Claude", "gemini": "Gemini", "groq": "Groq", "openai": "OpenAI"}


def label(provider: str) -> str:
    return LABELS.get(provider, "Assistant")


def provider_for_key(key: str) -> str | None:
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-"):
        return "openai"
    return None


def extract_key(text: str) -> str | None:
    """Pull an API key out of pasted text or a .txt/.env/.json file."""
    if not text or not text.strip():
        return None
    for pat in (r"sk-ant-[A-Za-z0-9_\-]{20,}", r"AIza[0-9A-Za-z_\-]{30,}", r"gsk_[0-9A-Za-z]{20,}"):
        m = re.search(pat, text)
        if m:
            return m.group(0)
    m = re.search(r"(?:ANTHROPIC|OPENAI|OPENROUTER|GROQ|GEMINI|GOOGLE)?_?API_KEY\s*[=:]\s*[\"']?([A-Za-z0-9_\-\.]{16,})", text)
    if m:
        return m.group(1)
    m = re.search(r"sk-[A-Za-z0-9_\-]{20,}", text)
    if m:
        return m.group(0)
    t = text.strip()
    return t if len(t) >= 16 and " " not in t and "\n" not in t else None


def error_text(raw: str) -> str:
    m = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', raw or "")
    if m:
        try:
            return json.loads('"' + m.group(1) + '"')
        except Exception:
            return m.group(1)
    return (raw or "")[:300]


# ---------------------------------------------------------------- message building

def _text_with_files(msg: dict) -> str:
    parts = []
    for a in msg.get("attachments", []):
        if a["kind"] == "text":
            parts.append(f"File: {a['name']}\n```\n{a['text']}\n```\n")
    parts.append(msg.get("content", ""))
    return "\n".join(parts)


def _anthropic_content(msg: dict):
    atts = msg.get("attachments") or []
    if not atts:
        return msg.get("content", "")
    blocks = []
    for a in atts:
        if a["kind"] == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": a["media_type"], "data": a["data"]}})
        elif a["kind"] == "pdf":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": a["data"]}})
    text = _text_with_files(msg).strip() or "(see attachment)"
    blocks.append({"type": "text", "text": text})
    return blocks


def _openai_content(msg: dict, provider: str):
    atts = msg.get("attachments") or []
    if not atts:
        return msg.get("content", "")
    parts = []
    text = _text_with_files(msg)
    for a in atts:
        if a["kind"] == "pdf":
            if provider == "openai":
                parts.append({"type": "file", "file": {"filename": a["name"], "file_data": "data:application/pdf;base64," + a["data"]}})
            else:
                text = f"[A PDF named {a['name']} was attached, but this provider can't read PDFs directly.]\n\n" + text
    parts.append({"type": "text", "text": text.strip() or "(see attachment)"})
    for a in atts:
        if a["kind"] == "image":
            parts.append({"type": "image_url", "image_url": {"url": f"data:{a['media_type']};base64,{a['data']}"}})
    return parts


def _request(provider: str, model: str, key: str, base_url: str, system: str, history: list[dict]) -> urllib.request.Request:
    if not key:
        raise RuntimeError("No API key yet. Open Settings to add one.")
    anthropic = provider == "anthropic"
    msgs = []
    if not anthropic and system:
        msgs.append({"role": "system", "content": system})
    for m in history:
        if m["role"] == "assistant" and not m.get("content"):
            continue
        msgs.append({"role": m["role"], "content": _anthropic_content(m) if anthropic else _openai_content(m, provider)})

    if anthropic:
        body = {"model": model, "max_tokens": 8192, "stream": True, "messages": msgs}
        if system:
            body["system"] = system
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST")
        req.add_header("x-api-key", key)
        req.add_header("anthropic-version", "2023-06-01")
    else:
        base = GEMINI_BASE if provider == "gemini" else GROQ_BASE if provider == "groq" else base_url
        body = {"model": model, "stream": True, "messages": msgs}
        req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST")
        req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Glass/2.0")
    return req


def stream(provider: str, model: str, key: str, base_url: str, system: str, history: list[dict],
           on_delta: Callable[[str], None], cancel: threading.Event) -> None:
    """Blocking: call from a worker thread. Raises on API errors."""
    req = _request(provider, model, key, base_url, system, history)
    anthropic = provider == "anthropic"
    try:
        resp = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"API error {e.code}: {error_text(raw)}") from None
    with resp:
        for raw_line in resp:
            if cancel.is_set():
                return
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                evt = json.loads(data)
            except ValueError:
                continue
            if anthropic:
                if evt.get("type") == "error":
                    raise RuntimeError(error_text(data))
                if evt.get("type") == "content_block_delta":
                    t = (evt.get("delta") or {}).get("text")
                    if t:
                        on_delta(t)
            else:
                ch = evt.get("choices") or []
                if ch:
                    t = (ch[0].get("delta") or {}).get("content")
                    if t:
                        on_delta(t)


def quick(provider: str, model: str, key: str, base_url: str, prompt: str) -> str:
    out: list[str] = []
    stream(provider, model, key, base_url, "", [{"role": "user", "content": prompt}], out.append, threading.Event())
    return "".join(out)


# ---------------------------------------------------------------- model lists

def _get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Glass/2.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Couldn't list models ({e.code}): {error_text(e.read().decode('utf-8', 'replace'))}") from None


def list_models(provider: str, key: str) -> list[tuple[str, str]]:
    if provider == "gemini":
        out, token = [], None
        while True:
            url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000" + (f"&pageToken={token}" if token else "")
            page = _get_json(url, {"x-goog-api-key": key})
            for m in page.get("models", []):
                mid = m.get("name", "").replace("models/", "")
                if mid.startswith("gemini") and "generateContent" in (m.get("supportedGenerationMethods") or []):
                    out.append((mid, m.get("displayName") or mid))
            token = page.get("nextPageToken")
            if not token:
                break
        return sorted(out, key=lambda x: x[0], reverse=True)
    if provider == "groq":
        page = _get_json(GROQ_BASE + "/models", {"Authorization": "Bearer " + key})
        skip = ("whisper", "tts", "guard", "orpheus")
        ids = [m["id"] for m in page.get("data", []) if m.get("active", True) and not any(s in m["id"].lower() for s in skip)]
        return [(i, i) for i in sorted(ids)]
    return []


# ---------------------------------------------------------------- speech to text (voice mode)

def transcribe(wav_bytes: bytes, provider: str, key: str, base_url: str) -> str:
    """Whisper transcription via Groq or OpenAI(-compatible). Raises if the provider can't do it."""
    if provider == "groq":
        url, model = GROQ_BASE + "/audio/transcriptions", "whisper-large-v3-turbo"
    elif provider == "openai":
        url, model = base_url.rstrip("/") + "/audio/transcriptions", "whisper-1"
    else:
        raise RuntimeError("Voice input on Linux needs a Groq or OpenAI key (it uses Whisper). Add one in Settings.")
    boundary = "----glass" + str(abs(hash(wav_bytes)) % 10**12)
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"speech.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode(),
        wav_bytes, f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("User-Agent", "Glass/2.0")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return (json.loads(r.read().decode()).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Transcription failed ({e.code}): {error_text(e.read().decode('utf-8', 'replace'))}") from None


def voice_provider(available: Iterable[str]) -> str | None:
    for p in ("groq", "openai"):
        if p in available:
            return p
    return None
