"""Quartz event tap on its own run loop; tagged events avoid forwarding feedback."""
import threading

import Quartz as Q
import ApplicationServices as AX
from CoreFoundation import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
                            CFRunLoopGetCurrent, CFRunLoopRunInMode, kCFRunLoopCommonModes,
                            kCFRunLoopDefaultMode)

from .base import MARKER, BaseBackend
from .keymap import HID_TO_MAC, MAC_CODES


class MacBackend(BaseBackend):
    def __init__(self, emit):
        super().__init__(emit)
        self.tap = None
        self.started = threading.Event()
        self._flags = 0

    def permissions(self, request=False):
        if request:
            AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True})
            Q.CGRequestListenEventAccess()
        return bool(AX.AXIsProcessTrusted() and Q.CGPreflightListenEventAccess())

    def bounds(self):
        rect = Q.CGDisplayBounds(Q.CGMainDisplayID())
        return rect.origin.x, rect.origin.y, rect.size.width, rect.size.height

    def desktop_active(self):
        session = Q.CGSessionCopyCurrentDictionary()
        return bool(session and not session.get("CGSSessionScreenIsLocked", False)
                    and session.get("kCGSessionOnConsoleKey", True))

    def start(self):
        if self.running:
            return
        self.error = ""
        if not self.permissions():
            self.error = "需要辅助功能和输入监控权限；授权后点击重新检查"
            return
        self.started.clear()
        threading.Thread(target=self.run, daemon=True, name="Quartz-input-tap").start()
        self.started.wait(3)

    def run(self):
        kinds = [Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged,
                 Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDragged, Q.kCGEventRightMouseDragged,
                 Q.kCGEventOtherMouseDragged, Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp,
                 Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp,
                 Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp, Q.kCGEventScrollWheel]
        mask = sum(1 << kind for kind in kinds)
        self._callback = self.callback
        self.tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                     Q.kCGEventTapOptionDefault, mask, self._callback, None)
        if self.tap is None:
            self.error = "输入监听启动失败，请检查权限并重启 MouseShare"
            self.started.set()
            return
        source = CFMachPortCreateRunLoopSource(None, self.tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self.tap, True)
        self.running = True
        self.started.set()
        try:
            while self.running:
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, False)
        finally:
            self.captured = False
            Q.CGEventTapEnable(self.tap, False)

    def callback(self, proxy, kind, event, refcon):
        if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            self.captured = False
            self.emit({"type": "command", "action": "panic"})
            Q.CGEventTapEnable(self.tap, True)
            return event
        if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == MARKER:
            return event
        try:
            if kind in (Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged):
                code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                key = MAC_CODES.get(code)
                if key is None:
                    return None if self.captured else event
                if kind == Q.kCGEventFlagsChanged:
                    mask = {224: Q.kCGEventFlagMaskControl, 228: Q.kCGEventFlagMaskControl,
                            225: Q.kCGEventFlagMaskShift, 229: Q.kCGEventFlagMaskShift,
                            226: Q.kCGEventFlagMaskAlternate, 230: Q.kCGEventFlagMaskAlternate,
                            227: Q.kCGEventFlagMaskCommand, 231: Q.kCGEventFlagMaskCommand,
                            57: Q.kCGEventFlagMaskAlphaShift}.get(key, 0)
                    down = bool(Q.CGEventGetFlags(event) & mask) and key not in self.keys
                    # Caps Lock toggles a state; send a complete press on either transition.
                    if key == 57:
                        captured = self.physical({"type": "key", "key": key, "down": True})
                        self.physical({"type": "key", "key": key, "down": False})
                        return None if captured else event
                else:
                    down = kind == Q.kCGEventKeyDown
                message = {"type": "key", "key": key, "down": down}
            elif kind == Q.kCGEventScrollWheel:
                message = {"type": "scroll",
                           "dx": Q.CGEventGetDoubleValueField(event, Q.kCGScrollWheelEventDeltaAxis2),
                           "dy": Q.CGEventGetDoubleValueField(event, Q.kCGScrollWheelEventDeltaAxis1)}
            elif kind in (Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDragged,
                          Q.kCGEventRightMouseDragged, Q.kCGEventOtherMouseDragged):
                point = Q.CGEventGetLocation(event)
                message = {"type": "move", "x": point.x, "y": point.y,
                           "dx": Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventDeltaX),
                           "dy": Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventDeltaY)}
            else:
                native_button = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
                button = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}.get(native_button)
                if button is None:
                    return event
                message = {"type": "button", "button": button,
                           "down": kind in (Q.kCGEventLeftMouseDown, Q.kCGEventRightMouseDown,
                                            Q.kCGEventOtherMouseDown)}
            return None if self.physical(message) else event
        except Exception:
            self.captured = False
            self.emit({"type": "command", "action": "panic"})
            return event

    def post(self, event):
        Q.CGEventSetIntegerValueField(event, Q.kCGEventSourceUserData, MARKER)
        Q.CGEventPost(Q.kCGHIDEventTap, event)

    def move(self, x, y):
        if self.injected_buttons:
            button = min(self.injected_buttons)
            kind = {1: Q.kCGEventLeftMouseDragged, 2: Q.kCGEventRightMouseDragged}.get(
                button, Q.kCGEventOtherMouseDragged)
            native = button - 1
        else:
            kind, native = Q.kCGEventMouseMoved, 0
        self.post(Q.CGEventCreateMouseEvent(None, kind, (x, y), native))

    def key(self, key, down):
        code = HID_TO_MAC.get(key)
        if code is None:
            return
        with self.inject_lock:
            self.injected_keys.add(key) if down else self.injected_keys.discard(key)
            flags = 0
            for keys, mask in [({224, 228}, Q.kCGEventFlagMaskControl),
                               ({225, 229}, Q.kCGEventFlagMaskShift),
                               ({226, 230}, Q.kCGEventFlagMaskAlternate),
                               ({227, 231}, Q.kCGEventFlagMaskCommand)]:
                if self.injected_keys & keys:
                    flags |= mask
            event = Q.CGEventCreateKeyboardEvent(None, code, down)
            Q.CGEventSetFlags(event, flags)
            self.post(event)

    def button(self, button, down):
        with self.inject_lock:
            point = Q.CGEventGetLocation(Q.CGEventCreate(None))
            kind = {1: (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp),
                    2: (Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp)}.get(
                        button, (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp))[0 if down else 1]
            event = Q.CGEventCreateMouseEvent(None, kind, point, button - 1)
            # Quartz clients use click-state to recognize double and triple clicks.
            import time
            now = time.monotonic()
            if down:
                last_time, last_button, last_point, count = getattr(self, "_click", (0, 0, (0, 0), 0))
                close = abs(point.x - last_point[0]) + abs(point.y - last_point[1]) < 8
                count = count + 1 if button == last_button and now - last_time < 0.45 and close else 1
                self._click = (now, button, (point.x, point.y), count)
            count = getattr(self, "_click", (0, 0, (0, 0), 1))[3]
            Q.CGEventSetIntegerValueField(event, Q.kCGMouseEventClickState, count)
            self.post(event)
            self.injected_buttons.add(button) if down else self.injected_buttons.discard(button)

    def scroll(self, dx, dy):
        event = Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitLine, 2, round(dy), round(dx))
        self.post(event)

