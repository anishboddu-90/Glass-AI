"""Voice for Linux: mic recording with level + silence detection (Qt Multimedia), and text-to-speech."""
from __future__ import annotations

import io
import math
import re
import shutil
import struct
import subprocess
import wave

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
except Exception:  # pragma: no cover
    QAudioSource = None

RATE = 16000


class Recorder(QObject):
    """Records 16 kHz mono. Emits level (0..1) continuously and finished(wav_bytes) after you stop talking."""
    level = Signal(float)
    finished = Signal(bytes)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.src = None
        self.dev = None
        self.buf = bytearray()
        self.heard_speech = False
        self.silence_ms = 0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)

    @property
    def active(self) -> bool:
        return self.src is not None

    def start(self) -> None:
        if QAudioSource is None:
            self.failed.emit("Qt Multimedia isn't available, so voice input can't record. Reinstall with ./install.sh.")
            return
        dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            self.failed.emit("No microphone found.")
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self.buf = bytearray()
        self.heard_speech = False
        self.silence_ms = 0
        self.src = QAudioSource(dev, fmt, self)
        self.dev = self.src.start()
        if self.dev is None:
            self.src = None
            self.failed.emit("Couldn't open the microphone.")
            return
        self.timer.start()

    def _tick(self) -> None:
        if self.dev is None:
            return
        chunk = bytes(self.dev.readAll())
        if chunk:
            self.buf.extend(chunk)
            n = len(chunk) // 2
            if n:
                samples = struct.unpack(f"<{n}h", chunk[: n * 2])
                rms = math.sqrt(sum(s * s for s in samples[::4]) / max(1, len(samples[::4])))
                lvl = min(1.0, rms / 6000.0)
                self.level.emit(lvl)
                if lvl > 0.08:
                    self.heard_speech = True
                    self.silence_ms = 0
                else:
                    self.silence_ms += 50
        # auto-stop: 1.2 s of quiet after you've said something, or 60 s max
        if (self.heard_speech and self.silence_ms > 1200) or len(self.buf) > RATE * 2 * 60:
            self.stop(send=True)

    def stop(self, send: bool = False) -> None:
        if self.src is None:
            return
        self.timer.stop()
        self.src.stop()
        self.src = None
        self.dev = None
        if send and self.heard_speech and len(self.buf) > RATE // 2:
            out = io.BytesIO()
            with wave.open(out, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(bytes(self.buf))
            self.finished.emit(out.getvalue())
        self.buf = bytearray()


class Speaker(QObject):
    """Reads replies aloud with speech-dispatcher (spd-say) or espeak-ng, whichever is installed."""
    speaking_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: subprocess.Popen | None = None
        self.poll = QTimer(self)
        self.poll.setInterval(200)
        self.poll.timeout.connect(self._check)

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("spd-say") or shutil.which("espeak-ng") or shutil.which("espeak"))

    @property
    def speaking(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def speak(self, markdown: str) -> None:
        self.stop()
        text = plain(markdown)
        if not text:
            return
        if shutil.which("spd-say"):
            cmd = ["spd-say", "-w", "-r", "10", text]
        elif shutil.which("espeak-ng"):
            cmd = ["espeak-ng", "-s", "175", text]
        elif shutil.which("espeak"):
            cmd = ["espeak", "-s", "175", text]
        else:
            return
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.speaking_changed.emit(True)
        self.poll.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            if shutil.which("spd-say"):
                subprocess.run(["spd-say", "-C"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.proc:
            self.proc = None
            self.poll.stop()
            self.speaking_changed.emit(False)

    def _check(self) -> None:
        if self.proc and self.proc.poll() is not None:
            self.proc = None
            self.poll.stop()
            self.speaking_changed.emit(False)


def plain(md: str) -> str:
    t = md or ""
    t = re.sub(r"```[\s\S]*?```", " (code block) ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_#>~|]+", "", t)
    t = re.sub(r"^\s*[-+]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()[:4000]
