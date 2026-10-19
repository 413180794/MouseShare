"""An optional click-through colored ring identifies remotely controlled input."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RemotePointer(QWidget):
    def __init__(self, window):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus |
                         Qt.WindowType.WindowTransparentForInput)
        self.window = window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(40, 40)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        visible = (not self.window.demo and self.window.engine.state == 'receiving'
                   and self.window.settings.get('remote_pointer', True) and self.window.engine.available)
        if visible:
            point = QCursor.pos()
            self.move(point.x()-20, point.y()-20)
            self.update()
        if self.isVisible() != visible:
            self.setVisible(visible)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.window.settings.get('pointer_color', '#16a38c'))
        if not color.isValid():
            color = QColor('#16a38c')
        painter.setPen(QPen(QColor('#ffffff'), 5))
        painter.drawEllipse(5, 5, 30, 30)
        painter.setPen(QPen(color, 2.5))
        painter.drawEllipse(5, 5, 30, 30)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
