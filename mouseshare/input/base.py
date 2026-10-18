"""Common native callback handling. Callbacks never perform network or disk I/O."""
import threading
import time

MARKER = 0x4D534852
CTRL = {224, 228}
ALT = {226, 230}


class BaseBackend:
    shortcuts = {41: "panic", 69: "game"}
    shortcut_modifiers = (CTRL, ALT)
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
            if down and all(self.keys & group for group in self.shortcut_modifiers) and key in self.shortcuts:
                self.hotkey_keys.add(key)
                self.capture(False)
                self.emit({"type": "command", "action": self.shortcuts[key]})
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

    def ready(self):
        return self.running and not self.error

    def permissions(self, request=False):
        return True

    def permission_status(self):
        return {}

    def bounds(self):
        return (0, 0, 1920, 1080)

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
        self.error = "当前平台缺少原生键鼠输入服务"

    def move(self, x, y):
        pass

    def key(self, key, down):
        self.injected_keys.add(key) if down else self.injected_keys.discard(key)

    def button(self, button, down):
        self.injected_buttons.add(button) if down else self.injected_buttons.discard(button)

    def scroll(self, dx, dy):
        pass

