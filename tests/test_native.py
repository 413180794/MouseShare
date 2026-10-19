"""Safe platform API checks; interactive input injection is covered by manual acceptance."""
import ctypes
import sys

import pytest

from mouseshare.input import create_backend
from mouseshare.input.keymap import HID_TO_MAC, HID_TO_WIN


@pytest.fixture(autouse=True)
def no_real_cursor_changes(monkeypatch):
    if sys.platform == 'win32':
        import mouseshare.input.windows as native
        class WindowsShield:
            panels = []
            def set_enabled(self, enabled):
                self.panels = [object()] if enabled else []
        monkeypatch.setattr(native, 'WindowsCursorShield', WindowsShield)
        return
    if sys.platform != "darwin":
        return
    from types import SimpleNamespace
    from mouseshare.input.macos import Q
    import mouseshare.input.macos as native
    class FakeShield:
        panels = []
        def set_enabled(self, enabled):
            self.panels = [object()] if enabled else []
    monkeypatch.setattr(native, "CursorShield", FakeShield)
    monkeypatch.setattr(Q, "CGEventCreate", lambda source: object())
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: SimpleNamespace(x=0, y=500))
    monkeypatch.setattr(Q, "CGEventSetLocation", lambda *args: None)
    monkeypatch.setattr(Q, "CGEventSetIntegerValueField", lambda *args: None)
    monkeypatch.setattr(Q, "CGWarpMouseCursorPosition", lambda point: 0)


def test_common_physical_keys_supported_on_both_platforms():
    for key in [*range(4, 30), 40, 41, 44, *range(58, 70), *range(79, 83), *range(224, 232)]:
        assert key in HID_TO_MAC
        assert key in HID_TO_WIN


@pytest.mark.skipif(sys.platform not in {"win32", "darwin"}, reason="Desktop OS only")
def test_native_api_loading():
    backend = create_backend(lambda event: True)
    assert isinstance(backend.permissions(), bool)
    assert isinstance(backend.desktop_active(), bool)
    assert backend.bounds()[2] > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="Mac TCC permissions")
def test_mac_permission_checks_are_independent_and_requests_are_scoped(monkeypatch):
    from mouseshare.input.macos import AX, Q, MacBackend
    calls = []
    monkeypatch.setattr(AX, "AXIsProcessTrusted", lambda: True)
    monkeypatch.setattr(Q, "CGPreflightListenEventAccess", lambda: False)
    monkeypatch.setattr(AX, "AXIsProcessTrustedWithOptions", lambda options: calls.append("accessibility"))
    monkeypatch.setattr(Q, "CGRequestListenEventAccess", lambda: calls.append("input_monitoring"))
    backend = MacBackend(lambda event: True)
    assert backend.permission_status() == {"accessibility": True, "input_monitoring": False}
    assert not backend.permissions() and calls == []
    backend.request_permission("input_monitoring")
    assert calls == ["input_monitoring"]
    backend.request_permission("accessibility")
    assert calls == ["input_monitoring", "accessibility"]
    with pytest.raises(ValueError):
        backend.request_permission("unknown")


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 ABI")
def test_win32_input_struct_layout_and_hook_thread():
    from mouseshare.input.windows import Input, RawInputHeader, RawMouse, RawMouseInput, WindowsBackend
    assert ctypes.sizeof(Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    assert ctypes.sizeof(RawInputHeader) == (24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)
    assert ctypes.sizeof(RawMouse) == 24 and RawMouse.lLastX.offset == 12
    assert RawMouseInput.mouse.offset == ctypes.sizeof(RawInputHeader)
    backend = WindowsBackend(lambda event: True)
    try:
        backend.start()
        assert backend.ready(), backend.error
        assert backend.raw_window
    finally:
        backend.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 raw mouse input")
def test_raw_motion_keeps_source_at_edge_and_suppresses_local_pointer(monkeypatch):
    from mouseshare.input.base import MARKER
    from mouseshare.input.windows import MouseHook, RawMouse, WindowsBackend

    events, warps = [], []
    backend = WindowsBackend(events.append)
    monkeypatch.setattr(backend, "bounds", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(backend, "move", lambda x, y: warps.append((x, y)))

    def motion(x, y):
        data = MouseHook()
        data.pt.x, data.pt.y = x, y
        return backend.mouse_proc(0, 0x0200, ctypes.addressof(data))

    backend.capture(True)
    assert warps == []
    assert motion(1919, 500) == 1
    assert events == []
    # Device zero is valid for precision touchpads. Motion remains relative
    # even with the physical cursor pinned at the edge by the hook.
    for dx, dy in [(12, 5), (8, -2), (-30, 0)]:
        backend.raw_motion(RawMouse(lLastX=dx, lLastY=dy), 0)
        assert (events[-1]["dx"], events[-1]["dy"]) == (dx, dy)
        assert motion(1919, 500) == 1
    count = len(events)
    backend.raw_motion(RawMouse(lLastX=500, ulExtraInformation=MARKER), 0)
    assert len(events) == count
    assert warps == []
    backend.capture(False)
    backend.raw_motion(RawMouse(lLastX=500), 0)
    assert len(events) == count
    motion(100, 100)
    assert events[-1]["dx"] == 0 and not backend.captured


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 absolute raw mouse input")
def test_absolute_raw_device_has_per_device_baseline_and_no_initial_jump(monkeypatch):
    from mouseshare.input.windows import RawMouse, WindowsBackend

    events = []
    backend = WindowsBackend(events.append)
    backend.capture(True)
    backend.raw_motion(RawMouse(usFlags=1, lLastX=60000, lLastY=30000), 1)
    backend.raw_motion(RawMouse(usFlags=1, lLastX=5000, lLastY=6000), 2)
    assert events == []
    backend.raw_motion(RawMouse(usFlags=1, lLastX=60100, lLastY=29900), 1)
    assert 0 < events[-1]["dx"] < 100 and -100 < events[-1]["dy"] < 0
    backend.capture(False)
    backend.capture(True)
    backend.raw_motion(RawMouse(usFlags=1, lLastX=1000, lLastY=1000), 1)
    assert len(events) == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz relative mouse input")
def test_mac_capture_forwards_delta_and_keeps_the_handoff_edge(monkeypatch):
    from types import SimpleNamespace

    from mouseshare.input.macos import Q, MacBackend

    events, warps, association = [], [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda enabled: association.append(enabled) or 0)
    backend = MacBackend(events.append)
    backend.capture(True)
    monkeypatch.setattr(backend, "move", lambda x, y: pytest.fail("Source must not be recentered"))
    monkeypatch.setattr(Q, "CGWarpMouseCursorPosition", lambda point: warps.append(point) or 0)
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: SimpleNamespace(x=0, y=500))
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda event, field: {
        Q.kCGMouseEventDeltaX: -17, Q.kCGMouseEventDeltaY: 6,
    }.get(field, 0))
    event = object()
    assert backend.callback(None, Q.kCGEventMouseMoved, event, None) is event
    assert (events[-1]["dx"], events[-1]["dy"]) == (-17, 6)
    assert warps == [(0, 500)]
    assert association == [False]
    backend.capture(False)
    assert association == [False, True]


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz cursor ownership")
@pytest.mark.parametrize("finish", ["return", "panic", "game", "pause", "disconnected", "timeout", "stop"])
def test_mac_cursor_association_restored_on_all_ownership_exits(tmp_path, monkeypatch, finish):
    from mouseshare.config import Settings
    from mouseshare.engine import Engine
    from mouseshare.input.macos import Q, MacBackend
    from types import SimpleNamespace

    association, moves = [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda enabled: association.append(enabled) or 0)
    now = [10.0]
    engine = Engine(Settings(tmp_path), clock=lambda: now[0])
    engine.backend = MacBackend(engine.enqueue)
    monkeypatch.setattr(engine.backend, "move", lambda x, y: moves.append((x, y)))
    monkeypatch.setattr(engine.backend, "bounds", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(engine.backend, "desktop_active", lambda: True)
    engine.session = SimpleNamespace(send=lambda message: True, peer_name="Other computer")
    engine.state = "pending" if finish == "timeout" else "sending"
    engine.pending_since = now[0]
    engine.backend.capture(True)
    engine.backend.capture(True)
    assert association == [False] and not moves
    if finish == "return":
        engine.receive({"type": "return", "position": .75})
    elif finish == "disconnected":
        engine.handle({"type": "disconnected", "session": engine.session})
    elif finish == "timeout":
        now[0] += 2
        engine.tick()
    else:
        engine.handle_command({"action": finish})
    engine.backend.stop()
    assert association == [False, True]
    assert not engine.backend.captured and not engine.backend._mouse_detached
    assert len(moves) == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz cursor recovery")
@pytest.mark.parametrize("failure", ["tap_timeout", "tap_disabled", "callback", "queue_full", "hotkey"])
def test_mac_native_failures_restore_local_cursor(monkeypatch, failure):
    from mouseshare.input.macos import Q, MacBackend

    association, events = [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda enabled: association.append(enabled) or 0)
    monkeypatch.setattr(Q, "CGEventTapEnable", lambda tap, enabled: None)
    backend = MacBackend(events.append)
    backend.capture(True)
    if failure in {"tap_timeout", "tap_disabled"}:
        kind = Q.kCGEventTapDisabledByTimeout if failure == "tap_timeout" else Q.kCGEventTapDisabledByUserInput
        backend.callback(None, kind, None, None)
        assert events[-1] == {"type": "command", "action": "panic"}
    elif failure == "callback":
        monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda event, field: 0)
        monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: (_ for _ in ()).throw(ValueError("test")))
        backend.callback(None, Q.kCGEventMouseMoved, object(), None)
        assert events[-1] == {"type": "command", "action": "panic"}
    elif failure == "queue_full":
        backend.emit = lambda event: False
        assert not backend.physical({"type": "move", "x": 0, "y": 500, "dx": 10, "dy": 1})
    else:
        for key in [224, 226, 41]:
            backend.physical({"type": "key", "key": key, "down": True})
        assert events[-1] == {"type": "command", "action": "panic"}
    assert association == [False, True] and not backend.captured


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz cursor API failure")
def test_mac_failed_cursor_detach_aborts_capture_and_restores(monkeypatch):
    from mouseshare.input.macos import Q, MacBackend

    association = []
    def associate(enabled):
        association.append(enabled)
        return 0 if enabled else 1000
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", associate)
    backend = MacBackend(lambda event: True)
    with pytest.raises(OSError):
        backend.capture(True)
    assert association == [False, True]
    assert not backend.captured and not backend._mouse_detached


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz cursor restore retry")
@pytest.mark.parametrize("raises", [False, True])
def test_mac_cursor_restore_failure_can_be_retried(monkeypatch, raises):
    from mouseshare.input.macos import Q, MacBackend

    calls = []
    def associate(enabled):
        calls.append(enabled)
        if len(calls) == 2:
            if raises:
                raise OSError("test")
            return 1000
        return 0
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", associate)
    backend = MacBackend(lambda event: True)
    backend.capture(True)
    backend.capture(False)
    assert not backend.captured and backend._mouse_detached and backend.error
    backend.stop()
    assert calls == [False, True, True] and not backend._mouse_detached


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz HID tap lifecycle")
def test_mac_tap_uses_hid_location_and_restores_capture_on_loop_failure(monkeypatch):
    from mouseshare.input.macos import Q, MacBackend
    import mouseshare.input.macos as native

    locations, association, enabled = [], [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda value: association.append(value) or 0)
    backend = MacBackend(lambda event: True)
    def create(location, *args):
        locations.append(location)
        return object()
    monkeypatch.setattr(Q, "CGEventTapCreate", create)
    monkeypatch.setattr(Q, "CGEventTapEnable", lambda tap, value: enabled.append(value))
    monkeypatch.setattr(native, "CFMachPortCreateRunLoopSource", lambda *args: object())
    monkeypatch.setattr(native, "CFRunLoopGetCurrent", lambda: object())
    monkeypatch.setattr(native, "CFRunLoopAddSource", lambda *args: None)
    def loop(*args):
        backend.capture(True)
        raise RuntimeError("test")
    monkeypatch.setattr(native, "CFRunLoopRunInMode", loop)
    with pytest.raises(RuntimeError):
        backend.run()
    assert locations == [Q.kCGHIDEventTap]
    assert association == [False, True] and enabled == [True, False]
    assert not backend.captured and not backend.running


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz stationary native movement")
@pytest.mark.parametrize("kind", ["move", "drag"])
def test_mac_returns_stationary_local_event_and_preserves_remote_delta(monkeypatch, kind):
    from types import SimpleNamespace
    from mouseshare.input.macos import Q, MacBackend

    live_event = object()
    live = SimpleNamespace(x=0, y=500)
    incoming = {"position": (700, 800), Q.kCGMouseEventDeltaX: -17, Q.kCGMouseEventDeltaY: 20}
    events, order = [], []
    monkeypatch.setattr(Q, "CGEventCreate", lambda source: live_event)
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: live if event is live_event else
                        SimpleNamespace(x=event["position"][0], y=event["position"][1]))
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda value: 0)
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda event, field: event.get(field, 0))
    def location(event, point):
        event["position"] = point
        order.append("stationary")
    monkeypatch.setattr(Q, "CGEventSetLocation", location)
    monkeypatch.setattr(Q, "CGEventSetIntegerValueField", lambda event, field, value: event.update({field: value}))
    def emit(event):
        assert incoming["position"] == (0, 500)
        assert incoming[Q.kCGMouseEventDeltaX] == incoming[Q.kCGMouseEventDeltaY] == 0
        order.append("forward")
        events.append(event)
        return True
    backend = MacBackend(emit)
    backend.capture(True)
    assert backend._cursor_shield.panels
    native_kind = Q.kCGEventMouseMoved if kind == "move" else Q.kCGEventLeftMouseDragged
    for _ in range(20):
        incoming.update({"position": (700, 800), Q.kCGMouseEventDeltaX: -17, Q.kCGMouseEventDeltaY: 20})
        returned = backend.callback(None, native_kind, incoming, None)
        # A NULL return would prevent WindowServer applying the fixed location.
        assert returned is incoming and returned["position"] == (0, 500)
        assert (events[-1]["dx"], events[-1]["dy"]) == (-17, 20)
    assert order == ["stationary", "forward"] * 20
    assert backend.captured_moves == 20
    backend.capture(False)
    assert not backend._cursor_shield.panels
    live.x, live.y = 50, 600
    backend.capture(True)
    assert backend._anchor == (50, 600)
    backend.capture(False)


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz stationary movement failure")
@pytest.mark.parametrize("failure", ["position", "delta", "shield", "warp"])
def test_mac_failed_stationary_movement_stops_forwarding(monkeypatch, failure):
    from mouseshare.input.macos import Q, MacBackend

    events, calls = [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda value: calls.append(value) or 0)
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda *args: 0)
    backend = MacBackend(events.append)
    def fail(*args):
        raise OSError("native failure")
    if failure == "shield":
        monkeypatch.setattr(backend._cursor_shield, "set_enabled", lambda value: fail() if value else None)
        with pytest.raises(OSError):
            backend.capture(True)
    else:
        backend.capture(True)
        api = {"position": "CGEventSetLocation", "delta": "CGEventSetIntegerValueField",
               "warp": "CGWarpMouseCursorPosition"}[failure]
        monkeypatch.setattr(Q, api, fail)
        event = object()
        assert backend.callback(None, Q.kCGEventMouseMoved, event, None) is event
        assert events == [{"type": "command", "action": "panic"}]
        assert backend.error
    assert not backend.captured and calls[-1] is True


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows keyboard hook')
def test_windows_builtin_keyboard_scan_and_missing_scan_fallback_preserve_repeats(monkeypatch):
    from mouseshare.input.windows import KeyHook, WindowsBackend, U
    events = []
    backend = WindowsBackend(events.append)
    monkeypatch.setattr(U, 'CallNextHookEx', lambda *args: 0)
    for scan in (0x1e, 0):
        data = KeyHook(vkCode=0x41, scanCode=scan, flags=0, dwExtraInfo=0)
        for message in (0x100, 0x100, 0x101):
            backend.key_proc(0, message, ctypes.addressof(data))
    assert events == [dict(type='key', key=4, down=down) for down in (True, True, False)*2]
    data = KeyHook(vkCode=0x41, scanCode=0x1e, flags=0x10, dwExtraInfo=0)
    backend.key_proc(0, 0x100, ctypes.addressof(data))
    assert len(events) == 6


@pytest.mark.skipif(sys.platform != 'darwin', reason='Quartz repeat metadata')
def test_mac_repeat_is_marked_and_released_without_posting_to_desktop(monkeypatch):
    from mouseshare.input.macos import MacBackend, Q
    backend = MacBackend(lambda e: True)
    flags, posts = [], []
    monkeypatch.setattr(Q, 'CGEventCreateKeyboardEvent', lambda *a: object())
    monkeypatch.setattr(Q, 'CGEventSetFlags', lambda *a: None)
    monkeypatch.setattr(Q, 'CGEventSetIntegerValueField', lambda e, field, value: flags.append((field, value)))
    monkeypatch.setattr(backend, 'post', posts.append)
    backend.key(4, True)
    backend.key(4, True)
    backend.key(4, False)
    assert [v for f, v in flags if f == Q.kCGKeyboardEventAutorepeat] == [0, 1, 0]
    assert len(posts) == 3 and not backend.injected_keys


@pytest.mark.skipif(sys.platform != 'darwin', reason='Quartz physical state reconciliation')
def test_mac_recovers_missed_releases_and_preserves_actual_held_input(monkeypatch):
    from mouseshare.input.macos import MacBackend, Q
    from mouseshare.input.keymap import HID_TO_MAC
    events = []
    backend = MacBackend(events.append)
    backend.keys.update({4, 225})
    backend.buttons.update({1, 2})
    backend.hotkey_keys.add(4)
    monkeypatch.setattr(Q, 'CGEventSourceKeyState', lambda state, key: key == HID_TO_MAC[225])
    monkeypatch.setattr(Q, 'CGEventSourceButtonState', lambda state, button: button == 1)
    backend.reconcile_physical()
    assert backend.keys == {225} and backend.buttons == {2}
    assert not backend.hotkey_keys and backend.recovered_releases == 2
    assert events == [dict(type='button', button=1, down=False)]
    backend.reconcile_physical()
    assert backend.keys == {225} and backend.buttons == {2} and backend.recovered_releases == 2


def test_windows_shield_reuses_hidden_surfaces_and_rebuilds_for_display_changes(monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    import mouseshare.input.windows_cursor as shield
    app = QApplication.instance() or QApplication([])
    screens = [QRect(0, 0, 1920, 1080)]
    created = []
    class Panel:
        def __init__(self, rect):
            self.visible = self.closed = self.deleted = False
            created.append(self)
        def show(self):
            self.visible = True
        def hide(self):
            self.visible = False
        def close(self):
            self.closed = True
        def deleteLater(self):
            self.deleted = True
    monkeypatch.setattr(shield, 'Surface', Panel)
    monkeypatch.setattr(shield.QApplication, 'screens', staticmethod(lambda: [
        SimpleNamespace(geometry=lambda r=r: r) for r in screens]))
    monkeypatch.setattr(shield.sys, 'platform', 'fixture')
    surface = shield.WindowsCursorShield()
    for _ in range(100):
        surface.set_enabled(True)
        assert surface.panels == created and all(p.visible for p in surface.panels)
        surface.set_enabled(False)
        assert not surface.panels and not surface.timer.isActive() and not created[0].visible
    assert len(created) == 1 and not created[0].closed
    screens.append(QRect(-1280, 0, 1280, 1024))
    surface.set_enabled(True)
    assert created[0].closed and created[0].deleted and len(surface.panels) == 2
    surface.set_enabled(False)
    assert not surface.panels and not surface.timer.isActive()
    app.processEvents()
