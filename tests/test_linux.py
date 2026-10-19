"""Platform-independent guards plus native checks only on an isolated CI X server."""
import ctypes as C
import json
import os
import subprocess
import sys
import time

import pytest

from mouseshare.input.linux import (Cookie, DeviceInfo, Event, HID_TO_X11, LinuxBackend, Monitor,
                                    RawEvent, SaverInfo, Valuators, X11, raw_axes, session_problem)
from mouseshare.startup import desktop_entry


def wait_for(predicate, diagnostic=lambda: ''):
    until = time.monotonic() + 4
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('X11 event timeout '+diagnostic())


def test_session_guard_rejects_xwayland_and_missing_display():
    assert not session_problem({'DISPLAY': ':0', 'XDG_SESSION_TYPE': 'x11'})
    assert 'Wayland' in session_problem({'DISPLAY': ':0', 'XDG_SESSION_TYPE': 'wayland'})
    assert 'Wayland' in session_problem({'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'})
    assert '图形桌面' in session_problem({})


def test_hid_positions_and_linux_shortcuts_avoid_virtual_terminal_keys():
    assert all(key in HID_TO_X11 for key in [*range(4, 30), 40, 41, 44, *range(58, 70),
                                            *range(79, 83), *range(224, 232)])
    events = []
    backend = LinuxBackend(events.append)
    for key in [224, 226, 69]:
        backend.physical(dict(type='key', key=key, down=True))
    assert not any(e.get('type') == 'command' for e in events)
    backend.physical(dict(type='key', key=225, down=True))
    backend.physical(dict(type='key', key=10, down=True))
    assert events[-1] == {'type': 'command', 'action': 'game'}
    backend.physical(dict(type='key', key=41, down=True))
    assert events[-1] == {'type': 'command', 'action': 'panic'}


def test_raw_valuators_sparse_axes_and_injection_filter():
    mask = (C.c_ubyte * 1)(0b101)
    values = (C.c_double * 2)(5.5, -2)
    event = RawEvent(valuators=Valuators(1, mask, values), raw_values=values)
    assert raw_axes(event) == {0: 5.5, 2: -2}
    events = []
    backend = LinuxBackend(events.append)
    backend.position = lambda: (123, 456)
    backend.test_sources = {99}
    backend.raw_input(17, 99, 0, {0: 20, 1: 30})
    assert not events
    backend.raw_input(17, 100, 0, {0: 20, 1: 30})
    assert events[-1] == dict(type='move', x=123, y=456, dx=20, dy=30)
    backend.raw_input(15, 100, 3, {})
    assert events[-1] == dict(type='button', button=2, down=True)
    backend.raw_input(15, 100, 4, {})
    assert events[-1] == dict(type='scroll', dx=0, dy=1)


def test_desktop_exec_quotes_paths_without_shell_interpretation():
    result = desktop_entry(['/path with space/$folder/MouseShare', '--minimized', '100%'])
    assert '"/path with space/\\$folder/MouseShare"' in result and '"100%%"' in result
    with pytest.raises(OSError):
        desktop_entry(['/path\nExec=evil'])


native = pytest.mark.skipif(sys.platform != 'linux' or os.environ.get('MOUSESHARE_X11_TEST') != '1',
                            reason='Requires isolated Xvfb; never inject into a user desktop')


@native
def test_native_struct_abi_matches_system_headers(tmp_path):
    source = tmp_path / 'abi.c'
    source.write_text('''#include <stdio.h>
#include <stddef.h>
#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>
#include <X11/extensions/Xrandr.h>
#include <X11/extensions/scrnsaver.h>
int main(void) {printf("[%zu,%zu,%zu,%zu,%zu,%zu,%zu]", sizeof(XEvent), sizeof(XGenericEventCookie), sizeof(XIRawEvent), sizeof(XIDeviceInfo), sizeof(XRRMonitorInfo), sizeof(XScreenSaverInfo), offsetof(XIRawEvent, valuators));}''')
    subprocess.run(['cc', str(source), '-o', str(tmp_path / 'abi')], check=True)
    sizes = json.loads(subprocess.check_output([str(tmp_path / 'abi')]))
    assert sizes == [C.sizeof(t) for t in [Event, Cookie, RawEvent, DeviceInfo, Monitor, SaverInfo]] + [RawEvent.valuators.offset]


@native
def test_native_source_anchor_raw_motion_and_local_recovery():
    events = []
    backend = LinuxBackend(events.append)
    backend.start()
    try:
        assert backend.ready(), backend.error
        assert backend.test_sources
        assert backend.bounds()[2:] == (1920, 1080)
        backend.move(1918, 500)
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        assert backend.position() == (1918, 500)
        backend.capture(True)
        with backend.lock:
            backend.api.xt.XTestFakeRelativeMotionEvent(backend.display, 120, -200, 0)
            backend.api.x.XSync(backend.display, False)
        assert backend.position() == (1918, 500)
        backend.raw_input(17, -1, 0, {0: 120, 1: -200})
        assert events[-1]['dx'] == 120 and events[-1]['dy'] == -200
        backend.capture(False)
        assert not backend.window and not backend.captured
        backend.move(1911, 500)
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        assert backend.position() == (1911, 500)
        backend.key(225, True)
        backend.button(1, True)
        backend.release_all()
        assert not backend.injected_keys and not backend.injected_buttons
    finally:
        backend.stop()
    assert not backend.display and not backend.running


@native
def test_native_keyboard_grab_suppresses_focus_and_injection_has_no_echo():
    events = []
    backend = LinuxBackend(events.append)
    backend.start()
    api = X11()
    x = api.x
    display = x.XOpenDisplay(None)
    U, D, Int = C.c_ulong, C.c_void_p, C.c_int
    x.XCreateSimpleWindow.restype = U
    x.XCreateSimpleWindow.argtypes = [D, U, Int, Int, C.c_uint, C.c_uint, C.c_uint, U, U]
    x.XSelectInput.argtypes = [D, U, C.c_long]
    x.XSetInputFocus.argtypes = [D, U, Int, U]
    window = x.XCreateSimpleWindow(display, x.XDefaultRootWindow(display), 10, 10, 100, 100, 0, 0, 0)
    try:
        assert backend.ready(), backend.error
        x.XSelectInput(display, window, 3)
        x.XMapWindow(display, window)
        x.XSetInputFocus(display, window, 1, 0)
        x.XSync(display, False)
        def diagnostic():
            return repr(dict(expected_focus=window, actual_focus=backend.focus_token(),
                             pending=x.XPending(display), ready=backend.ready(), error=backend.error))
        wait_for(lambda: backend.focus_token() == window, diagnostic)
        backend.key(4, True)
        # Observe down before releasing: XTEST input is queued separately from
        # Xlib requests, so XFlush alone is not an input-delivery barrier.
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        wait_for(lambda: x.XPending(display) >= 1, diagnostic)
        backend.key(4, False)
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        wait_for(lambda: x.XPending(display) >= 2, diagnostic)
        types = []
        while x.XPending(display):
            event = Event()
            x.XNextEvent(display, C.byref(event))
            types.append(event.cookie.type)
        assert 2 in types and 3 in types
        backend.capture(True)
        backend.key(5, True)
        backend.key(5, False)
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        x.XSync(display, False)
        assert not x.XPending(display)
        assert not events
        backend.capture(False)
    finally:
        backend.stop()
        x.XDestroyWindow(display, window)
        x.XCloseDisplay(display)


@native
def test_native_linux_window_and_session_monitor_startup(tmp_path):
    from PySide6.QtWidgets import QApplication
    from mouseshare.app import MainWindow
    from mouseshare.config import Settings
    from mouseshare.security import Identity
    app = QApplication.instance() or QApplication([])
    settings = Settings(tmp_path)
    window = MainWindow(settings, Identity(tmp_path))
    try:
        app.processEvents()
        assert window.backend.ready(), window.backend.error
        assert window.linux_session.timer.isActive()
        assert 'Linux' == window.screen_map.local_os
    finally:
        window.shutdown()
        window.close()
    assert not window.linux_session.timer.isActive()


def test_linux_startup_is_user_scoped_and_removable(monkeypatch, tmp_path):
    import mouseshare.startup as startup
    monkeypatch.setattr(startup.sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    startup.set_enabled(True)
    path = tmp_path / 'autostart/mouseshare.desktop'
    assert path.exists() and '--minimized' in path.read_text()
    startup.set_enabled(False)
    assert not path.exists()


@native
def test_native_x11_clipboard_between_processes(tmp_path):
    producer = r'''
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData, QTimer, QUrl
from PySide6.QtGui import QImage
app = QApplication([])
mime = QMimeData()
mime.setText('MouseShare 中文 clipboard')
mime.setHtml('<b>MouseShare 中文 clipboard</b>')
image = QImage(8, 8, QImage.Format.Format_ARGB32)
image.fill(0xff123456)
mime.setImageData(image)
mime.setUrls([QUrl.fromLocalFile('/tmp/中文 file.txt')])
mime.setData('x-special/gnome-copied-files', b'copy\nfile:///tmp/example.txt')
app.clipboard().setMimeData(mime)
print('ready', flush=True)
QTimer.singleShot(10000, app.quit)
app.exec()
'''
    consumer = r'''
import json
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([])
def read():
    mime = app.clipboard().mimeData()
    image = mime.imageData()
    print(json.dumps(dict(text=mime.text(), html=mime.html(), pixel=image.pixel(0, 0),
                          paths=[u.toLocalFile() for u in mime.urls()],
                          gnome=bytes(mime.data('x-special/gnome-copied-files')).decode())), flush=True)
    app.quit()
QTimer.singleShot(0, read)
app.exec()
'''
    env = {**os.environ, 'QT_QPA_PLATFORM': 'xcb'}
    owner = subprocess.Popen([sys.executable, '-c', producer], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == 'ready'
        result = subprocess.run([sys.executable, '-c', consumer], env=env, capture_output=True, text=True,
                                timeout=8, check=True)
        value = json.loads(result.stdout)
        assert value['text'] == 'MouseShare 中文 clipboard'
        assert value['html'] == '<b>MouseShare 中文 clipboard</b>'
        assert value['pixel'] == 0xff123456 and value['paths'] == ['/tmp/中文 file.txt']
        assert value['gnome'] == 'copy\nfile:///tmp/example.txt'
    finally:
        owner.terminate()
        owner.communicate(timeout=3)


@native
def test_native_file_paste_grab_suppresses_original_and_injected_paste_reaches_focus():
    api = X11()
    x = api.x
    x.XCreateSimpleWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint,
                                      C.c_uint, C.c_ulong, C.c_ulong]
    x.XCreateSimpleWindow.restype = C.c_ulong
    x.XSelectInput.argtypes = [C.c_void_p, C.c_ulong, C.c_long]
    x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
    display = x.XOpenDisplay(None)
    root = x.XDefaultRootWindow(display)
    window = x.XCreateSimpleWindow(display, root, 20, 20, 100, 100, 0, 0, 0)
    x.XSelectInput(display, window, 1 | 2)
    x.XMapWindow(display, window)
    x.XSetInputFocus(display, window, 1, 0)
    x.XSync(display, False)
    backend = LinuxBackend(lambda event: True)
    backend.start()
    try:
        backend.sharing_shortcuts_enabled = backend.native_file_paste_ready = True
        wait_for(lambda: len(backend.shortcut_grabs) == 12)
        assert not backend.shortcut_grab_error
        # XTEST on a different connection stands in for an actual keyboard.
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[224], True, 0)
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[25], True, 0)
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[25], False, 0)
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[224], False, 0)
        x.XSync(display, False)
        codes = []
        while x.XPending(display):
            event = Event()
            x.XNextEvent(display, C.byref(event))
            codes.append(event.cookie.type)
        assert codes.count(2) == 1  # Only Ctrl-down reached the original app.
        backend.clipboard_shortcut('paste')
        x.XSync(display, False)
        codes = []
        while x.XPending(display):
            event = Event()
            x.XNextEvent(display, C.byref(event))
            codes.append(event.cookie.type)
        assert codes.count(2) == 2  # Injected Ctrl and V reach the focused app.
        backend.cursor_hidden(True)
        backend.cursor_hidden(True)
        backend.cursor_hidden(False)
        assert not backend.cursor_is_hidden
    finally:
        backend.stop()
        x.XDestroyWindow(display, window)
        x.XCloseDisplay(display)
