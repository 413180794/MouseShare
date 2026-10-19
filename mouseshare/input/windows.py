"""Windows hooks on a dedicated message-loop thread; SendInput for tagged injection."""
import ctypes as C
import threading
from ctypes import wintypes as W

from ..i18n import tr
from .base import MARKER, BaseBackend
from .keymap import HID_TO_WIN, WIN_SCANS
from .windows_cursor import WindowsCursorShield

U = C.WinDLL("user32", use_last_error=True)
K = C.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = C.c_size_t
LRESULT = C.c_ssize_t
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


class WindowClass(C.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int),
                ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HANDLE),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HANDLE),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


class RawInputDevice(C.Structure):
    _fields_ = [("usUsagePage", W.USHORT), ("usUsage", W.USHORT),
                ("dwFlags", W.DWORD), ("hwndTarget", W.HWND)]


class RawInputHeader(C.Structure):
    _fields_ = [("dwType", W.DWORD), ("dwSize", W.DWORD),
                ("hDevice", W.HANDLE), ("wParam", W.WPARAM)]


class RawMouse(C.Structure):
    # ulButtons represents the aligned button union in RAWMOUSE.
    _fields_ = [("usFlags", W.USHORT), ("ulButtons", W.ULONG), ("ulRawButtons", W.ULONG),
                ("lLastX", W.LONG), ("lLastY", W.LONG), ("ulExtraInformation", W.ULONG)]


class RawMouseInput(C.Structure):
    _fields_ = [("header", RawInputHeader), ("mouse", RawMouse)]


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
U.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
U.GetCursorPos.restype = W.BOOL
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
U.MonitorFromWindow.restype = W.HANDLE
U.GetMonitorInfoW.argtypes = [W.HANDLE, C.c_void_p]
U.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
U.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
U.OpenInputDesktop.restype = W.HANDLE
U.GetUserObjectInformationW.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
U.CloseDesktop.argtypes = [W.HANDLE]
U.RegisterClassW.argtypes = [C.POINTER(WindowClass)]
U.RegisterClassW.restype = W.WORD
U.UnregisterClassW.argtypes = [W.LPCWSTR, W.HINSTANCE]
U.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                            C.c_int, C.c_int, C.c_int, C.c_int,
                            W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
U.CreateWindowExW.restype = W.HWND
U.DestroyWindow.argtypes = [W.HWND]
U.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.DefWindowProcW.restype = LRESULT
U.RegisterRawInputDevices.argtypes = [C.POINTER(RawInputDevice), W.UINT, W.UINT]
U.GetRawInputData.argtypes = [W.HANDLE, W.UINT, C.c_void_p, C.POINTER(W.UINT), W.UINT]
U.GetRawInputData.restype = W.UINT
U.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
U.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
U.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]
U.DispatchMessageW.restype = LRESULT
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
        self.last = None
        self.raw_absolute = {}
        self.raw_window = None
        self.thread_id = 0
        self.started = threading.Event()
        self.mouse_hook = self.key_hook = None
        self._cursor_shield = WindowsCursorShield()
        self.captured_moves = self.edge_pressure_moves = self.stationary_hook_moves = 0

    def cursor_hidden(self, hidden):
        self._cursor_shield.set_enabled(hidden)
        self.cursor_is_hidden = bool(hidden)

    def focus_token(self):
        hwnd = U.GetForegroundWindow()
        if not hwnd:
            return None
        pid = W.DWORD()
        U.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return int(hwnd), pid.value

    def bounds(self):
        return tuple(U.GetSystemMetrics(k) for k in (76, 77, 78, 79))

    def monitors(self):
        return self.cached_monitors(self.read_monitors)

    def read_monitors(self):
        result = []
        callback = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
        def collect(handle, dc, rect, data):
            r = rect.contents
            result.append(dict(id=str(handle), x=r.left, y=r.top, w=r.right-r.left, h=r.bottom-r.top,
                               primary=r.left == 0 and r.top == 0))
            return True
        fn = callback(collect)
        U.EnumDisplayMonitors.argtypes = [W.HDC, C.POINTER(W.RECT), callback, W.LPARAM]
        U.EnumDisplayMonitors.restype = W.BOOL
        if not U.EnumDisplayMonitors(None, None, fn, 0) or not result:
            raise C.WinError(C.get_last_error())
        return result

    def start(self):
        if self.running:
            return
        self.error = ""
        self.started.clear()
        threading.Thread(target=self.run, daemon=True, name="Windows-input-hooks").start()
        self.started.wait(3)

    def run(self):
        self.thread_id = K.GetCurrentThreadId()
        self._mouse_callback = HOOKPROC(self.mouse_proc)
        self._key_callback = HOOKPROC(self.key_proc)
        self._window_callback = WNDPROC(self.window_proc)
        module = K.GetModuleHandleW(None)
        class_name = f"MouseShareRawInput-{id(self)}"
        registered = False
        try:
            window_class = WindowClass(lpfnWndProc=self._window_callback,
                                       hInstance=module, lpszClassName=class_name)
            registered = bool(U.RegisterClassW(C.byref(window_class)))
            if not registered:
                raise C.WinError(C.get_last_error())
            self.raw_window = U.CreateWindowExW(0, class_name, "", 0, 0, 0, 0, 0,
                                               W.HWND(-3), None, module, None)
            if not self.raw_window:
                raise C.WinError(C.get_last_error())
            device = RawInputDevice(1, 2, 0x100, self.raw_window)  # RIDEV_INPUTSINK
            if not U.RegisterRawInputDevices(C.byref(device), 1, C.sizeof(device)):
                raise C.WinError(C.get_last_error())
            self.mouse_hook = U.SetWindowsHookExW(14, self._mouse_callback, module, 0)
            self.key_hook = U.SetWindowsHookExW(13, self._key_callback, module, 0)
            if not self.mouse_hook or not self.key_hook:
                raise C.WinError(C.get_last_error())
            self.running = True
            self.started.set()
            msg = W.MSG()
            while self.running and U.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                U.TranslateMessage(C.byref(msg))
                U.DispatchMessageW(C.byref(msg))
        except OSError:
            self.error = tr('无法启动 Windows 原始鼠标输入，请重启 MouseShare')
        finally:
            for hook in (self.mouse_hook, self.key_hook):
                if hook:
                    U.UnhookWindowsHookEx(hook)
            if self.raw_window:
                device = RawInputDevice(1, 2, 1, None)  # RIDEV_REMOVE
                U.RegisterRawInputDevices(C.byref(device), 1, C.sizeof(device))
                U.DestroyWindow(self.raw_window)
                self.raw_window = None
            if registered:
                U.UnregisterClassW(class_name, module)
            self.running = False
            self.captured = False
            self._cursor_shield.set_enabled(False)
            self.started.set()

    def capture(self, enabled):
        if enabled:
            self._cursor_shield.set_enabled(True)
        self.captured = bool(enabled)
        if not enabled:
            self._cursor_shield.set_enabled(False)
        self.raw_absolute.clear()
        self.last = None

    def window_proc(self, hwnd, msg, wparam, lparam):
        if msg == 0x00FF:  # WM_INPUT
            try:
                size = W.UINT()
                header_size = C.sizeof(RawInputHeader)
                if U.GetRawInputData(lparam, 0x10000003, None, C.byref(size), header_size) != 0:
                    raise OSError("Raw input size unavailable")
                if not header_size <= size.value <= 65536:
                    raise OSError("Invalid raw input size")
                buffer = C.create_string_buffer(size.value)
                count = U.GetRawInputData(lparam, 0x10000003, buffer, C.byref(size), header_size)
                if count != size.value:
                    raise OSError("Raw input read failed")
                if count >= C.sizeof(RawMouseInput):
                    packet = C.cast(buffer, C.POINTER(RawMouseInput)).contents
                    if packet.header.dwType == 0 and packet.header.dwSize == count:
                        self.raw_motion(packet.mouse, packet.header.hDevice)
            except Exception:
                self.capture(False)
                self.emit({"type": "command", "action": "panic"})
        # Required for foreground WM_INPUT cleanup, also handles window creation.
        return U.DefWindowProcW(hwnd, msg, wparam, lparam)

    def raw_motion(self, mouse, device):
        if mouse.ulExtraInformation == MARKER:
            return
        dx, dy = mouse.lLastX, mouse.lLastY
        if mouse.usFlags & 1:  # absolute devices (tablets / some remote sessions)
            metrics = (76, 77, 78, 79) if mouse.usFlags & 2 else (None, None, 0, 1)
            width, height = U.GetSystemMetrics(metrics[2]), U.GetSystemMetrics(metrics[3])
            point = (dx * max(1, width - 1) / 65535, dy * max(1, height - 1) / 65535)
            previous = self.raw_absolute.get(device)
            self.raw_absolute[device] = point
            if previous is None:
                return
            dx, dy = point[0] - previous[0], point[1] - previous[1]
        if dx or dy:
            # Raw deltas remain available at the screen edge. The LL hook below
            # suppresses the local pointer; no recenter/warp is involved.
            x = y = 0
            if not self.captured:
                point = W.POINT()
                if not U.GetCursorPos(C.byref(point)):
                    return
                x, y = point.x, point.y
                left, top, width, height = self.monitor_at((x, y))
                # A clamped cursor (or a missing first hook baseline) has zero
                # screen displacement even while the device pushes outward.
                # Only supplement edge pressure; regular local movement stays
                # on the LL hook to avoid duplicate motion/takeover events.
                if not (dx < 0 and x <= left+2 or dx > 0 and x >= left+width-3
                        or dy < 0 and y <= top+2 or dy > 0 and y >= top+height-3):
                    return
                self.edge_pressure_moves += 1
            else:
                self.captured_moves += 1
            self.physical({"type": "move", "x": x, "y": y, "dx": dx, "dy": dy})

    def mouse_proc(self, code, msg, pointer):
        if code < 0:
            return U.CallNextHookEx(None, code, msg, pointer)
        try:
            data = C.cast(pointer, C.POINTER(MouseHook)).contents
            if data.dwExtraInfo == MARKER:
                if msg == 0x0200 and not self.captured:
                    # Our tagged return/injection establishes the coordinate
                    # baseline, while remaining invisible to physical input.
                    self.last = (data.pt.x, data.pt.y)
                return U.CallNextHookEx(None, code, msg, pointer)
            if data.flags & 1:
                return U.CallNextHookEx(None, code, msg, pointer)
            x, y = data.pt.x, data.pt.y
            if msg == 0x0200:
                if self.captured:
                    return 1
                dx, dy = (0, 0) if self.last is None else (x - self.last[0], y - self.last[1])
                stationary = self.last == (x, y)
                self.last = (x, y)
                if stationary:
                    self.stationary_hook_moves += 1
                    return U.CallNextHookEx(None, code, msg, pointer)
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
                    if key is None:
                        # Some firmware / keyboard layouts omit a scan code.
                        # Prefer the physical code, then ask Windows for its VK mapping.
                        key = WIN_SCANS.get(U.MapVirtualKeyW(data.vkCode, 4))
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
                              0, 0x8000 | 0x4000 | 0x2000 | 0x0001, 0, MARKER)
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

    def desktop_active(self):
        desktop = U.OpenInputDesktop(0, False, 1)
        if not desktop:
            return False
        try:
            name = C.create_unicode_buffer(256)
            needed = W.DWORD()
            return bool(U.GetUserObjectInformationW(desktop, 2, name, C.sizeof(name), C.byref(needed))
                        and name.value.casefold() == "default")
        finally:
            U.CloseDesktop(desktop)

    def stop(self):
        super().stop()
        if self.thread_id:
            U.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)

