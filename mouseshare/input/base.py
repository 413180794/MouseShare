"""Common native callback handling. Callbacks never perform network or disk I/O."""
import threading
import time

from ..i18n import tr

MARKER = 0x4D534852
CTRL = {224, 228}
ALT = {226, 230}


class BaseBackend:
    shortcuts = {41: "panic", 69: "game", 6: "share_copy", 25: "share_paste", 44: "switch_peer"}
    shortcut_modifiers = (CTRL, ALT)
    copy_modifier = CTRL
    def __init__(self, emit):
        self.emit = emit
        self.captured = False
        self.running = False
        self.error = ""
        self.keys = set()
        self.buttons = set()
        self.injected_keys = set()
        self.injected_buttons = set()
        self.inject_lock = threading.RLock()
        self.hotkey_keys = set()
        self.last_local = time.monotonic()
        self.native_file_paste_ready = False
        self.sharing_shortcuts_enabled = False
        self.switch_shortcut_enabled = False
        self.cursor_is_hidden = False
        self.recovered_releases = 0
        self._monitors, self.monitor_checked = [], 0

    def physical(self, event):
        self.last_local = time.monotonic()
        if event["type"] == "key":
            key, down = event["key"], event["down"]
            if down:
                self.keys.add(key)
            else:
                self.keys.discard(key)
            if key in self.hotkey_keys:
                if not down:
                    self.hotkey_keys.discard(key)
                return True
            modifiers = (CTRL, ALT) if key in {6, 25, 44} else self.shortcut_modifiers
            action = self.shortcuts.get(key) if all(self.keys & group for group in modifiers) else None
            if (key in {6, 25, 44} and self.copy_modifier == CTRL and 230 in self.keys and 226 not in self.keys):
                action = None  # AltGr must continue producing layout-specific characters.
            if action in {'share_copy', 'share_paste'} and not self.sharing_shortcuts_enabled:
                action = None
            if action == 'switch_peer' and not self.switch_shortcut_enabled:
                action = None
            if (down and key == 25 and self.native_file_paste_ready and self.keys & self.copy_modifier
                    and not self.keys & (ALT | {225, 229})):
                action = 'share_paste'
            if down and action:
                self.hotkey_keys.add(key)
                if action in {'panic', 'game'}:
                    self.capture(False)
                self.emit({"type": "command", "action": action})
                return True
        elif event["type"] == "button":
            if event["down"]:
                self.buttons.add(event["button"])
            else:
                self.buttons.discard(event["button"])
        captured = self.captured
        accepted = self.emit(event)
        if accepted is False:
            self.capture(False)
        return captured and accepted is not False

    def capture(self, enabled):
        self.captured = enabled

    def cursor_hidden(self, hidden):
        self.cursor_is_hidden = bool(hidden)

    def focus_token(self):
        return None

    def reconcile_physical(self):
        """Platforms may recover releases missed while native monitoring was interrupted."""
        return None

    def clipboard_shortcut(self, action):
        # A clipboard callback runs on the GUI thread while the input owner can
        # release remote keys. Keep the entire synthetic chord atomic with both.
        with self.inject_lock:
            self.release_all()
            for modifier in range(224, 232):
                self.key(modifier, False)
            modifier = min(self.copy_modifier)
            key = 6 if action == 'copy' else 25
            try:
                self.key(modifier, True)
                self.key(key, True)
                self.key(key, False)
            finally:
                self.key(modifier, False)

    def ready(self):
        return self.running and not self.error

    def permissions(self, request=False):
        return True

    def permission_status(self):
        return {}

    def bounds(self):
        return (0, 0, 1920, 1080)

    def monitors(self):
        x, y, w, h = self.bounds()
        return [dict(id='primary', x=int(x), y=int(y), w=int(w), h=int(h), primary=True)]

    def cached_monitors(self, read):
        now = time.monotonic()
        if not self._monitors or now-self.monitor_checked >= 1:
            self._monitors = read()
            self.monitor_checked = now
        return self._monitors

    def screen_info(self):
        from ..displays import union
        monitors = self.monitors()
        x, y, w, h = union(monitors)
        return dict(x=int(x), y=int(y), w=int(w), h=int(h), monitors=monitors)

    def monitor_at(self, point):
        from ..displays import project
        screen = self.screen_info()
        x, y = project(point, screen)
        monitor = next(m for m in screen['monitors'] if m['x'] <= x < m['x']+m['w']
                       and m['y'] <= y < m['y']+m['h'])
        return tuple(monitor[k] for k in ('x', 'y', 'w', 'h'))

    def foreground(self):
        return "", False

    def desktop_active(self):
        return True

    def release_all(self):
        with self.inject_lock:
            for key in list(self.injected_keys):
                self.key(key, False)
            for button in list(self.injected_buttons):
                self.button(button, False)
            self.injected_keys.clear()
            self.injected_buttons.clear()

    def stop(self):
        self.capture(False)
        self.release_all()
        self.running = False


class NullBackend(BaseBackend):
    """Headless test backend for state-machine tests and unsupported platforms."""
    def start(self):
        self.error = tr('当前平台缺少原生键鼠输入服务')

    def move(self, x, y):
        pass

    def key(self, key, down):
        self.injected_keys.add(key) if down else self.injected_keys.discard(key)

    def button(self, button, down):
        self.injected_buttons.add(button) if down else self.injected_buttons.discard(button)

    def scroll(self, dx, dy):
        pass

