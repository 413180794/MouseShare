"""Presentation-only desktop widgets. No input capture or network behavior lives here."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

STYLE = """
QWidget { color: #233d39; font-size: 13px; }
QMainWindow, QDialog { background: #f6f7f5; }
QWidget#shell, QWidget#page { background: #f6f7f5; }
QFrame#sidebar { background: #edf1ed; border-right: 1px solid #dfe5df; }
QFrame#card { background: #ffffff; border: 1px solid #e1e7e1; border-radius: 14px; }
QFrame#canvas { background: #eff4ef; border: 1px solid #e1e8df; border-radius: 16px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 18px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#title { font-size: 27px; font-weight: 650; letter-spacing: -0.6px; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#eyebrow { color: #72827b; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#hint, QLabel#subtitle { color: #75837e; font-size: 12px; }
QLabel#state { font-size: 17px; font-weight: 600; }
QLabel#statusBadge { color: #12755f; background: #e3f1e9; border-radius: 12px; padding: 6px 12px; font-size: 12px; }
QLabel#statusBadge[tone="warning"] { color: #96631c; background: #fcf0d9; }
QLabel#statusBadge[tone="idle"] { color: #697a73; background: #e8ede8; }
QLabel#shortcut { color: #78867e; font-size: 11px; }
QPushButton { background: #ffffff; border: 1px solid #dce4dc; border-radius: 8px;
    padding: 9px 14px; min-height: 17px; font-weight: 500; }
QPushButton:hover { background: #f0f5f0; border-color: #b7cbc0; }
QPushButton:pressed { background: #e1ede4; }
QPushButton:focus { border-color: #20836c; }
QPushButton:disabled { color: #9da9a2; background: #f5f7f4; border-color: #e6ebe5; }
QPushButton#primary { background: #167c67; color: #ffffff; border-color: #167c67; font-weight: 600; }
QPushButton#primary:hover { background: #106955; border-color: #106955; }
QPushButton#primary:disabled { background: #e1e9e1; color: #94a69a; border-color: #e1e9e1; }
QPushButton#nav { background: transparent; border: 0; border-radius: 8px; padding: 12px; text-align: left; color: #728078; }
QPushButton#nav:hover { background: #e4ebe3; }
QPushButton#nav:checked { background: #dce8dd; color: #176652; font-weight: 600; }
QPushButton#quiet { background: transparent; border: 0; color: #6c7e74; padding: 7px 2px; text-align: left; }
QPushButton#quiet:hover { color: #146b57; }
QPushButton#game { background: #f5f8f3; text-align: left; padding: 12px 16px; border-radius: 10px; }
QPushButton#game:checked { background: #fbefd9; border-color: #dfbc7d; color: #89601f; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #fafcf9; color: #29433a;
    border: 1px solid #dce4db; border-radius: 7px; padding: 8px 10px; min-height: 18px;
    selection-background-color: #c6e4d4; selection-color: #174a36; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #298870; }
QComboBox QAbstractItemView { background: #ffffff; color: #29433a; selection-background-color: #e0ede2; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 3px 1px; }
QScrollBar::handle:vertical { background: #cbd6cb; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTableWidget { background: #ffffff; border: 0; gridline-color: #edf1eb; outline: 0;
    selection-background-color: #eff6ee; selection-color: #204a35; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #edf1eb; }
QTableWidget::item:selected { background: #eff6ee; color: #204a35; }
QHeaderView::section { background: #ffffff; border: 0; color: #8a968d; padding: 8px; font-size: 11px; text-align: left; }
QCheckBox { spacing: 10px; padding: 5px 0; }
QMenu { background: #ffffff; border: 1px solid #dae3da; padding: 5px; }
QMenu::item { padding: 9px 20px; border-radius: 4px; }
QMenu::item:selected { background: #e8f1e5; }
QToolTip { color: #ffffff; background: #244b3a; border: 0; padding: 6px; }
"""


def apply_theme(app):
    # Use a complete light palette so native controls also remain readable when
    # the operating system is in dark mode.
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in {
        "Window": "#f6f7f5", "WindowText": "#233d39", "Base": "#ffffff",
        "AlternateBase": "#f4f7f1", "Text": "#233d39", "Button": "#ffffff",
        "ButtonText": "#233d39", "Highlight": "#dcecdf", "HighlightedText": "#174734",
        "ToolTipBase": "#244b3a", "ToolTipText": "#ffffff", "PlaceholderText": "#8b978c",
        "Link": "#167c67", "Mid": "#dce4db", "Light": "#ffffff", "Dark": "#7d8d7f",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9ba69b"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


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
        self.owner = "local"
        self.setMinimumHeight(218)
        self.setAccessibleName("屏幕位置示意")

    def configure(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        direction = {"left": "左侧", "right": "右侧", "top": "上方", "bottom": "下方"}[self.side]
        self.setAccessibleDescription(f"本机 {self.local_name}；对方 {self.peer_name} 位于{direction}")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        vertical = self.side in {"top", "bottom"}
        sw, sh = (158, 66) if vertical else (180, 112)
        gap = 18 if vertical else 64
        cx, cy = w / 2, h / 2 if vertical else h / 2 - 11
        if vertical:
            # Names are inside each display for the more compact vertical map.
            first = QRectF(cx - sw / 2, cy - sh - gap / 2, sw, sh)
            second = QRectF(cx - sw / 2, cy + gap / 2, sw, sh)
        else:
            first = QRectF(cx - sw - gap / 2, cy - sh / 2, sw, sh)
            second = QRectF(cx + gap / 2, cy - sh / 2, sw, sh)
        local, peer = (second, first) if self.side in {"left", "top"} else (first, second)
        active_remote = self.owner == "sending"
        for rect, name, os_name, active, is_local in [
            (local, self.local_name, self.local_os, not active_remote, True),
            (peer, self.peer_name, self.peer_os, active_remote, False),
        ]:
            filled = active and (self.connected or is_local) and not self.blocked
            p.setPen(QPen(QColor("#2f8870" if filled else "#c6d4c5"), 1.5))
            p.setBrush(QColor("#deeee0" if filled else "#f8faf5"))
            p.drawRoundedRect(rect, 10, 10)
            p.setPen(QPen(QColor("#aac5ad" if filled else "#dce4d8"), 1))
            p.drawLine(QPointF(rect.x() + 11, rect.y() + 17), QPointF(rect.right() - 11, rect.y() + 17))
            for dx in (11, 17, 23):
                p.setBrush(QColor("#7ba78d" if filled else "#c6d2c3"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(rect.x() + dx, rect.y() + 9), 1.5, 1.5)
            p.setPen(QColor("#244f3d" if filled else "#7d8c7d"))
            font = QFont(self.font())
            font.setPixelSize(12 if vertical else 13)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            name_rect = rect.adjusted(10, 26, -10, -16)
            name_text = p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(name_rect.width()))
            p.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name_text)
            font.setPixelSize(10)
            font.setWeight(QFont.Weight.Normal)
            p.setFont(font)
            p.setPen(QColor("#7a8e7c"))
            p.drawText(rect.adjusted(10, 47 if vertical else 50, -10, -4), Qt.AlignmentFlag.AlignHCenter,
                       (os_name + " · 本机") if is_local else (os_name or "自动发现"))
            if not vertical:
                p.setPen(QPen(QColor("#a7bba7"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(rect.center().x(), rect.bottom() + 1), QPointF(rect.center().x(), rect.bottom() + 14))
                p.drawLine(QPointF(rect.center().x() - 19, rect.bottom() + 14),
                           QPointF(rect.center().x() + 19, rect.bottom() + 14))
        p.setPen(QPen(QColor("#548f72" if self.connected and not self.blocked else "#bccabc"), 1.5,
                      Qt.PenStyle.DashLine))
        if vertical:
            p.drawLine(QPointF(cx, first.bottom() + 7), QPointF(cx, second.top() - 7))
        else:
            p.drawLine(QPointF(first.right() + 8, cy), QPointF(second.left() - 8, cy))
        if self.connected and not self.blocked:
            rect = peer if active_remote else local
            px, py = rect.right() - 34, rect.bottom() - 35
            cursor = QPainterPath(QPointF(px, py))
            for dx, dy in [(0, 22), (6, 16), (12, 26), (16, 23), (10, 13), (19, 12)]:
                cursor.lineTo(px + dx, py + dy)
            cursor.closeSubpath()
            p.setPen(QPen(QColor("#ffffff"), 1.4))
            p.setBrush(QColor("#176d52"))
            p.drawPath(cursor)
        p.end()
