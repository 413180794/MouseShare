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

