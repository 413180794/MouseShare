"""Safe platform API checks; interactive input injection is covered by manual acceptance."""
import ctypes
import sys

import pytest

from mouseshare.input import create_backend
from mouseshare.input.keymap import HID_TO_MAC, HID_TO_WIN


@pytest.fixture(autouse=True)
def no_real_cursor_changes(monkeypatch):
    if sys.platform != "darwin":
        return
    from types import SimpleNamespace
    from mouseshare.input.macos import Q
    monkeypatch.setattr(Q, "CGEventCreate", lambda source: object())
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: SimpleNamespace(x=0, y=500))
    def unexpected_warp(point):
        pytest.fail("Native cursor warps must be mocked in tests")
    monkeypatch.setattr(Q, "CGWarpMouseCursorPosition", unexpected_warp)


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
def test_mac_capture_forwards_delta_without_warping_source(monkeypatch):
    from types import SimpleNamespace

    from mouseshare.input.macos import Q, MacBackend

    events, warps, association = [], [], []
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda enabled: association.append(enabled) or 0)
    backend = MacBackend(events.append)
    backend.capture(True)
    monkeypatch.setattr(backend, "move", lambda x, y: warps.append((x, y)))
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: SimpleNamespace(x=0, y=500))
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda event, field: {
        Q.kCGMouseEventDeltaX: -17, Q.kCGMouseEventDeltaY: 6,
    }.get(field, 0))
    assert backend.callback(None, Q.kCGEventMouseMoved, object(), None) is None
    assert (events[-1]["dx"], events[-1]["dy"]) == (-17, 6)
    assert warps == []
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


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz background cursor drift")
@pytest.mark.parametrize("warp_in_delta", [False, True])
def test_mac_background_recoupling_is_corrected_before_remote_motion(monkeypatch, warp_in_delta):
    from types import SimpleNamespace
    from mouseshare.input.macos import Q, MacBackend

    live = SimpleNamespace(x=0, y=500)
    live_event, incoming = object(), object()
    positions, events, order = [], [], []
    point = [SimpleNamespace(x=0, y=500)]
    delta = [-17, 20]
    monkeypatch.setattr(Q, "CGEventCreate", lambda source: live_event)
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: live if event is live_event else point[0])
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", lambda value: 0)
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda event, field: {
        Q.kCGMouseEventDeltaX: delta[0], Q.kCGMouseEventDeltaY: delta[1],
    }.get(field, 0))
    def warp(position):
        positions.append(position)
        live.x, live.y = position
        order.append("hold")
        return 0
    monkeypatch.setattr(Q, "CGWarpMouseCursorPosition", warp)
    def emit(event):
        assert (live.x, live.y) == (0, 500)
        order.append("forward")
        events.append(event)
        return True
    backend = MacBackend(emit)
    backend.capture(True)
    for index in range(20):
        # No sleep: high-rate movement must not bypass the hold operation.
        point[0] = SimpleNamespace(x=0, y=520)
        live.x, live.y = 0, 520
        delta[:] = [-17, 20 if index == 0 or not warp_in_delta else 0]
        assert backend.callback(None, Q.kCGEventMouseMoved, incoming, None) is None
        assert (events[-1]["dx"], events[-1]["dy"]) == (-17, 20)
    assert positions == [(0, 500)] * 20
    assert order == ["hold", "forward"] * 20
    assert backend.cursor_corrections == 20
    backend.capture(False)
    # Normal local motion has no correction; no stale warp carries into re-entry.
    live.x, live.y = 50, 600
    assert backend.hold_cursor(SimpleNamespace(x=50, y=600), 12, 4) == (12, 4)
    backend.capture(True)
    assert backend._anchor == (50, 600) and backend._warp_offset == (0, 0)
    backend.capture(False)


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz failed cursor hold")
@pytest.mark.parametrize("failure", ["warp", "ignored_warp", "detach"])
def test_mac_failed_cursor_hold_stops_forwarding(monkeypatch, failure):
    from types import SimpleNamespace
    from mouseshare.input.macos import Q, MacBackend

    live = SimpleNamespace(x=0, y=500)
    events, calls = [], []
    monkeypatch.setattr(Q, "CGEventGetLocation", lambda event: live)
    def associate(value):
        calls.append(value)
        return 1000 if failure == "detach" and len(calls) == 2 else 0
    monkeypatch.setattr(Q, "CGAssociateMouseAndMouseCursorPosition", associate)
    monkeypatch.setattr(Q, "CGEventGetIntegerValueField", lambda *args: 0)
    backend = MacBackend(events.append)
    backend.capture(True)
    live.y = 520
    def warp(point):
        if failure == "warp":
            return 1000
        if failure != "ignored_warp":
            live.x, live.y = point
        return 0
    monkeypatch.setattr(Q, "CGWarpMouseCursorPosition", warp)
    event = object()
    assert backend.callback(None, Q.kCGEventMouseMoved, event, None) is event
    assert events == [{"type": "command", "action": "panic"}]
    assert not backend.captured and backend.error and calls[-1] is True

