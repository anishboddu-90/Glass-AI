"""The Glass panel for Linux: chat, settings, composer, model menu, chats pane."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeySequence, QPainter, QShortcut, QTextCursor
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from . import ai, effects, store
from .voice import Recorder, Speaker
from .widgets import (STYLE, Dots, FlowLayout, MarkdownView, Orb, Switch, Toast, VoiceBars, fade_in, fade_out,
                      icon_btn, label, pill, repolish, set_selected)

RADIUS = 30
WIDTH = 430
GAP = 12

TINTS = [("Semi-gray", "#5C5E64"), ("Graphite", "#1E2026"), ("Smoke", "#8C8E94"), ("Midnight", "#162246"),
         ("Ocean", "#124E76"), ("Violet", "#482C7C"), ("Rose", "#842C52"), ("Forest", "#1C523C"), ("Amber", "#805216")]


class Bridge(QObject):
    """Run callables on the GUI thread from worker threads."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda f: f())


def run_bg(bridge: Bridge, work, done=None, fail=None):
    def go():
        try:
            r = work()
            if done:
                bridge.call.emit(lambda: done(r))
        except Exception as e:  # noqa: BLE001
            if fail:
                msg = str(e)
                bridge.call.emit(lambda: fail(msg))
    threading.Thread(target=go, daemon=True).start()


# ====================================================================== input box

class InputEdit(QPlainTextEdit):
    submit = Signal()
    edit_last = Signal()
    got_image = Signal(QImage)
    got_files = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Input")
        self.setPlaceholderText("Ask anything…")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().contentsChanged.connect(self._grow)
        self._grow()

    def _grow(self):
        h = int(self.document().size().height() * self.fontMetrics().lineSpacing()) + 10
        self.setFixedHeight(max(30, min(170, h)))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
            return
        if e.key() == Qt.Key_Up and not self.toPlainText():
            self.edit_last.emit()
            return
        super().keyPressEvent(e)

    def canInsertFromMimeData(self, src):
        return src.hasImage() or src.hasUrls() or super().canInsertFromMimeData(src)

    def insertFromMimeData(self, src):
        if src.hasUrls() and all(u.isLocalFile() for u in src.urls()):
            self.got_files.emit([u.toLocalFile() for u in src.urls()])
        elif src.hasImage() and not src.hasText():
            self.got_image.emit(QImage(src.imageData()))
        else:
            super().insertFromMimeData(src)


# ====================================================================== messages

class UserMsg(QWidget):
    def __init__(self, panel, msg: dict, index: int):
        super().__init__()
        self.setAttribute(Qt.WA_Hover)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(44, 10, 0, 0)
        outer.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(4)
        outer.addLayout(col)
        if msg.get("attachments"):
            tray = QWidget()
            fl = FlowLayout(tray, 6)
            for a in msg["attachments"]:
                fl.addWidget(panel.attachment_tile(a, removable=False))
            col.addWidget(tray, 0, Qt.AlignRight)
        if msg.get("content"):
            bubble = QFrame()
            bubble.setObjectName("UserBubble")
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(15, 10, 15, 11)
            t = QLabel(msg["content"])
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            t.setMaximumWidth(max(200, panel.width() - 120))
            bl.addWidget(t)
            col.addWidget(bubble, 0, Qt.AlignRight)
        self.actions = QWidget()
        al = QHBoxLayout(self.actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.addStretch(1)
        e = icon_btn("✎", "Edit & resend", "Action")
        e.clicked.connect(lambda: panel.begin_edit(index))
        c = icon_btn("⧉", "Copy", "Action")
        c.clicked.connect(lambda: panel.copy(msg.get("content", ""), c))
        al.addWidget(e); al.addWidget(c)
        self.actions.setVisible(False)
        col.addWidget(self.actions)

    def enterEvent(self, e):
        self.actions.setVisible(True)
        fade_in(self.actions, 140)

    def leaveEvent(self, e):
        self.actions.setVisible(False)


class AssistantMsg(QWidget):
    def __init__(self, panel, msg: dict):
        super().__init__()
        self.panel = panel
        self.msg = msg
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 14, 4, 2)
        v.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(9)
        head.addWidget(Orb(18))
        head.addWidget(label(ai.label(msg.get("provider", "")), "Title"))
        m = label(msg.get("model", ""), "Dim")
        head.addWidget(m)
        head.addStretch(1)
        v.addLayout(head)
        self.body = MarkdownView()
        self.body.setContentsMargins(27, 0, 0, 0)
        self.body.setViewportMargins(27, 0, 0, 0)
        self.body.hide()
        v.addWidget(self.body)
        self.dots = Dots()
        dl = QHBoxLayout(); dl.setContentsMargins(27, 0, 0, 0); dl.addWidget(self.dots); dl.addStretch(1)
        self.dots_row = QWidget(); self.dots_row.setLayout(dl)
        v.addWidget(self.dots_row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #FFB4B4; padding-left: 27px;")
        self.error.hide()
        v.addWidget(self.error)
        self.actions = QWidget()
        self.al = QHBoxLayout(self.actions)
        self.al.setContentsMargins(22, 0, 0, 0)
        self.al.setSpacing(2)
        self.actions.hide()
        v.addWidget(self.actions)

    def show_text(self, text: str, cursor: bool = False):
        if self.dots_row.isVisible():
            self.dots_row.hide()
            self.body.show()
            fade_in(self.body, 200)
        self.body.set_markdown(text + (" ▍" if cursor else ""))

    def finish(self, is_last: bool):
        self.dots_row.hide()
        self.body.setVisible(bool(self.msg.get("content")))
        self.body.set_markdown(self.msg.get("content", ""))
        if self.msg.get("error"):
            self.error.setText("⚠  " + self.msg["error"])
            self.error.show()
        while self.al.count():
            it = self.al.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self.msg.get("content"):
            c = icon_btn("⧉", "Copy", "Action")
            c.clicked.connect(lambda: self.panel.copy(self.msg["content"], c))
            self.al.addWidget(c)
            s = icon_btn("🔊", "Read aloud", "Action")
            s.clicked.connect(lambda: self.panel.speak_toggle(self.msg["content"]))
            self.al.addWidget(s)
        if is_last:
            r = icon_btn("↻", "Regenerate", "Action")
            r.clicked.connect(self.panel.regenerate)
            self.al.addWidget(r)
        t = label(time.strftime("%-I:%M %p", time.localtime(self.msg.get("time", time.time()))), "Dim")
        t.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10.5px; padding-left: 6px;")
        self.al.addWidget(t)
        self.al.addStretch(1)
        self.actions.show()
        fade_in(self.actions, 220, 60)


# ====================================================================== panel

class Panel(QWidget):
    def __init__(self, settings: store.Settings):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.s = settings
        self.bridge = Bridge()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.side = 1
        self.screen_ = QGuiApplication.primaryScreen()
        self.full = False
        self.pinned = False
        self.shown = False
        self.backdrop: QImage | None = None
        self.glass: QImage | None = None
        self.glass_size = QSize()
        self.anim = QPropertyAnimation(self, b"geometry", self)

        self.chat = store.new_chat()
        self.chats = store.load_chats()
        self.pending: list[dict] = []
        self.editing = -1
        self.cancel: threading.Event | None = None
        self.streaming = False
        self.model_cache: dict[str, list] = {}
        self.voice_mode = False
        self.recorder = Recorder(self)
        self.speaker = Speaker(self)
        self.recorder.level.connect(lambda l: setattr(self.bars, "level", max(self.bars.level * 0.6, l)))
        self.recorder.finished.connect(self._on_speech)
        self.recorder.failed.connect(self._voice_failed)
        self.speaker.speaking_changed.connect(self._on_speaking)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.pane = self._build_pane()
        self.pane.hide()
        root.addWidget(self.pane)
        main = QWidget()
        root.addWidget(main, 1)
        mv = QVBoxLayout(main)
        mv.setContentsMargins(16, 12, 16, 16)
        mv.setSpacing(0)
        mv.addLayout(self._build_header())
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background: rgba(255,255,255,0.10);")
        mv.addWidget(line)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_chat_page())
        self.stack.addWidget(self._build_settings_page())
        mv.addWidget(self.stack, 1)
        self.composer = self._build_composer()
        self.composer_wrap = QWidget()
        cw = QHBoxLayout(self.composer_wrap); cw.setContentsMargins(0, 6, 0, 0); cw.addWidget(self.composer)
        mv.addWidget(self.composer_wrap)

        self.toast = Toast(self)
        self.menu = self._build_model_menu()
        self.drop = QLabel("⬇\nDrop to attach\nImages, PDFs, text and code", self)
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setStyleSheet("background: rgba(0,0,0,0.35); border: 2px dashed rgba(255,255,255,0.8); border-radius: 24px; font-size: 16px; font-weight: 600;")
        self.drop.hide()

        for seq, fn in (("Ctrl+N", self.new_chat), ("Ctrl+K", self.toggle_menu), ("Ctrl+,", lambda: self.show_settings(not self.in_settings)),
                        ("Ctrl+Shift+S", self.ask_screen), ("Ctrl+Shift+V", self.toggle_voice), ("Ctrl+O", self.pick_files),
                        ("F11", self.toggle_full), ("Escape", self.escape)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

        self.render_timer = QTimer(self)
        self.render_timer.setInterval(45)
        self.render_timer.timeout.connect(self._flush_stream)
        self.update_status()
        self.render_all()

    # ------------------------------------------------------------------ glass painting

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        dpr = self.devicePixelRatioF()
        want = QSize(int(self.width() * dpr), int(self.height() * dpr))
        if self.glass is None or (self.glass_size != want and self.anim.state() != QPropertyAnimation.Running):
            self.glass = effects.render_glass(self.backdrop, want.width(), want.height(), RADIUS * dpr, self.s.tint,
                                              self.s.tint_strength, int(self.s.blur), dpr)
            self.glass_size = want
        p.drawImage(self.rect(), self.glass)

    def refresh_glass(self, rect: QRect):
        """Snapshot what's behind `rect` (plus a margin for the rim refraction)."""
        m = 40
        r = rect.adjusted(-m, -m, m, m)
        self.backdrop = effects.grab_screen(r, self.screen_)
        self.glass = None
        self.update()

    def _rerender(self):
        self.glass = None
        self.update()

    # ------------------------------------------------------------------ geometry / motion

    def _sidebar_rect(self) -> QRect:
        a = self.screen_.availableGeometry()
        x = a.right() - GAP - WIDTH + 1 if self.side > 0 else a.left() + GAP
        return QRect(x, a.top() + GAP, WIDTH, a.height() - 2 * GAP)

    def _hidden_rect(self) -> QRect:
        r = self._sidebar_rect()
        return r.translated(self.side * (WIDTH + GAP + 40), 0)

    def _full_rect(self) -> QRect:
        return self.screen_.availableGeometry().adjusted(14, 14, -14, -14)

    def _animate(self, to: QRect, ms: int, curve, done=None):
        self.anim.stop()
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass
        self.anim.setDuration(ms)
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(to)
        self.anim.setEasingCurve(curve)

        def fin():
            self._rerender()
            if done:
                done()
        self.anim.finished.connect(fin)
        self.anim.start()

    def show_at(self, side: int, screen=None):
        self.side = side
        self.screen_ = screen or QGuiApplication.primaryScreen()
        self.full = False
        self.pane.hide()
        target = self._sidebar_rect()
        self.refresh_glass(target)          # snapshot before we're on screen
        self.setGeometry(self._hidden_rect())
        self.show()
        self.raise_()
        self.activateWindow()
        effects.kde_blur_behind(int(self.winId()))
        self.shown = True
        curve = QEasingCurve(QEasingCurve.OutBack)
        curve.setAmplitude(0.55)
        self._animate(target, 520, curve)
        self.focus_input()

    def hide_panel(self):
        if not self.shown:
            return
        self.shown = False
        self.close_menu()
        if self.full:
            self.full = False
            self.pane.hide()
        self._animate(self._hidden_rect(), 260, QEasingCurve(QEasingCurve.InCubic), self.hide)

    def toggle(self, side: int = 1, screen=None):
        if self.shown:
            self.hide_panel()
        else:
            self.show_at(side, screen)

    def toggle_full(self):
        if not self.shown:
            return
        self.full = not self.full
        target = self._full_rect() if self.full else self._sidebar_rect()
        # briefly go invisible so the snapshot shows the desktop, not us
        self.setWindowOpacity(0.0)

        def go():
            self.refresh_glass(target)
            self.setWindowOpacity(1.0)
            curve = QEasingCurve(QEasingCurve.OutBack)
            curve.setAmplitude(0.35)
            self._animate(target, 480, curve)
            self.pane.setVisible(self.full)
            if self.full:
                self.refresh_chat_list()
                fade_in(self.pane, 320, 120)
            self.full_btn.setText("⤡" if self.full else "⤢")
        QTimer.singleShot(90, go)

    def on_swipe(self, side: int, screen):
        if not self.shown:
            self.show_at(side, screen)
        elif self.full:
            return
        elif side == self.side:
            self.hide_panel()
        else:
            self.hide()
            self.shown = False
            self.show_at(side, screen)

    def escape(self):
        if self.menu.isVisible():
            self.close_menu()
        elif self.voice_mode:
            self.stop_voice()
        elif self.editing >= 0:
            self.cancel_edit()
        elif self.in_settings:
            self.show_settings(False)
        elif self.full:
            self.toggle_full()
        else:
            self.hide_panel()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.shown and not self.pinned \
                and not self.voice_mode and not getattr(self, "_dialog", False) and not self.menu.isVisible():
            QTimer.singleShot(150, lambda: (not self.isActiveWindow() and self.shown and not self.pinned) and self.hide_panel())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.drop.setGeometry(self.rect().adjusted(10, 10, -10, -10))
        if self.menu.isVisible():
            self._place_menu()

    # ------------------------------------------------------------------ header

    def _build_header(self):
        h = QHBoxLayout()
        h.setContentsMargins(4, 0, 0, 10)
        h.setSpacing(10)
        self.orb = Orb(22)
        h.addWidget(self.orb)
        col = QVBoxLayout(); col.setSpacing(0)
        self.title = label("Glass", "Title")
        self.subtitle = label("", "Dim")
        col.addWidget(self.title); col.addWidget(self.subtitle)
        h.addLayout(col, 1)
        for text, tip, fn in (("✎", "New chat (Ctrl+N)", self.new_chat), ("📌", "Pin (stay open)", self.toggle_pin),
                              ("⚙", "Settings (Ctrl+,)", lambda: self.show_settings(not self.in_settings))):
            b = icon_btn(text, tip)
            b.clicked.connect(fn)
            h.addWidget(b)
            if text == "📌":
                self.pin_btn = b
        self.full_btn = icon_btn("⤢", "Fullscreen (F11)")
        self.full_btn.clicked.connect(self.toggle_full)
        h.addWidget(self.full_btn)
        c = icon_btn("✕", "Close (Esc)")
        c.clicked.connect(self.hide_panel)
        h.addWidget(c)
        return h

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.pin_btn.setProperty("active", "true" if self.pinned else "false")
        repolish(self.pin_btn)
        self.toast.show_text("Pinned — Glass stays open" if self.pinned else "Unpinned")

    def update_status(self):
        has = bool(self.s.api_key)
        self.subtitle.setText(f"{ai.label(self.s.provider)} · {self.s.model}" if has else "Not connected")
        self.model_chip.setText(("●  " + self.s.model) if has else "Add API key")
        self.hint.setText("Drop in a file, paste a screenshot, or tap the mic to talk. Flick your cursor into a screen edge any time."
                          if has else "Add an API key in Settings (⚙ above) to get started.")

    # ------------------------------------------------------------------ chat page

    def _build_chat_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        self.chat_stack = QStackedWidget()
        v.addWidget(self.chat_stack)

        # welcome
        self.welcome = QWidget()
        wl = QVBoxLayout(self.welcome)
        wl.setContentsMargins(8, 0, 8, 0)
        wl.addStretch(1)
        wl.addWidget(Orb(46, glow=True))
        hour = time.localtime().tm_hour
        self.greet = label("Up late?" if hour < 5 else "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening", "H1")
        wl.addWidget(self.greet)
        wl.addWidget(label("How can I help?", "H2"))
        wl.addSpacing(18)
        chips = QWidget()
        self.chip_flow = FlowLayout(chips, 8)
        for text, prompt in (("▣  What's on my screen?", "@screen"), ("≡  Summarize something", "Summarize this in a few bullet points:\n"),
                             ("💡  Explain a concept", "Explain this simply, like I'm new to it: "),
                             ("✉  Draft a message", "Write a short, friendly message that "),
                             ("🐞  Debug some code", "Help me find the bug in this code:\n"), ("🎙  Talk to me", "@voice")):
            b = pill(text)
            b.clicked.connect(lambda _=False, p=prompt: self._suggest(p))
            self.chip_flow.addWidget(b)
        wl.addWidget(chips)
        self.hint = label("", "Dim", wrap=True)
        wl.addSpacing(10)
        wl.addWidget(self.hint)
        wl.addStretch(1)
        self.chat_stack.addWidget(self.welcome)

        # messages
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("Transparent")
        self.msgs = QVBoxLayout(holder)
        self.msgs.setContentsMargins(2, 8, 6, 12)
        self.msgs.setSpacing(0)
        self.msgs.addStretch(1)
        self.scroll.setWidget(holder)
        self.chat_stack.addWidget(self.scroll)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._maybe_follow)
        return page

    def _suggest(self, p: str):
        if p == "@screen":
            self.ask_screen()
        elif p == "@voice":
            self.toggle_voice()
        else:
            self.input.setPlainText(p)
            self.input.moveCursor(QTextCursor.End)
            self.focus_input()

    def _near_bottom(self) -> bool:
        sb = self.scroll.verticalScrollBar()
        return sb.maximum() - sb.value() < 90

    def _maybe_follow(self, _min, _max):
        if getattr(self, "_follow", True):
            self.scroll.verticalScrollBar().setValue(_max)

    def scroll_end(self):
        self._follow = True
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _add_widget(self, w: QWidget, animate=True):
        self.msgs.insertWidget(self.msgs.count() - 1, w)
        if animate:
            fade_in(w, 280)

    def render_all(self):
        while self.msgs.count() > 1:
            it = self.msgs.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        msgs = self.chat["messages"]
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                self._add_widget(UserMsg(self, m, i), animate=i >= len(msgs) - 4)
            else:
                w = AssistantMsg(self, m)
                self._add_widget(w, animate=i >= len(msgs) - 4)
                w.finish(i == len(msgs) - 1)
        self.chat_stack.setCurrentIndex(1 if msgs else 0)
        if not msgs:
            fade_in(self.welcome, 400)
        self.title.setText(self.chat["title"] if msgs else "Glass")
        self.scroll_end()

    # ------------------------------------------------------------------ chats

    def new_chat(self):
        self.stop_stream()
        self.speaker.stop()
        self.cancel_edit()
        self.chat = store.new_chat()
        self.clear_pending()
        self.show_settings(False)
        self.render_all()
        self.refresh_chat_list()
        self.focus_input()

    def persist(self, c: dict):
        if not c["messages"]:
            return
        if c["title"] == "New chat":
            first = next((m for m in c["messages"] if m["role"] == "user"), None)
            if first:
                c["title"] = store.make_title(first.get("content") or (first["attachments"][0]["name"] if first.get("attachments") else ""))
        c["provider"], c["model"] = self.s.provider, self.s.model
        store.save_chat(c)
        self.chats = [x for x in self.chats if x["id"] != c["id"]]
        self.chats.insert(0, c)
        self.chats = store.sort_chats(self.chats)
        if c is self.chat:
            self.title.setText(c["title"])
        self.refresh_chat_list()

    def smart_title(self, c: dict):
        if c.get("smart_titled") or len(c["messages"]) < 2:
            return
        c["smart_titled"] = True
        first = next((m for m in c["messages"] if m["role"] == "user" and m.get("content")), None)
        if not first:
            return
        prov, model, key, base = self.s.provider, self.s.model, self.s.api_key, self.s.base_url
        q = first["content"][:600]

        def done(t):
            t = (t or "").strip().strip("\"'.*#").replace("\n", " ")
            if 2 < len(t) < 60:
                c["title"] = t
                store.save_chat(c, touch=False)
                if c is self.chat:
                    self.title.setText(t)
                self.refresh_chat_list()
        run_bg(self.bridge, lambda: ai.quick(prov, model, key, base,
               "Write a 2-5 word title for a chat that starts with this message. Reply with only the title.\n\n" + q), done)

    # ------------------------------------------------------------------ sending / streaming

    def send(self):
        if self.streaming:
            self.stop_stream()
            return
        text = self.input.toPlainText().strip()
        if not text and not self.pending:
            return
        if not self.s.api_key:
            self.show_settings(True)
            self.key_status.setText("Add an API key first.")
            return
        self.speaker.stop()
        if self.editing >= 0:
            del self.chat["messages"][self.editing:]
            self.editing = -1
            self.edit_banner.hide()
            self.render_all()
        msg = {"role": "user", "content": text, "attachments": list(self.pending), "time": time.time()}
        self.input.clear()
        self.clear_pending()
        self.chat["messages"].append(msg)
        self.chat_stack.setCurrentIndex(1)
        self._add_widget(UserMsg(self, msg, len(self.chat["messages"]) - 1))
        self.persist(self.chat)
        self.scroll_end()
        self.run_reply()

    def regenerate(self):
        if self.streaming:
            return
        msgs = self.chat["messages"]
        if msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()
        if msgs and msgs[-1]["role"] == "user":
            self.render_all()
            self.run_reply()

    def begin_edit(self, index: int):
        if self.streaming or index >= len(self.chat["messages"]):
            return
        m = self.chat["messages"][index]
        self.editing = index
        self.input.setPlainText(m.get("content", ""))
        self.clear_pending()
        for a in m.get("attachments", []):
            self.add_pending(a)
        self.edit_banner.show()
        fade_in(self.edit_banner, 200)
        self.focus_input()

    def cancel_edit(self):
        if self.editing < 0:
            return
        self.editing = -1
        self.edit_banner.hide()
        self.input.clear()
        self.clear_pending()

    def run_reply(self):
        chat = self.chat
        reply = {"role": "assistant", "content": "", "provider": self.s.provider, "model": self.s.model, "time": time.time()}
        view = AssistantMsg(self, reply)
        self._add_widget(view)
        self.scroll_end()
        self.streaming = True
        self.orb.set_breathing(True)
        self._set_send(True)
        cancel = threading.Event()
        self.cancel = cancel
        self._buf: list[str] = []
        self._view = view
        self._dirty = False
        self.render_timer.start()
        history = [dict(m) for m in chat["messages"]]
        args = (self.s.provider, self.s.model, self.s.api_key, self.s.base_url, self.s.system_prompt)

        def on_delta(t):
            self._buf.append(t)
            self._dirty = True

        def finish(err):
            self.render_timer.stop()
            reply["content"] = "".join(self._buf)
            if cancel.is_set():
                reply["content"] += ("\n\n*Stopped.*" if reply["content"] else "*Stopped.*")
            if err:
                reply["error"] = err
            if reply["content"] or err:
                chat["messages"].append(reply)
                self.persist(chat)
            follow = self._near_bottom()
            view.finish(True)
            self.streaming = False
            self.cancel = None
            self.orb.set_breathing(False)
            self._set_send(False)
            if follow:
                self.scroll_end()
            spoke = False
            if not err and not cancel.is_set() and reply["content"]:
                if self.s.speak_replies or self.voice_mode:
                    self.speaker.speak(reply["content"])
                    spoke = Speaker.available()
                self.smart_title(chat)
            if self.voice_mode and not spoke:
                QTimer.singleShot(400, self.start_listening)

        def work():
            ai.stream(*args, history, on_delta, cancel)

        run_bg(self.bridge, work, lambda _: finish(None), finish)

    def _flush_stream(self):
        if self._dirty and self._view is not None:
            self._dirty = False
            self._follow = self._near_bottom()
            self._view.show_text("".join(self._buf), cursor=True)

    def stop_stream(self):
        if self.cancel:
            self.cancel.set()

    def _set_send(self, streaming: bool):
        self.send_btn.setText("■" if streaming else "↑")
        self.send_btn.setToolTip("Stop" if streaming else "Send (Enter)")
        self._update_send()

    def _update_send(self):
        self.send_btn.setEnabled(self.streaming or bool(self.input.toPlainText().strip()) or bool(self.pending))

    def copy(self, text: str, btn: QPushButton | None = None):
        QApplication.clipboard().setText(text or "")
        if btn is not None:
            old = btn.text()
            btn.setText("✓")
            QTimer.singleShot(1200, lambda: btn.setText(old))

    def speak_toggle(self, text: str):
        if not Speaker.available():
            self.toast.show_text("Install speech-dispatcher or espeak-ng to hear replies.")
        elif self.speaker.speaking:
            self.speaker.stop()
        else:
            self.speaker.speak(text)

    # ------------------------------------------------------------------ composer

    def _build_composer(self):
        box = QFrame()
        box.setObjectName("Composer")
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 10, 8, 8)
        v.setSpacing(6)

        self.edit_banner = QWidget()
        eb = QHBoxLayout(self.edit_banner); eb.setContentsMargins(4, 0, 0, 2)
        eb.addWidget(label("✎  Editing message — Enter to resend", "Dim"))
        eb.addStretch(1)
        x = icon_btn("✕", "Cancel edit", "Action"); x.clicked.connect(self.cancel_edit)
        eb.addWidget(x)
        self.edit_banner.hide()
        v.addWidget(self.edit_banner)

        self.tray = QWidget()
        self.tray_flow = FlowLayout(self.tray, 8)
        self.tray.hide()
        v.addWidget(self.tray)

        self.input = InputEdit()
        self.input.submit.connect(self.send)
        self.input.edit_last.connect(self._edit_last)
        self.input.got_image.connect(lambda img: (self.add_pending(effects.from_image(img, "Pasted image.jpg")), self.toast.show_text("Image pasted")))
        self.input.got_files.connect(self.attach_files)
        self.input.textChanged.connect(self._update_send)
        v.addWidget(self.input)

        self.voice_row = QWidget()
        vr = QHBoxLayout(self.voice_row); vr.setContentsMargins(4, 0, 0, 0)
        self.bars = VoiceBars()
        vr.addWidget(self.bars)
        self.voice_label = label("Listening…")
        vr.addWidget(self.voice_label, 1)
        self.voice_row.hide()
        v.addWidget(self.voice_row)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        a = icon_btn("📎", "Attach images, PDFs, files (or drop / paste) — Ctrl+O"); a.clicked.connect(self.pick_files)
        sc = icon_btn("▣", "Ask about my screen (Ctrl+Shift+S)"); sc.clicked.connect(self.ask_screen)
        bar.addWidget(a); bar.addWidget(sc)
        self.model_chip = pill("●  model")
        self.model_chip.setToolTip("Switch model (Ctrl+K)")
        self.model_chip.clicked.connect(self.toggle_menu)
        bar.addWidget(self.model_chip)
        bar.addStretch(1)
        self.mic_btn = icon_btn("🎙", "Voice mode (Ctrl+Shift+V)")
        self.mic_btn.clicked.connect(self.toggle_voice)
        bar.addWidget(self.mic_btn)
        self.send_btn = icon_btn("↑", "Send (Enter)", "Send")
        self.send_btn.clicked.connect(self.send)
        bar.addWidget(self.send_btn)
        v.addLayout(bar)
        self._update_send_later = True
        return box

    def _edit_last(self):
        idx = [i for i, m in enumerate(self.chat["messages"]) if m["role"] == "user"]
        if idx and not self.streaming:
            self.begin_edit(idx[-1])

    def focus_input(self):
        QTimer.singleShot(50, lambda: (self.activateWindow(), self.input.setFocus()) if not self.in_settings else None)

    # attachments
    def attachment_tile(self, a: dict, removable: bool) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        if a["kind"] == "image":
            lbl = QLabel()
            size = 64 if removable else 150
            pm = effects.thumbnail(a, size)
            if pm:
                lbl.setPixmap(pm.copy(0, 0, size, size if removable else 110))
            lbl.setFixedSize(size, size if removable else 110)
            lbl.setStyleSheet("border-radius: 14px; border: 1px solid rgba(255,255,255,0.3);")
            lbl.setToolTip(a["name"])
            lay.addWidget(lbl)
        else:
            chip = QFrame(); chip.setObjectName("Chip")
            cl = QHBoxLayout(chip); cl.setContentsMargins(6, 6, 12, 6); cl.setSpacing(10)
            ic = QLabel("PDF" if a["kind"] == "pdf" else "TXT")
            ic.setAlignment(Qt.AlignCenter); ic.setFixedSize(34, 34)
            ic.setStyleSheet(f"background: {'#E5484D' if a['kind'] == 'pdf' else '#5E8BFF'}; border-radius: 10px; font-size: 10px; font-weight: 700;")
            cl.addWidget(ic)
            col = QVBoxLayout(); col.setSpacing(0)
            n = QLabel(a["name"]); n.setMaximumWidth(150)
            col.addWidget(n)
            col.addWidget(label(("PDF" if a["kind"] == "pdf" else "Text") + " · " + effects.size_text(a.get("bytes", 0)), "Dim"))
            cl.addLayout(col)
            lay.addWidget(chip)
        if removable:
            x = icon_btn("✕", "Remove", "Action")
            x.clicked.connect(lambda: self.remove_pending(a, w))
            lay.addWidget(x, 0, Qt.AlignTop)
        return w

    def add_pending(self, a: dict | None):
        if not a:
            return
        self.pending.append(a)
        tile = self.attachment_tile(a, True)
        self.tray_flow.addWidget(tile)
        self.tray.show()
        fade_in(tile, 220)
        self._update_send()

    def remove_pending(self, a: dict, tile: QWidget):
        if a in self.pending:
            self.pending.remove(a)

        def gone():
            self.tray_flow.removeWidget(tile)
            tile.deleteLater()
            self.tray.setVisible(bool(self.pending))
        fade_out(tile, 140, gone)
        self._update_send()

    def clear_pending(self):
        self.pending.clear()
        self.tray_flow.clear()
        self.tray.hide()
        self.input.setPlaceholderText("Ask anything…")
        self._update_send()

    def attach_files(self, paths):
        for p in paths:
            try:
                self.add_pending(effects.from_file(p))
            except Exception as e:  # noqa: BLE001
                self.toast.show_text(str(e))
        self.focus_input()

    def pick_files(self):
        self._dialog = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", "Images, PDFs, text & code (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf *.txt *.md *.csv *.json *.py *.js *.ts *.html *.css *.c *.cpp *.rs *.go *.java *.sh *.log);;All files (*)")
        finally:
            self._dialog = False
        self.activateWindow()
        if paths:
            self.attach_files(paths)

    def ask_screen(self):
        if not self.shown:
            return
        self.show_settings(False)
        # step out of the way, grab, come back
        self.setWindowOpacity(0.0)

        def grab():
            img = effects.grab_screen(None, self.screen_)
            self.setWindowOpacity(1.0)
            if img is None or img.isNull():
                self.toast.show_text("Couldn't capture the screen (install grim, spectacle or gnome-screenshot on Wayland).")
                return
            self.add_pending(effects.from_image(img, time.strftime("Screen %H:%M.jpg")))
            if not self.input.toPlainText().strip():
                self.input.setPlaceholderText("Ask about your screen…")
            self.toast.show_text("Screenshot attached — ask anything about it")
            self.focus_input()
        QTimer.singleShot(120, grab)

    # drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.setGeometry(self.rect().adjusted(10, 10, -10, -10))
            self.drop.show(); self.drop.raise_()
            fade_in(self.drop, 160)

    def dragLeaveEvent(self, e):
        self.drop.hide()

    def dropEvent(self, e):
        self.drop.hide()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.show_settings(False)
            self.attach_files(paths)

    # ------------------------------------------------------------------ voice mode

    def toggle_voice(self):
        if self.voice_mode:
            self.stop_voice()
            return
        vp = ai.voice_provider(self.s.keyed_providers())
        if vp is None:
            self.toast.show_text("Voice input uses Whisper — add a Groq or OpenAI key in Settings.")
            return
        self.voice_mode = True
        self.toast.show_text("Voice mode — just talk. Pause to send, Esc to stop.")
        self.start_listening()

    def start_listening(self):
        if not self.voice_mode or not self.shown:
            return
        self.speaker.stop()
        self.recorder.start()
        if self.recorder.active:
            self.input.hide()
            self.voice_row.show()
            self.voice_label.setText("Listening…")
            self.bars.start()
            self.mic_btn.setProperty("active", "true")
            repolish(self.mic_btn)

    def _voice_ui_off(self):
        self.bars.stop()
        self.voice_row.hide()
        self.input.show()
        self.mic_btn.setProperty("active", "false")
        repolish(self.mic_btn)

    def stop_voice(self):
        self.voice_mode = False
        self.recorder.stop(send=False)
        self.speaker.stop()
        self._voice_ui_off()
        self.focus_input()

    def _voice_failed(self, msg: str):
        self.voice_mode = False
        self._voice_ui_off()
        self.toast.show_text(msg)

    def _on_speech(self, wav: bytes):
        self.voice_label.setText("Transcribing…")
        vp = ai.voice_provider(self.s.keyed_providers())
        key, base = self.s.key_for(vp), self.s.base_url

        def done(text):
            self._voice_ui_off()
            if text:
                self.input.setPlainText(text)
                self.send()
            elif self.voice_mode:
                self.start_listening()

        def fail(msg):
            self._voice_ui_off()
            self.voice_mode = False
            self.toast.show_text(msg)
        run_bg(self.bridge, lambda: ai.transcribe(wav, vp, key, base), done, fail)

    def _on_speaking(self, speaking: bool):
        if not speaking and self.voice_mode and not self.streaming:
            QTimer.singleShot(250, self.start_listening)

    # ------------------------------------------------------------------ model menu (Ctrl+K)

    def _build_model_menu(self):
        m = QFrame(self)
        m.setObjectName("Menu")
        m.setFixedWidth(300)
        v = QVBoxLayout(m)
        v.setContentsMargins(8, 8, 8, 8)
        self.menu_filter = QLineEdit()
        self.menu_filter.setPlaceholderText("Search or type a model…")
        self.menu_filter.textChanged.connect(self.build_menu)
        self.menu_filter.returnPressed.connect(self._menu_enter)
        v.addWidget(self.menu_filter)
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setMaximumHeight(340)
        holder = QWidget(); holder.setObjectName("Transparent")
        self.menu_list = QVBoxLayout(holder); self.menu_list.setContentsMargins(0, 4, 0, 0); self.menu_list.setSpacing(1)
        sa.setWidget(holder)
        v.addWidget(sa)
        self.menu_status = label("", "Dim", wrap=True)
        v.addWidget(self.menu_status)
        m.hide()
        return m

    def _place_menu(self):
        self.menu.adjustSize()
        x = self.composer_wrap.mapTo(self, QPoint(0, 0)).x() + 6
        y = self.composer_wrap.mapTo(self, QPoint(0, 0)).y() - self.menu.height() - 6
        self.menu.move(x, max(60, y))

    def toggle_menu(self):
        if self.menu.isVisible():
            self.close_menu()
            return
        self.show_settings(False)
        self.menu_filter.clear()
        self.build_menu()
        self._place_menu()
        self.menu.show(); self.menu.raise_()
        fade_in(self.menu, 160)
        self.menu_filter.setFocus()
        for p in ("gemini", "groq"):
            if p not in self.model_cache and self.s.has_key(p):
                key = self.s.key_for(p)

                def done(lst, p=p):
                    self.model_cache[p] = lst
                    if self.menu.isVisible():
                        self.build_menu()
                run_bg(self.bridge, lambda p=p, key=key: ai.list_models(p, key), done, lambda _m, p=p: self.model_cache.__setitem__(p, []))

    def close_menu(self):
        if self.menu.isVisible():
            self.menu.hide()
            self.focus_input()

    def build_menu(self):
        while self.menu_list.count():
            it = self.menu_list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        q = self.menu_filter.text().strip().lower()
        seen, shown = set(), 0

        def match(p, text):
            return not q or q in text.lower() or q in ai.label(p).lower()

        def add_header(t):
            self.menu_list.addWidget(label(t, "Dim"))

        recents = [r.split("|", 1) for r in self.s.recent_models if "|" in r]
        recents = [r for r in recents if self.s.has_key(r[0]) and match(r[0], r[1])]
        if recents:
            add_header("Recent")
            for p, mdl in recents:
                self.menu_list.addWidget(self._menu_item(p, mdl, mdl))
                seen.add((p, mdl)); shown += 1
        for p in ("anthropic", "gemini", "groq", "openai"):
            if not self.s.has_key(p):
                continue
            models = [(m, m) for m in ai.CLAUDE_MODELS] if p == "anthropic" else list(self.model_cache.get(p, []))
            if p == self.s.provider and all(m[0] != self.s.model for m in models):
                models.insert(0, (self.s.model, self.s.model))
            models = [m for m in models if (p, m[0]) not in seen and match(p, m[0] + " " + m[1])][:40]
            if not models:
                continue
            add_header(ai.label(p))
            for mid, name in models:
                self.menu_list.addWidget(self._menu_item(p, mid, name))
                shown += 1
        if shown == 0 and q:
            self.menu_status.setText(f'Press Enter to use "{q}" with {ai.label(self.s.provider)}.')
        else:
            self.menu_status.setText("Add more providers' keys in Settings to see them here.")
        if self.menu.isVisible():
            self._place_menu()

    def _menu_item(self, p, mid, name):
        cur = p == self.s.provider and mid == self.s.model
        b = QPushButton(("✓  " if cur else "     ") + name)
        b.setObjectName("Row")
        b.setProperty("selected", "true" if cur else "false")
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(mid)
        b.clicked.connect(lambda: self.switch_model(p, mid))
        b._target = (p, mid)
        return b

    def _menu_enter(self):
        for i in range(self.menu_list.count()):
            w = self.menu_list.itemAt(i).widget()
            if isinstance(w, QPushButton) and hasattr(w, "_target"):
                self.switch_model(*w._target)
                return
        t = self.menu_filter.text().strip()
        if t:
            self.switch_model(self.s.provider, t)

    def switch_model(self, p: str, mid: str):
        self.s.set(provider=p, model=mid)
        self.s.remember_model(mid)
        self.s.save()
        self.update_status()
        self.close_menu()
        self.toast.show_text(f"Now using {ai.label(p)} · {mid}")

    # ------------------------------------------------------------------ settings page

    @property
    def in_settings(self) -> bool:
        return self.stack.currentIndex() == 1

    def show_settings(self, show: bool):
        if show == self.in_settings:
            return
        self.close_menu()
        if show:
            self._load_settings_ui()
        self.stack.setCurrentIndex(1 if show else 0)
        self.composer_wrap.setVisible(not show)
        fade_in(self.stack.currentWidget(), 260)
        if not show:
            self.focus_input()

    def _card(self, title: str):
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(16, 14, 16, 16); v.setSpacing(6)
        v.addWidget(label(title, "CardTitle"))
        return card, v

    def _build_settings_page(self):
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget(); holder.setObjectName("Transparent")
        v = QVBoxLayout(holder); v.setContentsMargins(0, 12, 4, 12); v.setSpacing(12)
        top = QHBoxLayout()
        h = label("Settings", "H1"); h.setStyleSheet("font-size: 22px; font-weight: 600;")
        top.addWidget(h); top.addStretch(1)
        done = pill("Done"); done.clicked.connect(lambda: self.show_settings(False))
        top.addWidget(done)
        v.addLayout(top)

        # provider
        card, c = self._card("AI provider")
        c.addWidget(label("API key", "Dim"))
        self.key_edit = QLineEdit(); self.key_edit.setEchoMode(QLineEdit.Password); self.key_edit.setPlaceholderText("Paste your key")
        self.key_edit.textEdited.connect(self._key_typed)
        c.addWidget(self.key_edit)
        row = QHBoxLayout()
        for t, fn in (("Import from file…", self._import_key), ("Paste", self._paste_key), ("Remove", lambda: (self.key_edit.clear(), self.key_status.setText("Key will be removed when you save.")))):
            b = pill(t); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(1)
        c.addLayout(row)
        self.key_status = label("", "Dim", wrap=True)
        c.addWidget(self.key_status)
        c.addWidget(label("Provider", "Dim"))
        pw = QWidget(); pf = FlowLayout(pw, 6)
        self.prov_btns = {}
        for p, t in (("anthropic", "Anthropic (Claude)"), ("gemini", "Google Gemini"), ("groq", "Groq"), ("openai", "OpenAI-compatible")):
            b = pill(t); b.clicked.connect(lambda _=False, p=p: self._set_provider(p, swap=True)); pf.addWidget(b); self.prov_btns[p] = b
        c.addWidget(pw)
        self.models_box = QWidget()
        mb = QVBoxLayout(self.models_box); mb.setContentsMargins(0, 6, 0, 0)
        mh = QHBoxLayout(); self.models_title = label("Models", "Dim"); mh.addWidget(self.models_title); mh.addStretch(1)
        rf = pill("Refresh"); rf.clicked.connect(lambda: self._load_models(force=True)); mh.addWidget(rf)
        mb.addLayout(mh)
        self.models_status = label("", "Dim", wrap=True); mb.addWidget(self.models_status)
        mw = QWidget(); self.models_flow = FlowLayout(mw, 6); mb.addWidget(mw)
        c.addWidget(self.models_box)
        c.addWidget(label("Model", "Dim"))
        self.model_edit = QLineEdit(); self.model_edit.textChanged.connect(self._highlight_models)
        c.addWidget(self.model_edit)
        self.base_box = QWidget(); bb = QVBoxLayout(self.base_box); bb.setContentsMargins(0, 0, 0, 0)
        bb.addWidget(label("Base URL (OpenAI, OpenRouter, Ollama, LM Studio…)", "Dim"))
        self.base_edit = QLineEdit(); bb.addWidget(self.base_edit)
        c.addWidget(self.base_box)
        v.addWidget(card)

        # glass
        card, c = self._card("Glass")
        c.addWidget(label("Tint", "Dim"))
        sw = QWidget(); sf = FlowLayout(sw, 6)
        self.swatches = []
        for name, hexv in TINTS:
            b = QPushButton(); b.setFixedSize(34, 34); b.setToolTip(name); b.setCursor(Qt.PointingHandCursor)
            b._hex = hexv
            b.clicked.connect(lambda _=False, h=hexv: self._set_tint(h))
            sf.addWidget(b); self.swatches.append(b)
        c.addWidget(sw)
        self.hex_edit = QLineEdit(); self.hex_edit.setFixedWidth(110); self.hex_edit.setPlaceholderText("#5C5E64")
        self.hex_edit.returnPressed.connect(lambda: self._set_tint(self.hex_edit.text()))
        hr = QHBoxLayout(); hr.addWidget(self.hex_edit); hr.addWidget(label("Custom hex — press Enter", "Dim")); hr.addStretch(1)
        c.addLayout(hr)
        self.tint_label = label("", "Dim")
        c.addWidget(self.tint_label)
        self.tint_slider = QSlider(Qt.Horizontal); self.tint_slider.setRange(0, 85)
        self.tint_slider.valueChanged.connect(self._tint_strength)
        c.addWidget(self.tint_slider)
        self.blur_label = label("", "Dim")
        c.addWidget(self.blur_label)
        self.blur_slider = QSlider(Qt.Horizontal); self.blur_slider.setRange(0, 40)
        self.blur_slider.valueChanged.connect(self._blur_changed)
        c.addWidget(self.blur_slider)
        reset = pill("Reset to semi-gray"); reset.clicked.connect(self._reset_glass)
        c.addWidget(reset, 0, Qt.AlignLeft)
        v.addWidget(card)

        # voice
        card, c = self._card("Voice")
        r = QHBoxLayout()
        col = QVBoxLayout(); col.addWidget(label("Read replies aloud")); col.addWidget(label("Uses speech-dispatcher or espeak-ng", "Dim"))
        r.addLayout(col, 1)
        self.speak_switch = Switch(); self.speak_switch.toggled.connect(lambda on: (self.s.set(speak_replies=on), self.s.save()))
        r.addWidget(self.speak_switch)
        c.addLayout(r)
        c.addWidget(label("Voice mode transcribes with Whisper using your Groq or OpenAI key.", "Dim", wrap=True))
        v.addWidget(card)

        # behaviour
        card, c = self._card("Behavior")
        c.addWidget(label("Swipe sensitivity (X11)", "Dim"))
        sr = QHBoxLayout(); self.sens_btns = []
        for i, t in enumerate(("Hard flick", "Normal", "Light")):
            b = pill(t); b.clicked.connect(lambda _=False, i=i: self._set_sens(i)); sr.addWidget(b); self.sens_btns.append(b)
        sr.addStretch(1)
        c.addLayout(sr)
        c.addWidget(label("Custom instructions", "Dim"))
        self.sys_edit = QPlainTextEdit(); self.sys_edit.setObjectName("Field"); self.sys_edit.setFixedHeight(90)
        c.addWidget(self.sys_edit)
        v.addWidget(card)

        save = QPushButton("Save changes"); save.setObjectName("Primary"); save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save_settings)
        v.addWidget(save)
        v.addWidget(label("Glass and voice settings apply instantly. Shortcuts: Ctrl+N new chat · Ctrl+K switch model · Ctrl+Shift+S ask about screen · "
                          "Ctrl+Shift+V voice · F11 fullscreen · Esc close. Bind `glass --toggle` to a key in your desktop settings.", "Dim", wrap=True))
        v.addStretch(1)
        sa.setWidget(holder)
        return sa

    def _load_settings_ui(self):
        self._draft = self.s.provider
        self.key_edit.setText(self.s.api_key)
        self.key_status.setText("Key saved." if self.s.api_key else "No key saved yet.")
        self.model_edit.setText(self.s.model)
        self.base_edit.setText(self.s.base_url)
        self.sys_edit.setPlainText(self.s.system_prompt)
        self._set_provider(self.s.provider, swap=False, keep_key=True)
        self._set_sens(self.s.sensitivity, save=False)
        self.speak_switch.setChecked(bool(self.s.speak_replies))
        self._sync_glass_ui()

    def _set_provider(self, p: str, swap: bool, keep_key: bool = False):
        changed = p != getattr(self, "_draft", None)
        if changed and not keep_key:
            self.key_edit.setText(self.s.key_for(p))
            self.key_status.setText(f"Using your saved {ai.label(p)} key." if self.key_edit.text() else f"No {ai.label(p)} key saved yet.")
        if swap and changed:
            self.model_edit.setText(ai.ANTHROPIC_DEFAULT if p == "anthropic" else ai.GEMINI_DEFAULT if p == "gemini" else "")
        self._draft = p
        for k, b in self.prov_btns.items():
            set_selected(b, k == p)
        self.base_box.setVisible(p == "openai")
        self.models_box.setVisible(p in ("gemini", "groq"))
        if p in ("gemini", "groq"):
            self.models_title.setText(f"{ai.label(p)} models")
            self._load_models(force=changed)

    def _load_models(self, force=False):
        p = self._draft
        key = self.key_edit.text().strip()
        self.models_flow.clear()
        if not key:
            self.models_status.setText(f"Add your {ai.label(p)} key above, then hit Refresh to load every model.")
            return
        self.models_status.setText(f"Loading {ai.label(p)} models…")

        def done(lst):
            if self._draft != p:
                return
            self.models_flow.clear()
            for i, (mid, name) in enumerate(lst):
                b = pill(name, mid == self.model_edit.text().strip()); b.setToolTip(mid); b._mid = mid
                b.clicked.connect(lambda _=False, m=mid: self.model_edit.setText(m))
                self.models_flow.addWidget(b)
                if i < 30:
                    fade_in(b, 200, i * 15)
            if lst and all(m[0] != self.model_edit.text().strip() for m in lst) and (p == "groq" or not self.model_edit.text().strip()):
                self.model_edit.setText(lst[0][0])
            self.models_status.setText(f"{len(lst)} models available. Tap one to use it.")
            self.model_cache[p] = lst
        run_bg(self.bridge, lambda: ai.list_models(p, key), done, lambda m: self.models_status.setText(m))

    def _highlight_models(self):
        cur = self.model_edit.text().strip()
        for i in range(self.models_flow.count()):
            w = self.models_flow.itemAt(i).widget()
            if w is not None and hasattr(w, "_mid"):
                set_selected(w, w._mid == cur)

    def _key_typed(self, text):
        k = ai.extract_key(text) or text.strip()
        p = ai.provider_for_key(k)
        if p and p != self._draft and not (p == "openai" and self._draft == "openai"):
            self._set_provider(p, swap=True, keep_key=True)

    def _accept_key(self, k: str, how: str):
        self.key_edit.setText(k)
        p = ai.provider_for_key(k)
        if p:
            self._set_provider(p, swap=True, keep_key=True)
        self.key_status.setText(f"{how} Looks like {'a ' + ai.label(p) if p else 'an OpenAI-compatible'} key — hit Save.")

    def _paste_key(self):
        k = ai.extract_key(QApplication.clipboard().text())
        if k:
            self._accept_key(k, "Pasted from clipboard.")
        else:
            self.key_status.setText("Clipboard doesn't contain an API key.")

    def _import_key(self):
        self._dialog = True
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Import API key", "", "Key files (*.txt *.env *.json *.key);;All files (*)")
        finally:
            self._dialog = False
        if not path:
            return
        try:
            k = ai.extract_key(open(path, encoding="utf-8", errors="replace").read())
        except OSError as e:
            self.key_status.setText(f"Couldn't read file: {e}")
            return
        if k:
            self._accept_key(k, f"Imported from {path.rsplit('/', 1)[-1]}.")
        else:
            self.key_status.setText("Couldn't find an API key in that file.")

    def _set_sens(self, i: int, save: bool = True):
        for j, b in enumerate(self.sens_btns):
            set_selected(b, j == i)
        self._draft_sens = i

    def _save_settings(self):
        model = self.model_edit.text().strip()
        if not model:
            self.key_status.setText("Enter a model name (or pick one from the list).")
            return
        p = self._draft
        self.s.set_key(p, self.key_edit.text().strip())
        self.s.set(provider=p, model=model, base_url=self.base_edit.text().strip() or "https://api.openai.com/v1",
                   system_prompt=self.sys_edit.toPlainText(), sensitivity=getattr(self, "_draft_sens", self.s.sensitivity))
        self.s.remember_model(model)
        self.s.save()
        self.update_status()
        self.show_settings(False)
        self.toast.show_text(f"Saved · {ai.label(p)} · {model}")

    # glass controls
    def _sync_glass_ui(self):
        for b in self.swatches:
            sel = b._hex.upper() == self.s.tint.upper()
            b.setStyleSheet(f"background: {b._hex}; border-radius: 17px; border: {'2px solid white' if sel else '1px solid rgba(255,255,255,0.35)'};")
        self.hex_edit.setText(self.s.tint)
        self.tint_slider.blockSignals(True); self.tint_slider.setValue(int(self.s.tint_strength * 100)); self.tint_slider.blockSignals(False)
        self.blur_slider.blockSignals(True); self.blur_slider.setValue(int(self.s.blur)); self.blur_slider.blockSignals(False)
        self.tint_label.setText(f"Tint strength  ·  {round(self.s.tint_strength / 0.85 * 100)}%")
        self.blur_label.setText(f"Blur  ·  {'Off' if self.s.blur <= 0 else str(int(self.s.blur)) + ' px'}")

    def _glass_changed(self):
        self._sync_glass_ui()
        self.s.save()
        self._rerender()

    def _set_tint(self, h: str):
        h = h.strip()
        if not h.startswith("#"):
            h = "#" + h
        if QColor(h).isValid() and len(h) in (4, 7):
            self.s.set(tint=QColor(h).name().upper())
        self._glass_changed()

    def _tint_strength(self, v):
        self.s.set(tint_strength=v / 100.0)
        self._glass_changed()

    def _blur_changed(self, v):
        self.s.set(blur=v)
        self._glass_changed()

    def _reset_glass(self):
        self.s.set(tint=store.DEFAULTS["tint"], tint_strength=store.DEFAULTS["tint_strength"], blur=store.DEFAULTS["blur"])
        self._glass_changed()
        self.toast.show_text("Glass reset to semi-gray")

    # ------------------------------------------------------------------ chats pane (fullscreen)

    def _build_pane(self):
        pane = QFrame(); pane.setObjectName("Pane"); pane.setFixedWidth(284)
        v = QVBoxLayout(pane); v.setContentsMargins(14, 18, 12, 14); v.setSpacing(8)
        top = QHBoxLayout(); top.addWidget(Orb(26)); t = label("Glass"); t.setStyleSheet("font-size: 17px; font-weight: 600;")
        top.addWidget(t); top.addStretch(1)
        v.addLayout(top)
        nb = QPushButton("＋  New chat            Ctrl+N"); nb.setObjectName("Pill"); nb.setCursor(Qt.PointingHandCursor)
        nb.setStyleSheet("padding: 10px 14px; font-weight: 600; text-align: left;")
        nb.clicked.connect(self.new_chat)
        v.addWidget(nb)
        self.search = QLineEdit(); self.search.setPlaceholderText("🔍  Search chats")
        self.search.textChanged.connect(self.refresh_chat_list)
        v.addWidget(self.search)
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget(); holder.setObjectName("Transparent")
        self.list_lay = QVBoxLayout(holder); self.list_lay.setContentsMargins(0, 0, 0, 0); self.list_lay.setSpacing(1)
        self.list_lay.addStretch(1)
        sa.setWidget(holder)
        v.addWidget(sa, 1)
        return pane

    def refresh_chat_list(self):
        if not hasattr(self, "list_lay"):
            return
        while self.list_lay.count() > 1:
            it = self.list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        q = self.search.text().strip().lower()
        shown = [c for c in self.chats if not q or q in c["title"].lower() or any(q in (m.get("content") or "").lower() for m in c["messages"])]
        if not shown:
            self.list_lay.insertWidget(0, label("No chats match." if q else "Your chats will show up here.", "Dim"))
            return
        last = None
        i = 0
        for c in shown:
            b = store.bucket(c)
            if b != last:
                self.list_lay.insertWidget(self.list_lay.count() - 1, label(b, "Dim"))
                last = b
            self.list_lay.insertWidget(self.list_lay.count() - 1, self._chat_row(c))
            i += 1

    def _chat_row(self, c: dict) -> QWidget:
        row = QPushButton()
        row.setObjectName("Row")
        row.setProperty("selected", "true" if c["id"] == self.chat["id"] else "false")
        row.setCursor(Qt.PointingHandCursor)
        row.setMinimumHeight(48)
        lay = QHBoxLayout(row); lay.setContentsMargins(10, 6, 4, 6)
        col = QVBoxLayout(); col.setSpacing(1)
        t = QLabel(c["title"]); t.setStyleSheet("font-size: 13px;"); t.setAttribute(Qt.WA_TransparentForMouseEvents)
        d = label(f"{store.relative(c['updated'])} · {ai.label(c.get('provider', ''))}", "Dim"); d.setAttribute(Qt.WA_TransparentForMouseEvents)
        col.addWidget(t); col.addWidget(d)
        lay.addLayout(col, 1)
        tools = QWidget(); tl = QHBoxLayout(tools); tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(0)
        pin = icon_btn("★" if c.get("pinned") else "☆", "Unpin" if c.get("pinned") else "Pin to top", "Action")
        exp = icon_btn("⧉", "Copy chat as Markdown", "Action")
        dele = icon_btn("🗑", "Delete chat", "Action")
        for b in (pin, exp, dele):
            tl.addWidget(b)
        tools.setVisible(False)
        lay.addWidget(tools)
        row.enterEvent = lambda e: tools.setVisible(True)
        row.leaveEvent = lambda e: tools.setVisible(False)
        row.clicked.connect(lambda: self.open_chat(c))

        def toggle_pin():
            c["pinned"] = not c.get("pinned")
            store.save_chat(c, touch=False)
            self.chats = store.sort_chats(self.chats)
            self.refresh_chat_list()
        pin.clicked.connect(toggle_pin)
        exp.clicked.connect(lambda: (QApplication.clipboard().setText(store.export_markdown(c, ai.label)), self.toast.show_text("Chat copied as Markdown")))

        def delete():
            store.delete_chat(c)
            self.chats = [x for x in self.chats if x["id"] != c["id"]]
            if c["id"] == self.chat["id"]:
                self.new_chat()
            else:
                self.refresh_chat_list()
            self.toast.show_text("Chat deleted")
        dele.clicked.connect(delete)
        return row

    def open_chat(self, c: dict):
        if c is self.chat:
            return
        self.stop_stream()
        self.speaker.stop()
        self.cancel_edit()
        self.chat = c
        self.clear_pending()
        self.show_settings(False)
        self.render_all()
        self.refresh_chat_list()
        self.focus_input()
