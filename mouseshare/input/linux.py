"""X11 raw physical input + XTEST injection; active grabs keep the source at its edge."""
import ctypes as C
import ctypes.util
import os
import select
import threading
import time

from ..i18n import exception_text, tr
from .base import ALT, CTRL, BaseBackend
from .keymap import WIN_SCANS

EVDEV_TO_HID = {code: hid for code, hid in WIN_SCANS.items() if code < 0x80}
EVDEV_TO_HID.update({96: 88, 97: 228, 98: 84, 99: 70, 100: 230, 102: 74, 103: 82, 104: 75,
                     105: 80, 106: 79, 107: 77, 108: 81, 109: 78, 110: 73, 111: 76,
                     119: 72, 125: 227, 126: 231, 127: 101})
X11_TO_HID = {code + 8: hid for code, hid in EVDEV_TO_HID.items()}
HID_TO_X11 = {hid: code for code, hid in X11_TO_HID.items()}
BUTTONS = {1: 1, 3: 2, 2: 3, 8: 4, 9: 5}
HID_BUTTONS = {hid: code for code, hid in BUTTONS.items()}


def session_problem(environ=None):
    env = os.environ if environ is None else environ
    if env.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or env.get('WAYLAND_DISPLAY'):
        return tr('当前为 Wayland 会话。键鼠共享请注销后选择 X11／Xorg 会话；文件传输可继续使用。')
    if not env.get('DISPLAY'):
        return tr('未找到 X11 桌面。请在已登录的图形桌面中启动 MouseShare。')
    return ''


class Cookie(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int), ('display', C.c_void_p),
                ('extension', C.c_int), ('evtype', C.c_int), ('cookie', C.c_uint), ('data', C.c_void_p)]


class KeyEvent(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int), ('display', C.c_void_p),
                ('window', C.c_ulong), ('root', C.c_ulong), ('subwindow', C.c_ulong), ('time', C.c_ulong),
                ('x', C.c_int), ('y', C.c_int), ('x_root', C.c_int), ('y_root', C.c_int),
                ('state', C.c_uint), ('keycode', C.c_uint), ('same_screen', C.c_int)]


class Event(C.Union):
    _fields_ = [('cookie', Cookie), ('key', KeyEvent), ('pad', C.c_long * 24)]


class Valuators(C.Structure):
    _fields_ = [('mask_len', C.c_int), ('mask', C.POINTER(C.c_ubyte)), ('values', C.POINTER(C.c_double))]


class RawEvent(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int), ('display', C.c_void_p),
                ('extension', C.c_int), ('evtype', C.c_int), ('time', C.c_ulong), ('deviceid', C.c_int),
                ('sourceid', C.c_int), ('detail', C.c_int), ('flags', C.c_int),
                ('valuators', Valuators), ('raw_values', C.POINTER(C.c_double))]


class EventMask(C.Structure):
    _fields_ = [('deviceid', C.c_int), ('mask_len', C.c_int), ('mask', C.POINTER(C.c_ubyte))]


class DeviceInfo(C.Structure):
    _fields_ = [('deviceid', C.c_int), ('name', C.c_char_p), ('use', C.c_int), ('attachment', C.c_int),
                ('enabled', C.c_int), ('num_classes', C.c_int), ('classes', C.c_void_p)]


class Attributes(C.Structure):
    _fields_ = [('background_pixmap', C.c_ulong), ('background_pixel', C.c_ulong),
                ('border_pixmap', C.c_ulong), ('border_pixel', C.c_ulong), ('bit_gravity', C.c_int),
                ('win_gravity', C.c_int), ('backing_store', C.c_int), ('backing_planes', C.c_ulong),
                ('backing_pixel', C.c_ulong), ('save_under', C.c_int), ('event_mask', C.c_long),
                ('do_not_propagate_mask', C.c_long), ('override_redirect', C.c_int),
                ('colormap', C.c_ulong), ('cursor', C.c_ulong)]


class Color(C.Structure):
    _fields_ = [('pixel', C.c_ulong), ('red', C.c_ushort), ('green', C.c_ushort),
                ('blue', C.c_ushort), ('flags', C.c_char), ('pad', C.c_char)]


class Monitor(C.Structure):
    _fields_ = [('name', C.c_ulong), ('primary', C.c_int), ('automatic', C.c_int), ('noutput', C.c_int),
                ('x', C.c_int), ('y', C.c_int), ('width', C.c_int), ('height', C.c_int),
                ('mwidth', C.c_int), ('mheight', C.c_int), ('outputs', C.c_void_p)]


class SaverInfo(C.Structure):
    _fields_ = [('window', C.c_ulong), ('state', C.c_int), ('kind', C.c_int),
                ('til_or_since', C.c_ulong), ('idle', C.c_ulong), ('event_mask', C.c_ulong)]


_ERROR_HANDLERS = []  # Xlib retains function pointers for the life of the process.


class X11:
    def __init__(self):
        def lib(name):
            found = ctypes.util.find_library(name)
            if not found:
                raise OSError(tr('缺少 X11 系统库：{p0}。请按 Linux 安装说明安装依赖。', p0=name))
            return C.CDLL(found)
        self.x, self.xi, self.xt, self.rr, self.ss, self.xf = [lib(n) for n in ['X11', 'Xi', 'Xtst', 'Xrandr', 'Xss', 'Xfixes']]
        D, U, Int, P = C.c_void_p, C.c_ulong, C.c_int, C.POINTER
        specs = [
            (self.x, 'XInitThreads', Int, []), (self.x, 'XOpenDisplay', D, [C.c_char_p]),
            (self.x, 'XCloseDisplay', Int, [D]), (self.x, 'XDefaultRootWindow', U, [D]),
            (self.x, 'XDefaultScreen', Int, [D]), (self.x, 'XDisplayWidth', Int, [D, Int]),
            (self.x, 'XDisplayHeight', Int, [D, Int]), (self.x, 'XConnectionNumber', Int, [D]),
            (self.x, 'XPending', Int, [D]), (self.x, 'XNextEvent', Int, [D, P(Event)]),
            (self.x, 'XGetEventData', Int, [D, P(Cookie)]), (self.x, 'XFreeEventData', None, [D, P(Cookie)]),
            (self.x, 'XQueryExtension', Int, [D, C.c_char_p, P(Int), P(Int), P(Int)]),
            (self.x, 'XQueryPointer', Int, [D, U, P(U), P(U), P(Int), P(Int), P(Int), P(Int), P(C.c_uint)]),
            (self.x, 'XSync', Int, [D, Int]), (self.x, 'XFlush', Int, [D]),
            (self.x, 'XCreateWindow', U, [D, U, Int, Int, C.c_uint, C.c_uint, C.c_uint, Int, C.c_uint, D, U, P(Attributes)]),
            (self.x, 'XMapWindow', Int, [D, U]), (self.x, 'XDestroyWindow', Int, [D, U]),
            (self.x, 'XCreateBitmapFromData', U, [D, U, C.c_char_p, C.c_uint, C.c_uint]),
            (self.x, 'XCreatePixmapCursor', U, [D, U, U, P(Color), P(Color), C.c_uint, C.c_uint]),
            (self.x, 'XFreePixmap', Int, [D, U]), (self.x, 'XFreeCursor', Int, [D, U]),
            (self.x, 'XGrabPointer', Int, [D, U, Int, C.c_uint, Int, Int, U, U, U]),
            (self.x, 'XGrabKeyboard', Int, [D, U, Int, Int, Int, U]),
            (self.x, 'XUngrabPointer', Int, [D, U]), (self.x, 'XUngrabKeyboard', Int, [D, U]),
            (self.x, 'XGetInputFocus', Int, [D, P(U), P(Int)]),
            (self.x, 'XGrabKey', Int, [D, Int, C.c_uint, U, Int, Int, Int]),
            (self.x, 'XUngrabKey', Int, [D, Int, C.c_uint, U]),
            (self.xf, 'XFixesHideCursor', None, [D, U]), (self.xf, 'XFixesShowCursor', None, [D, U]),
            (self.xi, 'XIQueryVersion', Int, [D, P(Int), P(Int)]),
            (self.xi, 'XISelectEvents', Int, [D, U, P(EventMask), Int]),
            (self.xi, 'XIQueryDevice', P(DeviceInfo), [D, Int, P(Int)]),
            (self.xi, 'XIFreeDeviceInfo', None, [P(DeviceInfo)]),
            (self.xt, 'XTestQueryExtension', Int, [D, P(Int), P(Int), P(Int), P(Int)]),
            (self.xt, 'XTestFakeMotionEvent', Int, [D, Int, Int, Int, U]),
            (self.xt, 'XTestFakeRelativeMotionEvent', Int, [D, Int, Int, U]),
            (self.xt, 'XTestFakeKeyEvent', Int, [D, C.c_uint, Int, U]),
            (self.xt, 'XTestFakeButtonEvent', Int, [D, C.c_uint, Int, U]),
            (self.rr, 'XRRGetMonitors', P(Monitor), [D, U, Int, P(Int)]),
            (self.rr, 'XRRFreeMonitors', None, [P(Monitor)]),
            (self.rr, 'XRRQueryVersion', Int, [D, P(Int), P(Int)]),
            (self.ss, 'XScreenSaverQueryInfo', Int, [D, U, P(SaverInfo)]),
        ]
        for library, name, result, args in specs:
            fn = getattr(library, name)
            fn.restype, fn.argtypes = result, args
        if not self.x.XInitThreads():
            raise OSError(tr('无法初始化 X11 线程支持'))
        # Passive hotkeys may already be owned by the desktop. Preserve the
        # connection and record the failed grab instead of Xlib exiting.
        self.grab_errors = set()
        class Error(C.Structure):
            _fields_ = [('type', Int), ('display', D), ('resourceid', U), ('serial', U),
                        ('error_code', C.c_ubyte), ('request_code', C.c_ubyte), ('minor_code', C.c_ubyte)]
        handler = C.CFUNCTYPE(Int, D, P(Error))
        self.x.XSetErrorHandler.argtypes = [handler]
        self.x.XSetErrorHandler.restype = C.c_void_p
        previous = []
        def error_handler(display, error):
            if error.contents.request_code == 33:  # GrabKey / BadAccess
                self.grab_errors.add(error.contents.serial)
            elif previous and previous[0]:
                return handler(previous[0])(display, error)
            return 0
        self.error_handler = handler(error_handler)
        previous.append(self.x.XSetErrorHandler(self.error_handler))
        _ERROR_HANDLERS.append(self.error_handler)


def raw_axes(raw):
    if not 0 <= raw.valuators.mask_len <= 32:
        raise OSError(tr('无效的 X11 轴数据'))
    axes, index = {}, 0
    for bit in range(raw.valuators.mask_len * 8):
        if raw.valuators.mask[bit // 8] & (1 << (bit % 8)):
            axes[bit] = raw.raw_values[index]
            index += 1
    return axes


class LinuxBackend(BaseBackend):
    shortcuts = {41: 'panic', 10: 'game', 6: 'share_copy', 25: 'share_paste', 44: 'switch_peer'}
    shortcut_modifiers = (CTRL, ALT, {225, 229})
    def __init__(self, emit):
        super().__init__(emit)
        self.api = self.display = None
        self.root = self.opcode = self.window = self.cursor = 0
        self.lock = threading.RLock()
        self.started, self.stopping = threading.Event(), threading.Event()
        self.thread = None
        self.test_sources = set()
        self.session_locked = False
        self.saver_available = False
        self._bounds = (0, 0, 1920, 1080)
        self.scroll_remainder = [0.0, 0.0]
        self.shortcut_grabs = set()
        self.shortcut_grab_error = False
        self._monitors, self.monitor_checked = [], 0
        self.key_stamps = {}

    def open(self):
        if self.display:
            return
        problem = session_problem()
        if problem:
            raise OSError(problem)
        self.api = self.api or X11()
        display = self.api.x.XOpenDisplay(None)
        if not display:
            raise OSError(tr('无法访问当前 X11 桌面。请用登录桌面的普通用户启动，检查 DISPLAY 与 XAUTHORITY。'))
        self.display = display
        self.root = self.api.x.XDefaultRootWindow(display)
        opcode, event, error = C.c_int(), C.c_int(), C.c_int()
        self.saver_available = bool(self.api.x.XQueryExtension(display, b'MIT-SCREEN-SAVER',
                                    C.byref(opcode), C.byref(event), C.byref(error)))

    def permissions(self, request=False):
        try:
            with self.lock:
                self.open()
            return True
        except (OSError, AttributeError):
            return False

    def start(self):
        if self.running or self.thread and self.thread.is_alive():
            return
        self.started.clear()
        self.stopping.clear()
        self.error = ''
        self.thread = threading.Thread(target=self.run, daemon=True, name='X11-input')
        self.thread.start()
        self.started.wait(3)

    def run(self):
        try:
            with self.lock:
                self.open()
                x, xi, xt = self.api.x, self.api.xi, self.api.xt
                major, minor = C.c_int(2), C.c_int(2)
                if xi.XIQueryVersion(self.display, C.byref(major), C.byref(minor)) != 0 or (major.value, minor.value) < (2, 1):
                    raise OSError(tr('键鼠共享需要 XInput 2.1 或更新版本'))
                opcode, base, error = C.c_int(), C.c_int(), C.c_int()
                if not x.XQueryExtension(self.display, b'XInputExtension', C.byref(opcode), C.byref(base), C.byref(error)):
                    raise OSError(tr('当前 X11 服务未提供 XInput'))
                self.opcode = opcode.value
                a, b, c, d = [C.c_int() for _ in range(4)]
                if not xt.XTestQueryExtension(self.display, C.byref(a), C.byref(b), C.byref(c), C.byref(d)):
                    raise OSError(tr('当前 X11 服务未提供 XTEST'))
                count = C.c_int()
                devices = xi.XIQueryDevice(self.display, 0, C.byref(count))
                try:
                    self.test_sources = {devices[i].deviceid for i in range(count.value)
                                         if b'xtest' in (devices[i].name or b'').lower()}
                finally:
                    if devices:
                        xi.XIFreeDeviceInfo(devices)
                if not self.test_sources:
                    raise OSError(tr('无法识别 XTEST 注入设备，已停止以防输入回传'))
                bits = sum(1 << kind for kind in range(13, 18))
                mask = (C.c_ubyte * 4)(*(bits >> (8 * i) & 255 for i in range(4)))
                event_mask = EventMask(1, 4, mask)  # XIAllMasterDevices: no duplicate slave packets.
                if xi.XISelectEvents(self.display, self.root, C.byref(event_mask), 1) != 0:
                    raise OSError(tr('无法监听 X11 原始输入'))
                bitmap = x.XCreateBitmapFromData(self.display, self.root, b'\0', 1, 1)
                color = Color()
                self.cursor = x.XCreatePixmapCursor(self.display, bitmap, bitmap, C.byref(color), C.byref(color), 0, 0)
                x.XFreePixmap(self.display, bitmap)
                x.XSync(self.display, False)
                self.running = True
                self.started.set()
                fd = x.XConnectionNumber(self.display)
            while not self.stopping.is_set():
                packet = None
                with self.lock:
                    self.refresh_shortcut_grabs()
                    if x.XPending(self.display):
                        event = Event()
                        x.XNextEvent(self.display, C.byref(event))
                        cookie = event.cookie
                        if cookie.type == 35 and cookie.extension == self.opcode and x.XGetEventData(self.display, C.byref(cookie)):
                            try:
                                if 13 <= cookie.evtype <= 17:
                                    raw = C.cast(cookie.data, C.POINTER(RawEvent)).contents
                                    packet = (raw.evtype, raw.sourceid, raw.detail,
                                              raw_axes(raw) if raw.evtype == 17 else {}, raw.time)
                            finally:
                                x.XFreeEventData(self.display, C.byref(cookie))
                        elif cookie.type == 2:
                            packet = ('repeat', event.key.keycode, event.key.time)
                if packet:
                    if packet[0] == 'repeat':
                        self.core_key_press(packet[1], packet[2])
                    else:
                        self.raw_input(*packet)
                elif not x.XPending(self.display):
                    select.select([fd], [], [], 0.02)
        except Exception as exc:
            self.error = exception_text(exc) if isinstance(exc, OSError) else tr('X11 输入监听已安全停止，请重新检查')
            self.emit({'type': 'command', 'action': 'panic'})
        finally:
            self.running = False
            self.started.set()
            self.capture(False)

    def refresh_shortcut_grabs(self, suspend=False):
        desired = set()
        if not suspend and self.running:
            if self.sharing_shortcuts_enabled:
                desired.update((HID_TO_X11[key], 4 | 8 | shift | locks)
                               for key in (6, 25) for shift in (0, 1) for locks in (0, 2, 16, 18))
            if self.switch_shortcut_enabled:
                desired.update((HID_TO_X11[44], 4 | 8 | locks) for locks in (0, 2, 16, 18))
            if self.native_file_paste_ready:
                desired.update((HID_TO_X11[25], 4 | locks) for locks in (0, 2, 16, 18))
        x = self.api.x
        for key, modifiers in self.shortcut_grabs - desired:
            x.XUngrabKey(self.display, key, modifiers, self.root)
        for key, modifiers in desired - self.shortcut_grabs:
            x.XGrabKey(self.display, key, modifiers, self.root, False, 1, 1)
        if desired != self.shortcut_grabs:
            x.XSync(self.display, False)
            self.shortcut_grab_error = self.shortcut_grab_error or bool(self.api.grab_errors)
            self.api.grab_errors.clear()
        self.shortcut_grabs = desired

    def clipboard_shortcut(self, action):
        with self.lock:
            self.open()
            # End this client's passive key grab so the injected shortcut is
            # delivered to the existing focused application.
            self.api.x.XUngrabKeyboard(self.display, 0)
            self.refresh_shortcut_grabs(suspend=True)
            try:
                super().clipboard_shortcut(action)
                self.api.x.XSync(self.display, False)
            finally:
                self.refresh_shortcut_grabs()

    def position(self):
        with self.lock:
            self.open()
            root, child = C.c_ulong(), C.c_ulong()
            rx, ry, wx, wy = [C.c_int() for _ in range(4)]
            mask = C.c_uint()
            if not self.api.x.XQueryPointer(self.display, self.root, C.byref(root), C.byref(child),
                                            C.byref(rx), C.byref(ry), C.byref(wx), C.byref(wy), C.byref(mask)):
                return self._bounds[:2]
            return rx.value, ry.value

    def core_key_press(self, detail, stamp):
        hid = X11_TO_HID.get(detail)
        # Under an active keyboard grab Xorg repeats are core KeyPress events,
        # with no XI_RawKeyPress. Ignore the initial core/raw duplicate and never
        # echo XTEST keys: only a physically held, non-modifier key may repeat.
        if (self.captured and hid in self.keys and hid < 224 and self.key_stamps.get(detail) != stamp):
            self.key_stamps[detail] = stamp
            self.physical(dict(type='key', key=hid, down=True))

    def raw_input(self, kind, source, detail, axes, stamp=None):
        if source in self.test_sources:
            return
        if kind == 17:
            x, y = self.position()
            dx, dy = axes.get(0, 0), axes.get(1, 0)
            if dx or dy:
                self.physical(dict(type='move', x=x, y=y, dx=dx, dy=dy))
        elif kind in {13, 14}:
            hid = X11_TO_HID.get(detail)
            if hid:
                if kind == 13:
                    if stamp is not None and self.key_stamps.get(detail) == stamp:
                        return
                    self.key_stamps[detail] = stamp
                else:
                    self.key_stamps.pop(detail, None)
                self.physical(dict(type='key', key=hid, down=kind == 13))
        elif kind in {15, 16}:
            if detail in {4, 5, 6, 7}:
                if kind == 15:
                    self.physical(dict(type='scroll', dx={6: -1, 7: 1}.get(detail, 0),
                                       dy={4: 1, 5: -1}.get(detail, 0)))
            elif detail in BUTTONS:
                self.physical(dict(type='button', button=BUTTONS[detail], down=kind == 15))

    def capture(self, enabled):
        with self.lock:
            if not self.display:
                self.captured = False
                return
            x = self.api.x
            if not enabled:
                x.XUngrabPointer(self.display, 0)
                x.XUngrabKeyboard(self.display, 0)
                if self.window:
                    x.XDestroyWindow(self.display, self.window)
                    self.window = 0
                x.XFlush(self.display)
                self.captured = False
                return
            if self.captured:
                return
            px, py = self.position()
            attributes = Attributes(override_redirect=True)
            # A 1-pixel InputOnly window confines the system cursor at the handoff
            # coordinate. Raw motion remains relative and has no edge saturation.
            self.window = x.XCreateWindow(self.display, self.root, px, py, 1, 1, 0, 0, 2, None,
                                           1 << 9, C.byref(attributes))
            x.XMapWindow(self.display, self.window)
            x.XSync(self.display, False)
            pointer = x.XGrabPointer(self.display, self.window, False, (1 << 2) | (1 << 3) | (1 << 6),
                                    1, 1, self.window, self.cursor, 0)
            keyboard = x.XGrabKeyboard(self.display, self.window, False, 1, 1, 0)
            if pointer != 0 or keyboard != 0:
                self.capture(False)
                raise OSError(tr('键鼠正在被其他应用独占，请关闭占用后重新检查'))
            x.XSync(self.display, False)
            self.captured = True

    def bounds(self):
        from ..displays import union
        return union(self.monitors())

    def monitors(self):
        with self.lock:
            if self._monitors and time.monotonic()-self.monitor_checked < 1:
                return self._monitors
            try:
                self.open()
            except (OSError, AttributeError):
                x, y, w, h = self._bounds
                return [dict(id='primary', x=x, y=y, w=w, h=h, primary=True)]
            count = C.c_int()
            major, minor = C.c_int(), C.c_int()
            version = self.api.rr.XRRQueryVersion(self.display, C.byref(major), C.byref(minor))
            monitors = (self.api.rr.XRRGetMonitors(self.display, self.root, True, C.byref(count))
                        if version and (major.value, minor.value) >= (1, 5) else None)
            try:
                if monitors and count.value:
                    self._monitors = [dict(id=str(monitors[i].name), x=monitors[i].x, y=monitors[i].y,
                                           w=monitors[i].width, h=monitors[i].height, primary=bool(monitors[i].primary))
                                      for i in range(min(count.value, 16))
                                      if monitors[i].width >= 64 and monitors[i].height >= 64]
                else:
                    screen = self.api.x.XDefaultScreen(self.display)
                    self._monitors = [dict(id='primary', x=0, y=0, w=self.api.x.XDisplayWidth(self.display, screen),
                                           h=self.api.x.XDisplayHeight(self.display, screen), primary=True)]
                from ..displays import union
                self._bounds = union(self._monitors)
                self.monitor_checked = time.monotonic()
                return self._monitors
            finally:
                if monitors:
                    self.api.rr.XRRFreeMonitors(monitors)

    def move(self, x, y):
        with self.lock:
            self.open()
            self.api.xt.XTestFakeMotionEvent(self.display, -1, round(x), round(y), 0)
            self.api.x.XFlush(self.display)

    def key(self, key, down):
        code = HID_TO_X11.get(key)
        if code:
            with self.inject_lock, self.lock:
                self.open()
                if down and key in self.injected_keys:
                    # XTEST resets Xorg's repeat timer for duplicate presses.
                    # Let Xorg repeat the held key at the destination's rate.
                    return
                self.api.xt.XTestFakeKeyEvent(self.display, code, bool(down), 0)
                self.api.x.XFlush(self.display)
                self.injected_keys.add(key) if down else self.injected_keys.discard(key)

    def button(self, button, down):
        code = HID_BUTTONS.get(button)
        if code:
            with self.inject_lock, self.lock:
                self.open()
                self.api.xt.XTestFakeButtonEvent(self.display, code, bool(down), 0)
                self.api.x.XFlush(self.display)
                self.injected_buttons.add(button) if down else self.injected_buttons.discard(button)

    def scroll(self, dx, dy):
        with self.lock:
            self.open()
            for index, value in enumerate((dx, dy)):
                self.scroll_remainder[index] += value
                steps = int(self.scroll_remainder[index])
                self.scroll_remainder[index] -= steps
                code = (7 if steps > 0 else 6) if index == 0 else (4 if steps > 0 else 5)
                for _ in range(min(100, abs(steps))):
                    self.api.xt.XTestFakeButtonEvent(self.display, code, True, 0)
                    self.api.xt.XTestFakeButtonEvent(self.display, code, False, 0)
            self.api.x.XFlush(self.display)

    def desktop_active(self):
        if self.session_locked:
            return False
        with self.lock:
            if not self.display or not self.saver_available:
                return True  # File transfer is available without input permissions.
            info = SaverInfo()
            success = self.api.ss.XScreenSaverQueryInfo(self.display, self.root, C.byref(info))
            return not success or info.state != 1

    def focus_token(self):
        with self.lock:
            if not self.display:
                return None
            window, revert = C.c_ulong(), C.c_int()
            self.api.x.XGetInputFocus(self.display, C.byref(window), C.byref(revert))
            return window.value if window.value > 1 else None

    def cursor_hidden(self, hidden):
        with self.lock:
            if self.display and bool(hidden) != self.cursor_is_hidden:
                fn = self.api.xf.XFixesHideCursor if hidden else self.api.xf.XFixesShowCursor
                fn(self.display, self.root)
                self.api.x.XFlush(self.display)
            self.cursor_is_hidden = bool(hidden)

    def stop(self):
        self.stopping.set()
        self.cursor_hidden(False)
        super().stop()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(1)
        with self.lock:
            if self.display and (not self.thread or not self.thread.is_alive()):
                if self.cursor:
                    self.api.x.XFreeCursor(self.display, self.cursor)
                    self.cursor = 0
                self.api.x.XCloseDisplay(self.display)
                self.display = None
