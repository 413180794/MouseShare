"""Compositor-owned blur. No screen capture, desktop pixels or extra permissions."""
import ctypes as C
import sys

from PySide6.QtGui import QGuiApplication

_MAC_PANEL_CLASS = None


class Backdrop:
    def __init__(self, widget):
        self.widget = widget
        self.panel = None
        self.mac_front = None
        self.hwnd = None
        self.display = self.x = None
        self.atom = 0
        self.error = ''

    def show(self):
        self.close()
        self.error = ''
        if QGuiApplication.platformName() in {'offscreen', 'minimal'}:
            return False
        try:
            if sys.platform == 'darwin':
                return self.mac()
            if sys.platform == 'win32':
                return self.windows()
            if sys.platform.startswith('linux') and QGuiApplication.platformName() == 'xcb':
                return self.linux()
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
            self.close()
        return False

    def mac(self):
        global _MAC_PANEL_CLASS
        import AppKit as A
        import objc
        if A.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency():
            return False
        # A separate noninteractive panel keeps Qt's dragging destination intact.
        # Both windows are ordered together and live only for this drop gesture.
        if _MAC_PANEL_CLASS is None:
            class MouseShareBackdropPanel(A.NSPanel):
                def canBecomeKeyWindow(self):
                    return False
                def canBecomeMainWindow(self):
                    return False
            _MAC_PANEL_CLASS = MouseShareBackdropPanel
        view = objc.objc_object(c_void_p=int(self.widget.winId()))
        front = view.window()
        if front is None:
            return False
        panel = _MAC_PANEL_CLASS.alloc().initWithContentRect_styleMask_backing_defer_(
            front.frame(), A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel,
            A.NSBackingStoreBuffered, False)
        self.panel = panel
        panel.setReleasedWhenClosed_(False)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(A.NSColor.clearColor())
        panel.setHasShadow_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setIgnoresMouseEvents_(True)
        behavior = (A.NSWindowCollectionBehaviorCanJoinAllSpaces | A.NSWindowCollectionBehaviorFullScreenAuxiliary
                    | A.NSWindowCollectionBehaviorIgnoresCycle)
        panel.setCollectionBehavior_(behavior)
        panel.setLevel_(A.NSStatusWindowLevel)
        front.setLevel_(A.NSStatusWindowLevel)
        if front.isKindOfClass_(A.NSPanel):
            front.setStyleMask_(int(front.styleMask()) | A.NSWindowStyleMaskNonactivatingPanel)
            front.setBecomesKeyOnlyIfNeeded_(True)
        front.setCollectionBehavior_((int(front.collectionBehavior())
                                      & ~A.NSWindowCollectionBehaviorMoveToActiveSpace) | behavior)
        effect = A.NSVisualEffectView.alloc().initWithFrame_(panel.contentView().bounds())
        effect.setMaterial_(A.NSVisualEffectMaterialFullScreenUI)
        effect.setBlendingMode_(A.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(A.NSVisualEffectStateActive)
        effect.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameVibrantDark))
        effect.setAutoresizingMask_(A.NSViewWidthSizable | A.NSViewHeightSizable)
        panel.setContentView_(effect)
        front.addChildWindow_ordered_(panel, A.NSWindowBelow)
        self.mac_front = front
        panel.orderFrontRegardless()
        front.orderWindow_relativeTo_(A.NSWindowAbove, panel.windowNumber())
        return True

    def windows(self):
        from ctypes import wintypes as W
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                if winreg.QueryValueEx(key, 'EnableTransparency')[0] == 0:
                    return False
        except OSError:
            pass
        user, dwm = C.windll.user32, C.windll.dwmapi
        user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int,
                                       C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
        user.CreateWindowExW.restype = W.HWND
        user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
        user.ShowWindow.argtypes = [W.HWND, C.c_int]
        dwm.DwmSetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
        dwm.DwmSetWindowAttribute.restype = C.c_long
        class Margins(C.Structure):
            _fields_ = [(key, C.c_int) for key in ('left', 'right', 'top', 'bottom')]
        dwm.DwmExtendFrameIntoClientArea.argtypes = [W.HWND, C.POINTER(Margins)]
        front = int(self.widget.winId())
        rect = W.RECT()
        if not user.GetWindowRect(front, C.byref(rect)):
            return False
        # The blur window is deliberately not layered; DWM owns its entire frame.
        # The transparent Qt window above it remains the only file drop target.
        self.hwnd = user.CreateWindowExW(0x08000000 | 0x80 | 0x20 | 0x8, 'Static', 'MouseShare backdrop',
                                        0x80000000, rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top,
                                        None, None, None, None)
        if not self.hwnd:
            return False
        dark, acrylic = C.c_int(1), C.c_int(3)
        dwm.DwmSetWindowAttribute(self.hwnd, 20, C.byref(dark), C.sizeof(dark))
        margins = Margins(-1, -1, -1, -1)
        extended = dwm.DwmExtendFrameIntoClientArea(self.hwnd, C.byref(margins)) == 0
        enabled = dwm.DwmSetWindowAttribute(self.hwnd, 38, C.byref(acrylic), C.sizeof(acrylic)) == 0 and extended
        if not enabled:
            # Windows 10 compatibility: the optional compositor accent API may
            # be unavailable. Failure keeps the stronger translucent fallback.
            class Accent(C.Structure):
                _fields_ = [('state', C.c_int), ('flags', C.c_int), ('tint', W.DWORD), ('animation', C.c_int)]
            class Composition(C.Structure):
                _fields_ = [('attribute', C.c_int), ('data', C.c_void_p), ('size', C.c_size_t)]
            fn = getattr(user, 'SetWindowCompositionAttribute', None)
            if fn:
                fn.argtypes, fn.restype = [W.HWND, C.POINTER(Composition)], W.BOOL
                accent = Accent(4, 2, 0xB8241C16, 0)
                data = Composition(19, C.cast(C.pointer(accent), C.c_void_p), C.sizeof(accent))
                enabled = bool(fn(self.hwnd, C.byref(data)))
        if not enabled:
            self.close()
            return False
        user.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
        user.SetWindowPos(self.hwnd, front, rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top, 0x10)
        return True

    def linux(self):
        import ctypes.util
        name = ctypes.util.find_library('X11')
        if not name:
            return False
        x = self.x = C.CDLL(name)
        D, U, P = C.c_void_p, C.c_ulong, C.POINTER
        for method, result, args in [
            ('XOpenDisplay', D, [C.c_char_p]), ('XCloseDisplay', C.c_int, [D]),
            ('XDefaultRootWindow', U, [D]), ('XDefaultScreen', C.c_int, [D]),
            ('XInternAtom', U, [D, C.c_char_p, C.c_int]), ('XGetSelectionOwner', U, [D, U]),
            ('XGetWindowProperty', C.c_int, [D, U, U, C.c_long, C.c_long, C.c_int, U,
                                           P(U), P(C.c_int), P(U), P(U), P(P(C.c_ubyte))]),
            ('XChangeProperty', C.c_int, [D, U, U, U, C.c_int, C.c_int, P(C.c_ubyte), C.c_int]),
            ('XDeleteProperty', C.c_int, [D, U, U]), ('XFree', C.c_int, [C.c_void_p]),
            ('XFlush', C.c_int, [D]),
        ]:
            fn = getattr(x, method)
            fn.restype, fn.argtypes = result, args
        self.display = x.XOpenDisplay(None)
        if not self.display:
            return False
        atom = x.XInternAtom(self.display, b'_KDE_NET_WM_BLUR_BEHIND_REGION', True)
        supported = x.XInternAtom(self.display, b'_NET_SUPPORTED', True)
        compositor = x.XInternAtom(self.display, ('_NET_WM_CM_S'+str(x.XDefaultScreen(self.display))).encode(), True)
        if not atom or not supported or not compositor or not x.XGetSelectionOwner(self.display, compositor):
            self.close()
            return False
        actual, count, remaining = U(), U(), U()
        fmt, data = C.c_int(), P(C.c_ubyte)()
        result = x.XGetWindowProperty(self.display, x.XDefaultRootWindow(self.display), supported,
                                      0, 4096, False, 4, C.byref(actual), C.byref(fmt), C.byref(count),
                                      C.byref(remaining), C.byref(data))
        try:
            found = result == 0 and fmt.value == 32 and count.value <= 4096 and bool(data)
            if not found or atom not in list(C.cast(data, P(U))[:count.value]):
                self.close()
                return False
        finally:
            if data:
                x.XFree(data)
        self.atom = atom
        x.XChangeProperty(self.display, int(self.widget.winId()), atom, 6, 32, 0, None, 0)
        x.XFlush(self.display)
        return True

    def close(self):
        if self.panel:
            if self.mac_front:
                self.mac_front.removeChildWindow_(self.panel)
                self.mac_front = None
            self.panel.orderOut_(None)
            self.panel.close()
            self.panel = None
        if self.hwnd:
            from ctypes import wintypes as W
            user = C.windll.user32
            user.DestroyWindow.argtypes = [W.HWND]
            user.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.display:
            if self.atom:
                self.x.XDeleteProperty(self.display, int(self.widget.winId()), self.atom)
            self.x.XCloseDisplay(self.display)
            self.display, self.atom = None, 0
