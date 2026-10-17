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
    from mouseshare.input.windows import Input, WindowsBackend
    assert ctypes.sizeof(Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    backend = WindowsBackend(lambda event: True)
    try:
        backend.start()
        assert backend.ready(), backend.error
    finally:
        backend.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 hook event ordering")
def test_capture_waits_for_tagged_recenter_before_calculating_delta(monkeypatch):
    from mouseshare.input.base import MARKER
    from mouseshare.input.windows import MouseHook, WindowsBackend

    events, warps = [], []
    backend = WindowsBackend(events.append)
    monkeypatch.setattr(backend, "bounds", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(backend, "move", lambda x, y: warps.append((x, y)))

    def motion(x, y, marker=0, flags=0):
        data = MouseHook()
        data.pt.x, data.pt.y = x, y
        data.dwExtraInfo, data.flags = marker, flags
        return backend.mouse_proc(0, 0x0200, ctypes.addressof(data))

    backend.capture(True)
    assert warps == [(960, 540)]
    # This physical event was already queued at the old screen edge when
    # capture began. Its position is not a delta from the new center yet.
    assert motion(1919, 500) == 1
    assert events == []
    motion(960, 540, MARKER, 1)
    assert motion(972, 545) == 1
    assert events[-1]["dx"] == 12 and events[-1]["dy"] == 5
    count = len(events)
    motion(990, 550)  # another move queued before the next warp is applied
    assert len(events) == count
    motion(960, 540, MARKER, 1)
    motion(968, 542)
    assert events[-1]["dx"] == 8 and events[-1]["dy"] == 2
    backend.capture(False)
    motion(100, 100)
    assert events[-1]["dx"] == 0 and not backend.captured

