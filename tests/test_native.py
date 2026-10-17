"""Safe platform API checks; interactive input injection is covered by manual acceptance."""
import ctypes
import sys

import pytest

from mouseshare.input import create_backend
from mouseshare.input.keymap import HID_TO_MAC, HID_TO_WIN


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

    events, warps = [], []
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

