"""Glass rendering, screenshots and attachments for Linux.

Linux compositors don't let an app read what's behind its own window in real time, so the
glass here is a *snapshot*: right before the panel slides in we capture the screen behind it,
then blur, tint and refract it (edge lensing + RGB split) with numpy. On KDE we also ask KWin
for live blur-behind. On Wayland desktops that block screen capture, it falls back to tint only.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap

try:
    import numpy as np  # optional: enables real refraction
except Exception:  # pragma: no cover
    np = None

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".log", ".env",
            ".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".py", ".rb", ".go", ".rs", ".java", ".kt",
            ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".m", ".php", ".sh", ".bat", ".ps1", ".sql", ".lua", ".r",
            ".dart", ".vue", ".svelte", ".gradle", ".cfg", ".conf", ".tex"}
MAX_SIDE = 1600


def is_wayland() -> bool:
    """True on a Wayland session — even when Qt runs through XWayland (where screen grabs come back black)."""
    return QGuiApplication.platformName().startswith("wayland") or bool(os.environ.get("WAYLAND_DISPLAY"))


def _mostly_black(img: QImage) -> bool:
    small = img.scaled(16, 16)
    return all(QColor(small.pixel(x, y)).value() < 8 for x in range(16) for y in range(16))


# ---------------------------------------------------------------- screen capture

def grab_screen(rect: QRect | None = None, screen=None) -> QImage | None:
    """Screenshot of the desktop (rect in global logical px). X11: Qt directly. Wayland: grim / spectacle / gnome-screenshot."""
    screen = screen or QGuiApplication.primaryScreen()
    if not is_wayland():
        geo = screen.geometry()
        if rect is not None:
            r = rect.intersected(geo)
            pm = screen.grabWindow(0, r.x() - geo.x(), r.y() - geo.y(), r.width(), r.height())
        else:
            pm = screen.grabWindow(0)
        if not pm.isNull() and not _mostly_black(pm.toImage()):
            return pm.toImage()
    tmp = Path(tempfile.gettempdir()) / "glass-shot.png"
    for cmd in (["grim", str(tmp)], ["spectacle", "-b", "-n", "-f", "-o", str(tmp)], ["gnome-screenshot", "-f", str(tmp)],
                ["import", "-window", "root", str(tmp)]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, timeout=8, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                img = QImage(str(tmp))
                if not img.isNull():
                    if rect:
                        dpr = img.width() / max(1, screen.geometry().width())
                        r = QRect(int(rect.x() * dpr), int(rect.y() * dpr), int(rect.width() * dpr), int(rect.height() * dpr))
                        img = img.copy(r)
                    return img
            except Exception:
                continue
    return None


# ---------------------------------------------------------------- glass

def render_glass(backdrop: QImage | None, w: int, h: int, radius: float, tint_hex: str, strength: float, blur: int, dpr: float) -> QImage:
    """Returns a w*h (device px) ARGB image of the glass panel."""
    from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient

    tint = QColor(tint_hex)
    out = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)

    base: QImage | None = None
    if backdrop is not None and not backdrop.isNull() and np is not None:
        base = _refract(backdrop, w, h, radius, blur, dpr)
    elif backdrop is not None and not backdrop.isNull():
        base = _cheap_blur(backdrop.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation), blur)

    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, w - 1, h - 1, radius, radius)
    p.setClipPath(path)
    if base is not None:
        p.drawImage(0, 0, base)
        c = QColor(tint); c.setAlphaF(min(0.95, strength))
        p.fillRect(0, 0, w, h, c)
    else:
        c = QColor(tint); c.setAlphaF(min(0.97, 0.55 + strength * 0.5))
        p.fillRect(0, 0, w, h, c)
    # glossy top
    g = QLinearGradient(0, 0, 0, h * 0.5)
    g.setColorAt(0, QColor(255, 255, 255, 24)); g.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(0, 0, w, h, g)
    p.setClipping(False)
    # rim light, brighter top-left
    from PySide6.QtGui import QPen
    rim = QLinearGradient(0, 0, w, h)
    rim.setColorAt(0, QColor(255, 255, 255, 190)); rim.setColorAt(0.4, QColor(255, 255, 255, 30))
    rim.setColorAt(0.62, QColor(255, 255, 255, 16)); rim.setColorAt(1, QColor(255, 255, 255, 120))
    p.setPen(QPen(rim, 1.2 * dpr)); p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return out


def _cheap_blur(img: QImage, radius: int) -> QImage:
    if radius <= 0:
        return img
    k = max(2, radius // 2)
    small = img.scaled(max(1, img.width() // k), max(1, img.height() // k), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(img.width(), img.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _to_array(img: QImage):
    img = img.convertToFormat(QImage.Format_RGB32)
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape(img.height(), img.bytesPerLine() // 4, 4)
    return arr[:, : img.width(), :3].astype(np.float32)  # BGR


def _box_blur(a, r: int):
    if r < 1:
        return a
    for axis in (0, 1):
        for _ in range(2):
            c = np.cumsum(np.pad(a, [(r + 1, r) if i == axis else (0, 0) for i in range(3)], mode="edge"), axis=axis)
            hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
            lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
            a = (hi - lo) / (2 * r + 1)
    return a


def _refract(backdrop: QImage, w: int, h: int, radius: float, blur: int, dpr: float) -> QImage:
    m = int(40 * dpr)  # margin: the backdrop includes m px around the panel so the rim can pull from outside
    src = _to_array(backdrop.scaled(w + 2 * m, h + 2 * m, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    src = _box_blur(src, int(blur * dpr * 0.5))

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    px, py = xs + 0.5 - w / 2, ys + 0.5 - h / 2
    r = min(radius, w / 2, h / 2)
    qx, qy = np.abs(px) - (w / 2 - r), np.abs(py) - (h / 2 - r)
    corner = (qx > 0) & (qy > 0)
    ln = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + 1e-6
    sd = np.where(corner, ln - r, np.maximum(qx, qy) - r)
    nx = np.where(corner, qx / ln * np.sign(px), np.where(qx > qy, np.sign(px), 0))
    ny = np.where(corner, qy / ln * np.sign(py), np.where(qx > qy, 0, np.sign(py)))
    d = -sd

    bezel, amp = 20 * dpr, 26 * dpr
    t = np.clip(1 - d / bezel, 0, 1)
    disp = amp * (1 - np.sqrt(1 - t * t))
    H, W = src.shape[:2]

    def sample(k, ch):
        sx = np.clip((xs + m + nx * disp * k).astype(np.int32), 0, W - 1)
        sy = np.clip((ys + m + ny * disp * k).astype(np.int32), 0, H - 1)
        return src[sy, sx, ch]

    b, g, rr = sample(0.86, 0), sample(1.0, 1), sample(1.14, 2)
    lum = 0.299 * rr + 0.587 * g + 0.114 * b
    rr, g, b = lum + (rr - lum) * 1.18, lum + (g - lum) * 1.18, lum + (b - lum) * 1.18

    lx, ly = -0.6, -0.8
    dirv = nx * lx + ny * ly
    lit = np.maximum(dirv, -dirv * 0.55)
    rim_w = 1.4 * dpr + 0.6
    rim = np.clip(1 - d / rim_w, 0, 1)
    spec = rim * (0.30 + 0.70 * lit) + t ** 3 * 0.26 * lit
    band = bezel * 1.8
    k = np.clip(1 - d / band, 0, 1)
    shade = k * k * (0.10 + 0.12 * np.maximum(0, -dirv))
    rgb = np.stack([b, g, rr], axis=-1) * (1 - shade)[..., None]
    rgb = rgb + (255 - rgb) * np.clip(spec, 0, 1)[..., None]
    alpha = np.clip(d + 0.5, 0, 1)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb * alpha[..., None], 0, 255).astype(np.uint8)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    img = QImage(out.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied)
    return img.copy()


def kde_blur_behind(win_id: int, enable: bool = True) -> None:
    """Ask KWin (X11) for live blur behind our window. Harmless elsewhere."""
    if is_wayland() or not shutil.which("xprop"):
        return
    try:
        if enable:
            subprocess.run(["xprop", "-id", str(win_id), "-f", "_KDE_NET_WM_BLUR_BEHIND_REGION", "32c",
                            "-set", "_KDE_NET_WM_BLUR_BEHIND_REGION", "0"], timeout=2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["xprop", "-id", str(win_id), "-remove", "_KDE_NET_WM_BLUR_BEHIND_REGION"], timeout=2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ---------------------------------------------------------------- attachments

def _encode(img: QImage, name: str) -> dict:
    if max(img.width(), img.height()) > MAX_SIDE:
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    png = img.hasAlphaChannel() and name.lower().endswith(".png")
    if not png:
        img = img.convertToFormat(QImage.Format_RGB888)
    img.save(buf, "PNG" if png else "JPEG", -1 if png else 88)
    data = bytes(ba)
    return {"name": name, "kind": "image", "media_type": "image/png" if png else "image/jpeg",
            "data": base64.b64encode(data).decode(), "bytes": len(data)}


def from_image(img: QImage, name: str) -> dict:
    return _encode(img, name)


def from_file(path: str) -> dict:
    p = Path(path)
    ext = p.suffix.lower()
    size = p.stat().st_size
    if ext in IMAGE_EXT:
        img = QImage(str(p))
        if img.isNull():
            raise RuntimeError(f"Couldn't read image {p.name}.")
        return _encode(img, p.name)
    if ext == ".pdf":
        if size > 30 * 1024 * 1024:
            raise RuntimeError(f"{p.name} is larger than 30 MB.")
        return {"name": p.name, "kind": "pdf", "media_type": "application/pdf", "data": base64.b64encode(p.read_bytes()).decode(), "bytes": size}
    raw = p.read_bytes()[: 400 * 1024 + 1]
    if ext in TEXT_EXT or (raw and b"\x00" not in raw[:4096]):
        if size > 400 * 1024:
            raise RuntimeError(f"{p.name} is too large to send as text (max 400 KB).")
        return {"name": p.name, "kind": "text", "media_type": "text/plain", "text": raw.decode("utf-8", "replace"), "bytes": size}
    raise RuntimeError(f"Can't attach {p.name} — use images, PDFs, or text/code files.")


def thumbnail(att: dict, size: int) -> QPixmap | None:
    if att.get("kind") != "image":
        return None
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(att["data"]))
    if pm.isNull():
        return None
    return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def size_text(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n // 1024} KB"
    return f"{n / 1048576:.1f} MB"
