"""Presentation-only desktop widgets. No input capture or network behavior lives here."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProxyStyle, QPushButton, QStyle,
                               QVBoxLayout, QWidget)

from .branding import line_icon, pointer

# Light palette tokens shared by the style sheet and custom painting.
BG = "#f4f6f7"
SIDEBAR = "#ebeff1"
SURFACE = "#ffffff"
LINE = "#e2e7ea"
LINE_STRONG = "#cdd5d9"
INK = "#14262b"
INK_2 = "#56676d"
INK_3 = "#8a979c"
ACCENT = "#0c8176"
ACCENT_HOVER = "#0a6e65"
ACCENT_PRESS = "#085c54"
ACCENT_SOFT = "#e2f4f0"
ACCENT_LINE = "#93d5c8"
ACCENT_INK = "#09605a"
WARN = "#c27a12"
WARN_INK = "#8d5408"
WARN_SOFT = "#fdf1dc"
WARN_LINE = "#ecca8c"

# (text, background) per status tone; status is always spelled out, never color alone.
TONES = {
    "active": (ACCENT_INK, ACCENT_SOFT, ACCENT),
    "warning": (WARN_INK, WARN_SOFT, WARN),
    "idle": ("#55666c", "#e9eef0", "#9aa7ac"),
    "paired": (ACCENT_INK, "#eef7f5", "#5fb3a5"),
}

STYLE = """
QWidget { color: @INK@; font-size: 13px; }
QMainWindow, QDialog { background: @BG@; }
QWidget#shell, QWidget#page { background: @BG@; }
QFrame#sidebar { background: @SIDEBAR@; border-right: 1px solid @LINE@; }
QFrame#card { background: @SURFACE@; border: 1px solid @LINE@; border-radius: 14px; }
QFrame#canvas { border: 1px solid #d5e9e4; border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f3fbf9, stop:.6 #eef7f6, stop:1 #ecf3f7); }
QFrame#footer { background: @SURFACE@; border-top: 1px solid @LINE@; }
QLabel { background: transparent; }
QLabel#brand { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }
QLabel#title { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#eyebrow { color: @INK_3@; font-size: 10px; font-weight: 600; letter-spacing: 1.2px; }
QLabel#hint, QLabel#subtitle { color: @INK_2@; font-size: 12px; }
QLabel#hint[tone="warning"] { color: @WARN_INK@; }
QLabel#subtitle { font-size: 13px; }
QLabel#state { font-size: 19px; font-weight: 650; letter-spacing: -0.2px; }
QLabel#chip { color: @INK_2@; background: rgba(255, 255, 255, 0.78); border: 1px solid #dbe8e5;
    border-radius: 12px; padding: 4px 12px; font-size: 12px; }
QLabel#statusBadge { border-radius: 14px; padding: 6px 14px 6px 26px; font-size: 12px; font-weight: 600; }
QLabel#kbd { color: @INK@; background: #f7f9fa; border: 1px solid @LINE_STRONG@; border-bottom-width: 2px;
    border-radius: 6px; padding: 2px 8px; font-size: 12px; font-weight: 500; }
QLabel#digit { color: @ACCENT_INK@; background: @ACCENT_SOFT@; border: 1px solid @ACCENT_LINE@; border-radius: 10px;
    font-size: 34px; font-weight: 700; min-width: 46px; min-height: 62px; }
QPushButton { background: @SURFACE@; border: 1px solid @LINE_STRONG@; border-radius: 9px;
    padding: 9px 15px; min-height: 18px; font-weight: 500; }
QPushButton:hover { background: #f5f8f9; border-color: #b9c4c9; }
QPushButton:pressed { background: #eaeff1; }
QPushButton:focus { border-color: @ACCENT@; }
QPushButton:disabled { color: #a2adb1; background: #f6f8f9; border-color: #e6eaec; }
QPushButton#primary { background: @ACCENT@; color: #ffffff; border-color: @ACCENT@; font-weight: 600; }
QPushButton#primary:hover { background: @ACCENT_HOVER@; border-color: @ACCENT_HOVER@; }
QPushButton#primary:pressed { background: @ACCENT_PRESS@; border-color: @ACCENT_PRESS@; }
QPushButton#primary:focus { border-color: @ACCENT_PRESS@; }
QPushButton#primary:disabled { background: #e3e9eb; color: #97a4a9; border-color: #e3e9eb; }
QPushButton#nav { background: transparent; border: 1px solid transparent; border-radius: 9px;
    padding: 10px 12px; text-align: left; color: @INK_2@; font-size: 13px; }
QPushButton#nav:hover { background: #e2e8eb; }
QPushButton#nav:checked { background: @SURFACE@; border-color: @LINE@; color: @INK@; font-weight: 600; }
QPushButton#quiet { background: transparent; border: 0; color: @INK_2@; padding: 7px 4px; text-align: left; }
QPushButton#quiet:hover { color: @ACCENT@; }
QPushButton#quiet[tone="warning"] { color: @WARN_INK@; font-weight: 600; }
QPushButton#link { background: transparent; border: 0; color: @ACCENT@; padding: 7px 2px; font-weight: 500; }
QPushButton#link:hover { color: @ACCENT_PRESS@; }
QPushButton#link:checked { color: @INK_2@; }
QPushButton#game { padding: 9px 16px; font-weight: 600; }
QPushButton#game:checked { background: @WARN_SOFT@; border-color: @WARN_LINE@; color: @WARN_INK@; }
QPushButton#game:checked:hover { background: #fbe8c8; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #fbfcfc; color: @INK@;
    border: 1px solid @LINE_STRONG@; border-radius: 8px; padding: 8px 10px; min-height: 18px;
    selection-background-color: #bfe6dd; selection-color: @INK@; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #b4c0c5; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: @ACCENT@; background: #ffffff; }
QLineEdit:disabled { color: #9aa6ab; background: #f3f5f6; border-color: #e6eaec; }
QComboBox QAbstractItemView { background: #ffffff; color: @INK@; border: 1px solid @LINE@;
    selection-background-color: @ACCENT_SOFT@; selection-color: @ACCENT_INK@; outline: 0; padding: 4px; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox::down-arrow { image: url("@assets@/chevron-down.png"); width: 14px; height: 14px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { border: 0; width: 22px; subcontrol-origin: border; subcontrol-position: top right; }
QSpinBox::down-button, QDoubleSpinBox::down-button { border: 0; width: 22px; subcontrol-origin: border; subcontrol-position: bottom right; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@assets@/chevron-up.png"); width: 12px; height: 12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@assets@/chevron-down.png"); width: 12px; height: 12px; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 3px 1px; }
QScrollBar::handle:vertical { background: #c9d2d6; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #aebbc0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QCheckBox { spacing: 12px; padding: 5px 0; }
QCheckBox::indicator { width: 34px; height: 20px; }
QProgressBar { border: 1px solid @LINE@; border-radius: 5px; background: @BG@;
    min-height: 12px; max-height: 12px; text-align: center; font-size: 10px; }
QProgressBar::chunk { background: @ACCENT_LINE@; border-radius: 4px; }
QMenu { background: #ffffff; border: 1px solid @LINE@; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 8px 20px; border-radius: 5px; }
QMenu::item:selected { background: @ACCENT_SOFT@; color: @ACCENT_INK@; }
QMenu::separator { height: 1px; background: @LINE@; margin: 4px 8px; }
QToolTip { color: #ffffff; background: #1d3236; border: 0; padding: 6px 8px; }
"""


class DesktopStyle(QProxyStyle):
    """Paint essential indicators without an optional SVG image plugin."""
    def __init__(self):
        super().__init__("Fusion")

    def drawPrimitive(self, element, option, painter, widget=None):
        pe = QStyle.PrimitiveElement
        arrows = {pe.PE_IndicatorArrowDown, pe.PE_IndicatorArrowUp,
                  pe.PE_IndicatorSpinDown, pe.PE_IndicatorSpinUp}
        if element != pe.PE_IndicatorCheckBox and element not in arrows:
            return super().drawPrimitive(element, option, painter, widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        rect = QRectF(option.rect)
        if element == pe.PE_IndicatorCheckBox:
            # Settings checkboxes render as switches; the widget stays a native QCheckBox.
            checked = bool(option.state & QStyle.StateFlag.State_On)
            track = QRectF(0, 0, min(rect.width(), 34), min(rect.height(), 20))
            track.moveCenter(rect.center())
            track.adjust(.5, .5, -.5, -.5)
            on = QColor(ACCENT if enabled else ACCENT_LINE)
            painter.setPen(QPen(on if checked else QColor("#c2ccd0" if enabled else "#dde3e6"), 1))
            painter.setBrush(on if checked else QColor("#dfe5e8" if enabled else "#eef1f3"))
            painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
            if option.state & QStyle.StateFlag.State_HasFocus:
                painter.setPen(QPen(QColor(ACCENT_LINE), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), track.height() / 2 + 2, track.height() / 2 + 2)
            knob = track.height() - 4
            x = track.right() - 2 - knob if checked else track.left() + 2
            painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QRectF(x, track.top() + 2, knob, knob))
        else:
            x, y = rect.center().x(), rect.center().y()
            direction = -1 if element in {pe.PE_IndicatorArrowUp, pe.PE_IndicatorSpinUp} else 1
            painter.setPen(QPen(QColor(INK_2 if enabled else "#b8c2c6"), 1.4,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath(QPointF(x - 3, y - direction * 1.5))
            path.lineTo(x, y + direction * 1.5)
            path.lineTo(x + 3, y - direction * 1.5)
            painter.drawPath(path)
        painter.restore()


def apply_theme(app):
    # Use a complete light palette so native controls also remain readable when
    # the operating system is in dark mode.
    app.setStyle(DesktopStyle())
    palette = QPalette()
    for role, color in {
        "Window": BG, "WindowText": INK, "Base": SURFACE,
        "AlternateBase": "#f4f7f8", "Text": INK, "Button": SURFACE,
        "ButtonText": INK, "Highlight": "#cdeee6", "HighlightedText": INK,
        "ToolTipBase": "#1d3236", "ToolTipText": "#ffffff", "PlaceholderText": "#929fa4",
        "Link": ACCENT, "Mid": LINE_STRONG, "Light": "#ffffff", "Dark": "#7f8d92",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9ca8ad"))
    app.setPalette(palette)
    style = STYLE.replace("@assets@", (Path(__file__).parent / "assets").as_posix())
    # Longest names first so @INK@ does not clobber @INK_2@ and friends.
    for name, value in sorted(globals().items(), key=lambda item: -len(item[0])):
        if name.isupper() and isinstance(value, str) and value.startswith("#"):
            style = style.replace(f"@{name}@", value)
    app.setStyleSheet(style)


def text_label(text, role="", wrap=False):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setObjectName(role)
    label.setWordWrap(wrap)
    return label


def card(title=None, detail=None):
    box = QFrame()
    box.setObjectName("card")
    body = QVBoxLayout(box)
    body.setContentsMargins(22, 20, 22, 20)
    body.setSpacing(14)
    if title:
        body.addWidget(text_label(title, "section"))
    if detail:
        body.addWidget(text_label(detail, "hint", True))
    return box, body


def keycaps(keys, description):
    """A shortcut row: each key as a cap, followed by what it does."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    for key in keys:
        layout.addWidget(text_label(key, "kbd"))
    layout.addSpacing(10)
    layout.addWidget(text_label(description, "hint"), 1)
    row.setAccessibleName(f"{' + '.join(keys)}：{description}")
    return row


class StatusBadge(QLabel):
    """Pill with a leading status dot; the text always names the state."""
    def __init__(self, text=""):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.tone = "idle"
        self.set_status(text, "idle")

    def set_status(self, text, tone):
        self.tone = tone if tone in TONES else "idle"
        ink, soft, _ = TONES[self.tone]
        self.setText(text)
        self.setStyleSheet(f"color: {ink}; background: {soft};")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot = QColor(TONES[self.tone][2])
        halo = QColor(dot)
        halo.setAlpha(55)
        center = QPointF(15, self.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(center, 6, 6)
        p.setBrush(dot)
        p.drawEllipse(center, 3.5, 3.5)
        p.end()


class PeerCard(QPushButton):
    """Native checkable button (keeps Cocoa accessibility) painted as a device row."""
    def __init__(self):
        super().__init__()
        self.setObjectName("peer")
        self.setCheckable(True)
        self.setMinimumHeight(66)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name, self.os_name, self.host, self.status, self.tone = "", "", "", "", "idle"

    def show_peer(self, name, os_name, host, status, tone):
        self.name, self.os_name, self.host, self.status, self.tone = name, os_name, host, status, tone
        self.setText(f"{name}  ·  {os_name}\n{host}  ·  {status}")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        checked, hover = self.isChecked(), self.underMouse()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(ACCENT if checked or self.hasFocus() else LINE_STRONG if hover else LINE),
                      1.6 if checked else 1))
        p.setBrush(QColor("#f1faf8" if checked else "#fafbfc" if hover else SURFACE))
        p.drawRoundedRect(rect, 12, 12)
        avatar = QRectF(rect.left() + 13, rect.center().y() - 20, 40, 40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT_SOFT if checked else "#eef2f4"))
        p.drawRoundedRect(avatar, 10, 10)
        glyph = "laptop" if self.os_name == "macOS" else "monitor"
        line_icon(glyph, ACCENT_INK if checked else INK_2, 22).paint(p, avatar.adjusted(9, 9, -9, -9).toRect())
        ink, soft, dot = TONES.get(self.tone, TONES["idle"])
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        pill_w = p.fontMetrics().horizontalAdvance(self.status) + 30
        pill = QRectF(rect.right() - 14 - pill_w, rect.center().y() - 12, pill_w, 24)
        p.setBrush(QColor(soft))
        p.drawRoundedRect(pill, 12, 12)
        p.setBrush(QColor(dot))
        p.drawEllipse(QPointF(pill.left() + 12, pill.center().y()), 3.2, 3.2)
        p.setPen(QColor(ink))
        p.drawText(pill.adjusted(20, 0, -9, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.status)
        text = QRectF(avatar.right() + 13, rect.top(), pill.left() - avatar.right() - 26, rect.height())
        font.setPixelSize(14)
        p.setFont(font)
        p.setPen(QColor(INK))
        name = p.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight, int(text.width()))
        p.drawText(text.adjusted(0, 0, 0, -rect.height() / 2 + 2),
                   Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, name)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(INK_2))
        detail = "  ·  ".join(part for part in (self.os_name, self.host) if part)
        p.drawText(text.adjusted(0, rect.height() / 2 + 3, 0, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, int(text.width())))
        p.end()


class ScreenMap(QWidget):
    """A readable, live topology illustration; saved direction drives its layout."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.side = "right"
        self.local_name = "本机"
        self.peer_name = "等待另一台电脑"
        self.local_os = "macOS"
        self.peer_os = ""
        self.connected = False
        self.blocked = False
        self.game = False
        self.owner = "local"
        self.setMinimumHeight(190)
        self.setAccessibleName("屏幕位置示意")

    def configure(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        direction = {"left": "左侧", "right": "右侧", "top": "上方", "bottom": "下方"}[self.side]
        self.setAccessibleDescription(f"本机 {self.local_name}；对方 {self.peer_name} 位于{direction}")
        self.update()

    def _screen(self, p, rect, active, online, stand):
        """Monitor bezel; the screen that owns the pointer lights up in the accent gradient."""
        if stand:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#d3dbdf" if online else "#e3e8ea"))
            neck = QPainterPath(QPointF(rect.center().x() - 9, rect.bottom()))
            neck.lineTo(rect.center().x() + 9, rect.bottom())
            neck.lineTo(rect.center().x() + 12, rect.bottom() + 15)
            neck.lineTo(rect.center().x() - 12, rect.bottom() + 15)
            neck.closeSubpath()
            p.drawPath(neck)
            p.drawRoundedRect(QRectF(rect.center().x() - 30, rect.bottom() + 13, 60, 5), 2.5, 2.5)
        if online:
            for i, alpha in enumerate((14, 9, 5)):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(20, 60, 70, alpha))
                p.drawRoundedRect(rect.adjusted(-i, 2 + i, i, 3 + i * 1.5), 12, 12)
            p.setPen(QPen(QColor(ACCENT if active else LINE_STRONG), 1.4 if active else 1))
            p.setBrush(QColor(SURFACE))
        else:
            dash = QPen(QColor("#b9c5ca"), 1.3, Qt.PenStyle.CustomDashLine)
            dash.setDashPattern([4, 3])
            p.setPen(dash)
            p.setBrush(QColor(255, 255, 255, 120))
        p.drawRoundedRect(rect, 11, 11)
        inner = rect.adjusted(6, 6, -6, -6)
        p.setPen(Qt.PenStyle.NoPen)
        if online:
            fill = QLinearGradient(inner.topLeft(), inner.bottomRight())
            fill.setColorAt(0, QColor("#3fd2b3" if active else "#eef3f5"))
            fill.setColorAt(1, QColor("#0d8a80" if active else "#dde6ea"))
            p.setBrush(fill)
            p.drawRoundedRect(inner, 6, 6)
            if active:
                shine = QPainterPath()
                shine.moveTo(inner.left(), inner.top() + 6)
                shine.lineTo(inner.left() + inner.width() * .42, inner.top())
                shine.lineTo(inner.left() + inner.width() * .62, inner.top())
                shine.lineTo(inner.left(), inner.bottom() - inner.height() * .1)
                shine.closeSubpath()
                p.setClipRect(inner)
                p.setBrush(QColor(255, 255, 255, 26))
                p.drawPath(shine)
                p.setClipping(False)

    def _label(self, p, rect, align, name, sub, strong):
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(INK if strong else INK_2))
        flags = align | Qt.AlignmentFlag.AlignTop
        p.drawText(rect, flags, p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(rect.width())))
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(INK_3 if not strong else INK_2))
        p.drawText(rect.adjusted(0, 19, 0, 0), flags,
                   p.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, int(rect.width())))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        vertical = self.side in {"top", "bottom"}
        live = self.connected and not self.blocked
        if vertical:
            sw, sh, gap = 148, 60, 40
            top = (h - sh * 2 - gap) / 2
            first = QRectF(w / 2 - sw / 2 - 70, top, sw, sh)
            second = QRectF(first.left(), top + sh + gap, sw, sh)
        else:
            sw, sh, gap = 166, 98, 92
            top = (h - sh - 18 - 40) / 2
            first = QRectF(w / 2 - sw - gap / 2, top, sw, sh)
            second = QRectF(w / 2 + gap / 2, top, sw, sh)
        local, peer = (second, first) if self.side in {"left", "top"} else (first, second)
        remote_active = self.owner == "sending" and live
        local_active = not remote_active and not self.blocked
        self._screen(p, local, local_active, True, not vertical)
        self._screen(p, peer, remote_active, self.connected, not vertical)
        # Handoff edge on the local screen, facing the peer.
        edge = {"right": QRectF(local.right() - 2, local.top() + 18, 4, local.height() - 36),
                "left": QRectF(local.left() - 2, local.top() + 18, 4, local.height() - 36),
                "bottom": QRectF(local.left() + 22, local.bottom() - 2, local.width() - 44, 4),
                "top": QRectF(local.left() + 22, local.top() - 2, local.width() - 44, 4)}[self.side]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT if live else WARN if self.blocked and self.connected else "#c3cdd1"))
        p.drawRoundedRect(edge, 2, 2)
        # Connector between the two screens, with a state node in the middle.
        if vertical:
            a, b = QPointF(first.center().x(), first.bottom() + 6), QPointF(first.center().x(), second.top() - 6)
        else:
            a, b = QPointF(first.right() + 8, first.center().y()), QPointF(second.left() - 8, first.center().y())
        line = QPen(QColor(ACCENT_LINE if live else WARN_LINE if self.connected else "#c6d0d4"), 2,
                    Qt.PenStyle.SolidLine if self.connected else Qt.PenStyle.CustomDashLine, Qt.PenCapStyle.RoundCap)
        if not self.connected:
            line.setDashPattern([2, 3])
        p.setPen(line)
        p.drawLine(a, b)
        node = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        if self.connected:
            ring = ACCENT if live else WARN
            p.setPen(QPen(QColor(ring), 1.5))
            p.setBrush(QColor(SURFACE))
            p.drawEllipse(node, 15, 15)
            glyph = "link" if live else "lock" if self.game else "pause"
            line_icon(glyph, ring, 16).paint(p, QRectF(node.x() - 8, node.y() - 8, 16, 16).toRect())
        # Names: under each monitor, or beside each screen when stacked.
        local_sub = f"{self.local_os} · 本机"
        peer_sub = self.peer_os or ("已连接" if self.connected else "自动发现中")
        for rect, name, sub, strong in [(local, self.local_name, local_sub, True),
                                        (peer, self.peer_name, peer_sub, self.connected)]:
            if vertical:
                self._label(p, QRectF(rect.right() + 22, rect.center().y() - 18, 200, 40),
                            Qt.AlignmentFlag.AlignLeft, name, sub, strong)
            else:
                self._label(p, QRectF(rect.left() - 10, rect.bottom() + 26, rect.width() + 20, 40),
                            Qt.AlignmentFlag.AlignHCenter, name, sub, strong)
        screen = peer if remote_active else local
        cursor = pointer(screen.center().x() + 8, screen.center().y() - (8 if vertical else 14), .8 if vertical else 1.0)
        lit = remote_active or local_active
        p.setPen(QPen(QColor(INK if lit else "#ffffff"), 1.4,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor("#ffffff" if lit else INK_3))
        p.drawPath(cursor)
        p.end()
