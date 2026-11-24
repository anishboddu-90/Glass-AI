"""Reusable widgets + styling for the Linux port."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Property,
                            QParallelAnimationGroup, Signal)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QTextOption
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QLabel, QLayout, QSizePolicy, QTextBrowser, QWidget,
                               QAbstractButton, QPushButton)

FONT = "Inter, 'SF Pro Text', 'Cantarell', 'Noto Sans', 'Segoe UI', sans-serif"

STYLE = f"""
* {{ font-family: {FONT}; color: rgba(255,255,255,0.95); font-size: 13.5px; }}
QWidget#Transparent, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 1px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.22); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.38); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QToolTip {{ background: rgba(28,30,36,0.96); color: white; border: 1px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 5px 8px; }}

QPushButton#Icon {{ background: transparent; border: 1px solid transparent; border-radius: 16px;
    min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; font-size: 15px; }}
QPushButton#Icon:hover {{ background: rgba(255,255,255,0.15); border-color: rgba(255,255,255,0.18); }}
QPushButton#Icon:pressed {{ background: rgba(255,255,255,0.25); }}
QPushButton#Icon[active="true"] {{ background: #FF453A; border-color: #FF453A; }}
QPushButton#Icon:disabled {{ color: rgba(255,255,255,0.3); }}

QPushButton#Action {{ background: transparent; border: none; border-radius: 8px; color: rgba(255,255,255,0.55);
    min-width: 28px; max-width: 28px; min-height: 26px; max-height: 26px; font-size: 13px; }}
QPushButton#Action:hover {{ background: rgba(255,255,255,0.13); color: white; }}

QPushButton#Send {{ background: rgba(255,255,255,0.95); color: #111318; border: none; border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; font-size: 16px; font-weight: 700; }}
QPushButton#Send:hover {{ background: white; }}
QPushButton#Send:disabled {{ background: rgba(255,255,255,0.2); color: rgba(255,255,255,0.5); }}
QPushButton#Primary {{ background: rgba(255,255,255,0.95); color: #111318; border: none; border-radius: 14px; padding: 10px; font-weight: 600; }}
QPushButton#Primary:hover {{ background: white; }}

QPushButton#Pill {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.18); border-radius: 15px; padding: 6px 13px; font-size: 12.5px; }}
QPushButton#Pill:hover {{ background: rgba(255,255,255,0.14); border-color: rgba(255,255,255,0.38); }}
QPushButton#Pill[selected="true"] {{ background: rgba(255,255,255,0.30); border-color: rgba(255,255,255,0.6); }}

QPushButton#Row {{ background: transparent; border: none; border-radius: 12px; padding: 8px 10px; text-align: left; }}
QPushButton#Row:hover {{ background: rgba(255,255,255,0.10); }}
QPushButton#Row[selected="true"] {{ background: rgba(255,255,255,0.18); }}

QLineEdit, QPlainTextEdit#Field {{ background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.16);
    border-radius: 12px; padding: 8px 11px; selection-background-color: rgba(160,200,255,0.5); }}
QLineEdit:focus, QPlainTextEdit#Field:focus {{ border-color: rgba(255,255,255,0.5); background: rgba(255,255,255,0.13); }}
QPlainTextEdit#Input {{ background: transparent; border: none; font-size: 14.5px; selection-background-color: rgba(160,200,255,0.5); }}

QFrame#Card {{ background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.13); border-radius: 18px; }}
QFrame#Composer {{ background: rgba(255,255,255,0.13); border: 1px solid rgba(255,255,255,0.24); border-radius: 22px; }}
QFrame#Composer[focus="true"] {{ border-color: rgba(255,255,255,0.45); }}
QFrame#UserBubble {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,0.30), stop:1 rgba(255,255,255,0.19));
    border: 1px solid rgba(255,255,255,0.3); border-radius: 18px; border-bottom-right-radius: 6px; }}
QFrame#Menu {{ background: rgba(28,30,36,0.97); border: 1px solid rgba(255,255,255,0.22); border-radius: 18px; }}
QFrame#Pane {{ background: rgba(255,255,255,0.04); border: none; border-right: 1px solid rgba(255,255,255,0.10); }}
QFrame#Chip {{ background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.24); border-radius: 14px; }}
QLabel#Dim {{ color: rgba(255,255,255,0.6); font-size: 11.5px; }}
QLabel#Title {{ font-size: 14.5px; font-weight: 600; }}
QLabel#H1 {{ font-size: 27px; font-weight: 600; }}
QLabel#H2 {{ font-size: 21px; color: rgba(255,255,255,0.7); }}
QLabel#CardTitle {{ font-size: 14px; font-weight: 600; }}
QSlider::groove:horizontal {{ height: 6px; background: rgba(255,255,255,0.15); border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: rgba(255,255,255,0.85); border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 20px; height: 20px; margin: -7px 0; border-radius: 10px; }}
QCheckBox::indicator {{ width: 40px; height: 22px; }}
"""


# ---------------------------------------------------------------- animation helpers

def fade_in(w: QWidget, ms: int = 260, delay: int = 0) -> None:
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(0.0)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: w.setGraphicsEffect(None))  # drop the effect so text stays crisp
    QTimer.singleShot(delay, anim.start)
    w._fade = anim  # keep a reference


def fade_out(w: QWidget, ms: int = 160, done=None) -> None:
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    if done:
        anim.finished.connect(done)
    anim.start()
    w._fade = anim


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


# ---------------------------------------------------------------- buttons

def icon_btn(text: str, tip: str, kind: str = "Icon") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    return b


def pill(text: str, selected: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Pill")
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setProperty("selected", "true" if selected else "false")
    return b


def set_selected(b: QWidget, on: bool) -> None:
    b.setProperty("selected", "true" if on else "false")
    repolish(b)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


# ---------------------------------------------------------------- flow layout (wrapping chips)

class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 8):
        super().__init__(parent)
        self.items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self.items:
            s = s.expandedTo(it.minimumSize())
        return s

    def clear(self):
        while self.items:
            it = self.items.pop()
            if it.widget():
                it.widget().deleteLater()

    def _do(self, rect, test):
        x, y, row_h = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self.items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and row_h > 0:
                x, y, row_h = rect.x(), y + row_h + sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + sp
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y()


# ---------------------------------------------------------------- orb + switch + bars

class Orb(QWidget):
    def __init__(self, size: int = 22, glow: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + (16 if glow else 0), size + (16 if glow else 0))
        self.size_ = size
        self.glow = glow
        self._scale = 1.0
        self.breathing = False
        self._t = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

    def set_breathing(self, on: bool) -> None:
        self.breathing = on
        if on:
            self.timer.start()
        else:
            self.timer.stop()
            self._scale = 1.0
            self.update()

    def _tick(self):
        import math
        self._t += 0.033
        self._scale = 1 + 0.12 * math.sin(self._t * 6)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.rect().center())
        r = self.size_ / 2 * self._scale
        if self.glow:
            for i in range(6, 0, -1):
                p.setBrush(QColor(182, 156, 255, 12 * i))
                p.setPen(Qt.NoPen)
                p.drawEllipse(c, r + i * 1.4, r + i * 1.4)
        g = QLinearGradient(c.x() - r, c.y() - r, c.x() + r, c.y() + r)
        g.setColorAt(0, QColor("#9AE6FF")); g.setColorAt(0.55, QColor("#B69CFF")); g.setColorAt(1, QColor("#FFA8D9"))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, r, r)
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawEllipse(QPointF(c.x() - r * 0.25, c.y() - r * 0.45), r * 0.42, r * 0.22)


class Switch(QAbstractButton):
    """iOS-style toggle with a sliding knob."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 26)
        self._pos = 0.0
        self.anim = QPropertyAnimation(self, b"knob", self)
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self.anim.stop()
        self.anim.setStartValue(self._pos)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def setChecked(self, on):
        super().setChecked(on)
        self.anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = QColor(52, 199, 89)
        off = QColor(255, 255, 255, 50)
        t = max(0.0, min(1.0, self._pos))
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t), int(off.alpha() + (255 - off.alpha()) * t))
        p.setBrush(track); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, 44, 26, 13, 13)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(13 + self._pos * 18, 13), 11, 11)


class VoiceBars(QWidget):
    """Live mic bars."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(70, 28)
        self.level = 0.0
        self.heights = [4.0] * 7
        self._t = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _tick(self):
        import math
        self._t += 0.016
        self.level *= 0.9
        for i in range(len(self.heights)):
            wave = 0.5 + 0.5 * math.sin(self._t * 9 + i * 0.9)
            target = 4 + 22 * min(1.0, 0.12 + self.level * 1.6) * (0.35 + 0.65 * wave)
            self.heights[i] += (target - self.heights[i]) * 0.3
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("white")); p.setPen(Qt.NoPen)
        for i, h in enumerate(self.heights):
            x = i * 9
            p.drawRoundedRect(QRectF(x, (28 - h) / 2, 4, h), 2, 2)


class Dots(QWidget):
    """'Thinking' indicator: shimmering label + bouncing dots."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 26)
        self._t = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self._t += 0.016
        self.update()

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font()); f.setPointSizeF(10.5)
        p.setFont(f)
        x = (math.fmod(self._t / 1.4, 1.0) * 2 - 0.5) * 80
        g = QLinearGradient(x - 40, 0, x + 40, 0)
        g.setColorAt(0, QColor(255, 255, 255, 100)); g.setColorAt(0.5, QColor(255, 255, 255, 255)); g.setColorAt(1, QColor(255, 255, 255, 100))
        p.setPen(QPen(g, 1))
        p.drawText(QRect(0, 0, 70, 26), Qt.AlignVCenter | Qt.AlignLeft, "Thinking")
        p.setPen(Qt.NoPen)
        for i in range(3):
            ph = (self._t * 1000 - i * 140) % 1000
            y = -5 * math.sin(ph / 520 * math.pi) if ph < 520 else 0
            a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self._t * 6 - i))
            p.setBrush(QColor(255, 255, 255, int(255 * a)))
            p.drawEllipse(QPointF(76 + i * 10, 14 + y), 3, 3)


# ---------------------------------------------------------------- markdown view that sizes to its content

class MarkdownView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; font-size: 14px; }")
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(
            "code { background-color: rgba(255,255,255,0.16); font-family: 'JetBrains Mono','Fira Code',monospace; }"
            "pre { background-color: rgba(0,0,0,0.30); font-family: 'JetBrains Mono','Fira Code',monospace; }"
            "a { color: #A8D8FF; text-decoration: none; }"
            "table { border-color: rgba(255,255,255,0.2); }"
            "th { background-color: rgba(255,255,255,0.12); }")
        self.document().contentsChanged.connect(self._fit)

    def set_markdown(self, md: str) -> None:
        self.setMarkdown(md or "")
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        self.document().setTextWidth(max(50, self.viewport().width()))
        h = int(self.document().size().height()) + 4
        if self.height() != h:
            self.setFixedHeight(h)


# ---------------------------------------------------------------- toast

class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(28,30,36,0.94); border: 1px solid rgba(255,255,255,0.25); border-radius: 14px; padding: 8px 14px; font-size: 12.5px;")
        self.setWordWrap(True)
        self.setMaximumWidth(340)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: fade_out(self, 250, self.hide))

    def show_text(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, 64)
        self.raise_()
        self.show()
        fade_in(self, 200)
        self.timer.start(2400)
