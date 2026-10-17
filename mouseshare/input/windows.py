"""Windows hooks on a dedicated message-loop thread; SendInput for tagged injection."""
import ctypes as C
import threading
from ctypes import wintypes as W

from .base import MARKER, BaseBackend
from .keymap import HID_TO_WIN, WIN_SCANS

U = C.WinDLL("user32", use_last_error=True)
K = C.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = C.c_size_t
LRESULT = C.c_ssize_t
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)


class MouseHook(C.Structure):
    _fields_ = [("pt", W.POINT), ("mouseData", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KeyHook(C.Structure):
    _fields_ = [("vkCode", W.DWORD), ("scanCode", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MouseInput(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KeyInput(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HardwareInput(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class InputUnion(C.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyInput), ("hi", HardwareInput)]


class Input(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", W.DWORD), ("data", InputUnion)]


# Explicit pointer-sized signatures are required on Windows x64.
U.SetWindowsHookExW.argtypes = [C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]
U.SetWindowsHookExW.restype = W.HANDLE
U.CallNextHookEx.argtypes = [W.HANDLE, C.c_int, W.WPARAM, W.LPARAM]
U.CallNextHookEx.restype = LRESULT
U.UnhookWindowsHookEx.argtypes = [W.HANDLE]
U.SendInput.argtypes = [W.UINT, C.POINTER(Input), C.c_int]
U.SendInput.restype = W.UINT
U.GetForegroundWindow.restype = W.HWND
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
U.MonitorFromWindow.restype = W.HANDLE
U.GetMonitorInfoW.argtypes = [W.HANDLE, C.c_void_p]
U.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
K.GetModuleHandleW.argtypes = [W.LPCWSTR]
K.GetModuleHandleW.restype = W.HMODULE
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
K.CloseHandle.argtypes = [W.HANDLE]


class MonitorInfo(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


class WindowsBackend(BaseBackend):
    def __init__(self, emit):
        super().__init__(emit)
        self.anchor = (0, 0)
        self.last = None
        self.thread_id = 0
        self.started = threading.Event()
        self.mouse_hook = self.key_hook = None

    def bounds(self):
        return (0, 0, U.GetSystemMetrics(0), U.GetSystemMetrics(1))

    def start(self):
        self.error = ""
        threading.Thread(target=self.run, daemon=True, name="Windows-input-hooks").start()
        self.started.wait(3)

    def run(self):
        self.thread_id = K.GetCurrentThreadId()
        self._mouse_callback = HOOKPROC(self.mouse_proc)
        self._key_callback = HOOKPROC(self.key_proc)
        module = K.GetModuleHandleW(None)
        self.mouse_hook = U.SetWindowsHookExW(14, self._mouse_callback, module, 0)
        self.key_hook = U.SetWindowsHookExW(13, self._key_callback, module, 0)
        self.running = bool(self.mouse_hook and self.key_hook)
        if not self.running:
            self.error = "无法安装 Windows 输入钩子，请重启 MouseShare"
        self.started.set()
        try:
            msg = W.MSG()
            while self.running and U.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                U.TranslateMessage(C.byref(msg))
                U.DispatchMessageW(C.byref(msg))
        finally:
            for hook in (self.mouse_hook, self.key_hook):
                if hook:
                    U.UnhookWindowsHookEx(hook)
            self.running = False
            self.captured = False

    def capture(self, enabled):
        if enabled and not self.captured:
            x, y, width, height = self.bounds()
            self.anchor = (x + width // 2, y + height // 2)
            self.captured = True
            self.move(*self.anchor)
        else:
            self.captured = enabled
        self.last = None

    def mouse_proc(self, code, msg, pointer):
        if code < 0:
            return U.CallNextHookEx(None, code, msg, pointer)
        try:
            data = C.cast(pointer, C.POINTER(MouseHook)).contents
            if data.dwExtraInfo == MARKER or data.flags & 1:
                return U.CallNextHookEx(None, code, msg, pointer)
            x, y = data.pt.x, data.pt.y
            if msg == 0x0200:
                if self.captured:
                    dx, dy = x - self.anchor[0], y - self.anchor[1]
                    if dx == 0 and dy == 0:
                        return 1
                    self.move(*self.anchor)
                else:
                    dx, dy = (0, 0) if self.last is None else (x - self.last[0], y - self.last[1])
                    self.last = (x, y)
                event = {"type": "move", "x": x, "y": y, "dx": dx, "dy": dy}
            elif msg in (0x020A, 0x020E):
                amount = C.c_short(data.mouseData >> 16).value / 120
                event = {"type": "scroll", "dx": amount if msg == 0x020E else 0,
                         "dy": amount if msg == 0x020A else 0}
            else:
                buttons = {0x0201: (1, True), 0x0202: (1, False), 0x0204: (2, True),
                           0x0205: (2, False), 0x0207: (3, True), 0x0208: (3, False)}
                if msg in (0x020B, 0x020C):
                    button, down = (4 if (data.mouseData >> 16) == 1 else 5), msg == 0x020B
                elif msg in buttons:
                    button, down = buttons[msg]
                else:
                    return U.CallNextHookEx(None, code, msg, pointer)
                event = {"type": "button", "button": button, "down": down}
            if self.physical(event):
                return 1
        except Exception:
            self.captured = False
            self.emit({"type": "command", "action": "panic"})
        return U.CallNextHookEx(None, code, msg, pointer)

    def key_proc(self, code, msg, pointer):
        if code >= 0:
            try:
                data = C.cast(pointer, C.POINTER(KeyHook)).contents
                if data.dwExtraInfo != MARKER and not data.flags & 0x10:
                    scan = data.scanCode | (0xE000 if data.flags & 1 else 0)
                    key = WIN_SCANS.get(scan)
                    if key and self.physical({"type": "key", "key": key,
                                              "down": msg in (0x0100, 0x0104)}):
                        return 1
                    if key is None and self.captured:
                        return 1
            except Exception:
                self.captured = False
                self.emit({"type": "command", "action": "panic"})
        return U.CallNextHookEx(None, code, msg, pointer)

    def send(self, value):
        if U.SendInput(1, C.byref(value), C.sizeof(Input)) != 1:
            raise OSError("SendInput blocked (check application privilege level)")

    def move(self, x, y):
        # Absolute virtual-desktop coordinates work with Windows display scaling.
        left, top = U.GetSystemMetrics(76), U.GetSystemMetrics(77)
        width, height = U.GetSystemMetrics(78), U.GetSystemMetrics(79)
        value = Input(type=0)
        value.mi = MouseInput(round((x - left) * 65535 / max(1, width - 1)),
                              round((y - top) * 65535 / max(1, height - 1)),
                              0, 0x8000 | 0x4000 | 0x0001, 0, MARKER)
        self.send(value)

    def key(self, key, down):
        scan = HID_TO_WIN.get(key)
        if scan is None:
            return
        with self.inject_lock:
            flags = 0x0008 | (0x0001 if scan & 0xE000 else 0) | (0 if down else 0x0002)
            value = Input(type=1)
            value.ki = KeyInput(0, scan & 0xFF, flags, 0, MARKER)
            self.send(value)
            self.injected_keys.add(key) if down else self.injected_keys.discard(key)

    def button(self, button, down):
        with self.inject_lock:
            flags = {1: (2, 4), 2: (8, 16), 3: (32, 64), 4: (128, 256), 5: (128, 256)}
            value = Input(type=0)
            value.mi = MouseInput(0, 0, (1 if button == 4 else 2) if button >= 4 else 0,
                                  flags[button][0 if down else 1], 0, MARKER)
            self.send(value)
            self.injected_buttons.add(button) if down else self.injected_buttons.discard(button)

    def scroll(self, dx, dy):
        for amount, flags in ((dx, 0x1000), (dy, 0x0800)):
            if amount:
                value = Input(type=0)
                value.mi = MouseInput(0, 0, int(amount * 120) & 0xFFFFFFFF, flags, 0, MARKER)
                self.send(value)

    def foreground(self):
        hwnd = U.GetForegroundWindow()
        if not hwnd:
            return "", False
        class_name = C.create_unicode_buffer(256)
        U.GetClassNameW(hwnd, class_name, 256)
        if class_name.value in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
            return "", False
        pid = W.DWORD()
        U.GetWindowThreadProcessId(hwnd, C.byref(pid))
        exe = ""
        handle = K.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                text = C.create_unicode_buffer(32768)
                size = W.DWORD(len(text))
                if K.QueryFullProcessImageNameW(handle, 0, text, C.byref(size)):
                    exe = text.value.rsplit("\\", 1)[-1]
            finally:
                K.CloseHandle(handle)
        rect = W.RECT()
        info = MonitorInfo(cbSize=C.sizeof(MonitorInfo))
        monitor = U.MonitorFromWindow(hwnd, 2)
        fullscreen = False
        if U.GetWindowRect(hwnd, C.byref(rect)) and U.GetMonitorInfoW(monitor, C.byref(info)):
            screen = info.rcMonitor
            fullscreen = (abs(rect.left - screen.left) <= 2 and abs(rect.top - screen.top) <= 2
                          and abs(rect.right - screen.right) <= 2 and abs(rect.bottom - screen.bottom) <= 2)
        return exe, fullscreen

    def stop(self):
        super().stop()
        if self.thread_id:
            U.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)

