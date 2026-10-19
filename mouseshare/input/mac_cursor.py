"""Non-activating cursor surface, owned exclusively by the Qt GUI thread."""
import threading

import AppKit as A
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from ..i18n import tr


class MouseShareCursorPanel(A.NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class MouseShareCursorSurface(A.NSView):
    def resetCursorRects(self):
        image = A.NSImage.alloc().initWithSize_((16, 16))
        self.blank_cursor = A.NSCursor.alloc().initWithImage_hotSpot_(image, (0, 0))
        self.addCursorRect_cursor_(self.bounds(), self.blank_cursor)

    def mouseMoved_(self, event):
        if hasattr(self, "blank_cursor"):
            self.blank_cursor.set()


class CursorShield(QObject):
    show_requested = Signal(object)
    hide_requested = Signal()

    def __init__(self):
        super().__init__()
        self.panels = []
        self.error = ""
        self.detail = ""
        self.show_requested.connect(self.show, Qt.ConnectionType.QueuedConnection)
        self.hide_requested.connect(self.hide, Qt.ConnectionType.QueuedConnection)

    def set_enabled(self, enabled):
        if QThread.currentThread() == self.thread():
            self.show() if enabled else self.hide()
        elif enabled:
            request = {"done": threading.Event(), "cancelled": False}
            self.show_requested.emit(request)
            if not request["done"].wait(0.4):
                request["cancelled"] = True
                self.hide_requested.emit()
                raise OSError(tr('Mac 光标保护窗口未就绪，已中止共享'))
        else:
            # Never block the event tap or GUI shutdown waiting for dismissal.
            self.hide_requested.emit()
        if enabled and not self.panels:
            raise OSError(self.error or tr('无法创建 Mac 光标保护窗口，已中止共享'))

    @Slot(object)
    def show(self, request=None):
        if request and request["cancelled"]:
            request["done"].set()
            return
        self.hide()
        self.error = ""
        self.detail = ""
        try:
            self.create_panels()
        except Exception as exc:
            self.hide()
            self.error = tr('无法创建 Mac 光标保护窗口，已中止共享')
            self.detail = f"{type(exc).__name__}: {exc}"
        finally:
            if request:
                if request["cancelled"]:
                    self.hide()
                request["done"].set()

    def create_panels(self):
        behavior = (A.NSWindowCollectionBehaviorCanJoinAllSpaces
                    | A.NSWindowCollectionBehaviorStationary
                    | A.NSWindowCollectionBehaviorFullScreenAuxiliary
                    | A.NSWindowCollectionBehaviorIgnoresCycle)
        for screen in A.NSScreen.screens():
            panel = MouseShareCursorPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                screen.frame(), A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel,
                A.NSBackingStoreBuffered, False)
            panel.setReleasedWhenClosed_(False)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(A.NSColor.clearColor())
            panel.setHasShadow_(False)
            panel.setHidesOnDeactivate_(False)
            panel.setAcceptsMouseMovedEvents_(True)
            panel.setIgnoresMouseEvents_(False)
            panel.setLevel_(A.NSScreenSaverWindowLevel)
            panel.setCollectionBehavior_(behavior)
            surface = MouseShareCursorSurface.alloc().initWithFrame_(panel.contentView().bounds())
            panel.setContentView_(surface)
            panel.orderFrontRegardless()
            panel.invalidateCursorRectsForView_(surface)
            surface.resetCursorRects()
            surface.blank_cursor.set()
            self.panels.append(panel)

    @Slot()
    def hide(self):
        visible = bool(self.panels)
        for panel in self.panels:
            panel.orderOut_(None)
            panel.close()
        self.panels.clear()
        if visible:
            A.NSCursor.arrowCursor().set()
