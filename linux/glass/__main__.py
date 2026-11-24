"""Glass for Linux — entry point.

  python3 -m glass            start (or bring up the running copy)
  python3 -m glass --toggle   open/close the sidebar — bind this to a keyboard shortcut
"""
from __future__ import annotations

import os
import sys
import time

# Wayland doesn't let apps place their own windows (needed to slide in from the edge),
# so run through XWayland unless the user overrides it.
if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import store
from .panel import Panel

SOCKET = "glass-sidebar-" + str(os.getuid())


class FlickDetector:
    """Polls the cursor (~120 Hz). A fast slam into the left/right screen edge opens the panel.
    Works on X11; Wayland doesn't expose the global cursor, so use `glass --toggle` there."""

    def __init__(self, panel: Panel, settings: store.Settings):
        self.panel = panel
        self.s = settings
        self.samples: list[tuple[float, int]] = []
        self.was_edge = False
        self.last_fire = 0.0
        self.timer = QTimer()
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tick(self):
        now = time.monotonic()
        p = QCursor.pos()
        self.samples.append((now, p.x()))
        self.samples = [s for s in self.samples if now - s[0] < 0.15]
        scr = QGuiApplication.screenAt(p)
        if scr is None:
            return
        g = scr.geometry()
        side = -1 if p.x() <= g.left() + 1 else (1 if p.x() >= g.right() - 1 else 0)
        at_edge = side != 0
        if at_edge and not self.was_edge and now - self.last_fire > 0.7 and not QApplication.mouseButtons():
            old = next((s for s in self.samples if now - s[0] <= 0.09), None)
            if old:
                dt = max(0.001, now - old[0])
                travel = (p.x() - old[1]) * side
                k = max(0, min(2, int(self.s.sensitivity)))
                if travel / dt > g.width() * (2.4, 1.6, 1.05)[k] and travel > g.width() * (0.16, 0.10, 0.06)[k]:
                    self.last_fire = now
                    self.panel.on_swipe(side, scr)
        self.was_edge = at_edge


def orb_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(4, 4, 60, 60)
    g.setColorAt(0, QColor("#9AE6FF")); g.setColorAt(0.55, QColor("#B69CFF")); g.setColorAt(1, QColor("#FFA8D9"))
    p.setBrush(g); p.setPen(QColor(255, 255, 255, 200))
    p.drawEllipse(4, 4, 56, 56)
    p.setBrush(QColor(255, 255, 255, 170)); p.setPen(QColor(0, 0, 0, 0))
    p.drawEllipse(16, 12, 24, 13)
    p.end()
    return QIcon(pm)


def main() -> int:
    toggle_only = "--toggle" in sys.argv
    app = QApplication(sys.argv)

    # already running? hand the request over and quit
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if sock.waitForConnected(300):
        sock.write(b"toggle" if toggle_only else b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0

    app.setApplicationName("Glass")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(orb_icon())

    settings = store.Settings()
    panel = Panel(settings)

    def under_cursor():
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    server = QLocalServer()
    QLocalServer.removeServer(SOCKET)
    server.listen(SOCKET)

    def on_conn():
        c = server.nextPendingConnection()
        c.waitForReadyRead(300)
        msg = bytes(c.readAll()).decode()
        if msg == "toggle":
            panel.toggle(1, under_cursor())
        elif not panel.shown:
            panel.show_at(1, under_cursor())
        c.disconnectFromServer()
    server.newConnection.connect(on_conn)

    flick = FlickDetector(panel, settings)  # noqa: F841 (kept alive)

    tray = QSystemTrayIcon(orb_icon())
    tray.setToolTip("Glass — flick your cursor into a screen edge")
    menu = QMenu()
    a_open = QAction("Open Glass", menu); a_open.triggered.connect(lambda: panel.show_at(1, under_cursor()))
    a_quit = QAction("Quit", menu); a_quit.triggered.connect(app.quit)
    menu.addAction(a_open); menu.addSeparator(); menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and panel.toggle(1, under_cursor()))
    tray.show()

    if toggle_only or not settings.api_key:
        QTimer.singleShot(300, lambda: panel.show_at(1, under_cursor()))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
