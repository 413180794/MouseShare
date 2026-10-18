"""GUI-thread cursor ownership while Windows forwards physical input."""
import ctypes as C
import sys
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


class Surface(QWidget):
    def __init__(self, geometry):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(geometry)
        self.setCursor(Qt.CursorShape.BlankCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        # A zero-alpha layered window is hit-test transparent on Windows. The
        # minimal nonzero alpha retains cursor ownership without taking focus.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))


class WindowsCursorShield(QObject):
    show_requested = Signal(object)
    hide_requested = Signal()

    def __init__(self):
        super().__init__()
        self.panels = []
        self.detail = ''
        self.show_requested.connect(self.show, Qt.ConnectionType.QueuedConnection)
        self.hide_requested.connect(self.hide, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.enforce)

    def set_enabled(self, enabled):
        if QThread.currentThread() == self.thread():
            self.show() if enabled else self.hide()
        elif enabled:
            request = dict(done=threading.Event(), cancelled=False)
            self.show_requested.emit(request)
            if not request['done'].wait(0.5):
                request['cancelled'] = True
                self.hide_requested.emit()
                raise OSError('Windows 光标保护未就绪，已中止共享')
        else:
            self.hide_requested.emit()
        if enabled and not self.panels:
            raise OSError(self.detail or '无法隐藏源端光标，已中止共享')

    @Slot(object)
    def show(self, request=None):
        try:
            if request and request['cancelled']:
                return
            if not self.panels:
                for screen in QApplication.screens():
                    panel = Surface(screen.geometry())
                    panel.show()
                    self.panels.append(panel)
            self.enforce()
            self.timer.start()
        except Exception as exc:
            self.detail = type(exc).__name__
            self.hide()
        finally:
            if request:
                if request['cancelled']:
                    self.hide()
                request['done'].set()

    def enforce(self):
        if sys.platform != 'win32' or not self.panels:
            return
        from ctypes import wintypes as W
        user = C.windll.user32
        user.WindowFromPoint.argtypes, user.WindowFromPoint.restype = [W.POINT], W.HWND
        user.SetCursor.argtypes, user.SetCursor.restype = [W.HANDLE], W.HANDLE
        point = W.POINT()
        if user.GetCursorPos(C.byref(point)):
            owner = user.WindowFromPoint(point)
            if owner in {int(panel.winId()) for panel in self.panels}:
                user.SetCursor(None)

    @Slot()
    def hide(self):
        visible = bool(self.panels)
        self.timer.stop()
        for panel in self.panels:
            panel.hide()
            panel.close()
            panel.deleteLater()
        self.panels.clear()
        if visible and sys.platform == 'win32':
            from ctypes import wintypes as W
            user = C.windll.user32
            user.LoadCursorW.argtypes, user.LoadCursorW.restype = [W.HINSTANCE, C.c_void_p], W.HANDLE
            user.SetCursor.argtypes, user.SetCursor.restype = [W.HANDLE], W.HANDLE
            user.SetCursor(user.LoadCursorW(None, C.c_void_p(32512)))
