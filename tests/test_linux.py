"""Platform-independent guards plus native checks only on an isolated CI X server."""
import ctypes as C
import json
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from mouseshare.input.linux import (Cookie, DeviceInfo, Event, HID_TO_X11, LinuxBackend, Monitor,
                                    KeyEvent, RawEvent, SaverInfo, Valuators, X11, raw_axes, session_problem)
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


@pytest.mark.parametrize('action', ['copy', 'paste'])
def test_clipboard_shortcut_and_remote_key_release_make_progress(action):
    """Force the GUI shortcut to overlap input-owner modifier release."""
    backend = LinuxBackend(lambda event: True)
    remote_ready, clipboard_started = threading.Event(), threading.Event()
    failures = []

    class ObservedLock:
        def __init__(self, x11=False):
            self.inner, self.x11 = threading.RLock(), x11

        def __enter__(self):
            clipboard = threading.current_thread().name == 'clipboard-completion'
            if clipboard and not self.x11:
                clipboard_started.set()
            if not self.inner.acquire(timeout=2):
                raise TimeoutError('Clipboard and input owner are waiting on opposite locks')
            if clipboard and self.x11:
                clipboard_started.set()
            return self

        def __exit__(self, *args):
            self.inner.release()

    backend.inject_lock, backend.lock = ObservedLock(), ObservedLock(x11=True)
    backend.open = lambda: None
    backend.refresh_shortcut_grabs = lambda **kwargs: None
    backend.api = SimpleNamespace(x=SimpleNamespace(XUngrabKeyboard=lambda *a: None,
        XSync=lambda *a: None, XFlush=lambda *a: None),
        xt=SimpleNamespace(XTestFakeKeyEvent=lambda *a: None))
    backend.injected_keys.add(224)

    def guarded(operation):
        try:
            operation()
        except Exception as exc:
            failures.append(exc)

    def remote_release():
        with backend.inject_lock:
            remote_ready.set()
            assert clipboard_started.wait(2)
            backend.key(224, False)

    remote = threading.Thread(target=lambda: guarded(remote_release), name='input-owner', daemon=True)
    clipboard = threading.Thread(target=lambda: guarded(lambda: backend.clipboard_shortcut(action)),
                                 name='clipboard-completion', daemon=True)
    remote.start()
    assert remote_ready.wait(2)
    clipboard.start()
    remote.join(4)
    clipboard.join(4)
    assert not remote.is_alive() and not clipboard.is_alive()
    assert not failures, repr(failures)
    assert not backend.injected_keys and not backend.injected_buttons


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
int main(void) {printf("[%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu]", sizeof(XEvent), sizeof(XGenericEventCookie), sizeof(XIRawEvent), sizeof(XIDeviceInfo), sizeof(XRRMonitorInfo), sizeof(XScreenSaverInfo), sizeof(XKeyEvent), offsetof(XIRawEvent, valuators));}''')
    subprocess.run(['cc', str(source), '-o', str(tmp_path / 'abi')], check=True)
    sizes = json.loads(subprocess.check_output([str(tmp_path / 'abi')]))
    assert sizes == [C.sizeof(t) for t in [Event, Cookie, RawEvent, DeviceInfo, Monitor, SaverInfo, KeyEvent]] + [RawEvent.valuators.offset]


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
        def next_key_type():
            wait_for(lambda: x.XPending(display) > 0, diagnostic)
            event = Event()
            x.XNextEvent(display, C.byref(event))
            return event.cookie.type
        backend.key(4, True)
        # XPending doesn't read the socket while its local queue is nonempty.
        # Consume down before waiting for up; waiting for a count of 2 can stall.
        # https://www.x.org/releases/X11R7.6/doc/libX11/specs/libX11/libX11.html#Event_Queue_Management
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        assert next_key_type() == 2
        backend.key(4, False)
        with backend.lock:
            backend.api.x.XSync(backend.display, False)
        assert next_key_type() == 3
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
        backend.switch_shortcut_enabled = True
        wait_for(lambda: all((HID_TO_X11[key], mask) in backend.shortcut_grabs
                             for key, mask in [(25, 4), (25, 4 | 8), (25, 4 | 8 | 1), (44, 4 | 8)]))
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


def test_grabbed_core_repeat_deduplicates_raw_and_never_repeats_released_or_injected_keys():
    events = []
    backend = LinuxBackend(events.append)
    backend.captured = True
    backend.test_sources = {99}
    backend.raw_input(13, 100, HID_TO_X11[4], {}, 10)
    backend.core_key_press(HID_TO_X11[4], 10)
    backend.core_key_press(HID_TO_X11[4], 20)
    backend.raw_input(13, 100, HID_TO_X11[4], {}, 20)
    assert len(events) == 2 and all(e['down'] for e in events)
    backend.raw_input(14, 100, HID_TO_X11[4], {}, 30)
    backend.core_key_press(HID_TO_X11[4], 40)
    backend.raw_input(13, 99, HID_TO_X11[5], {}, 50)
    backend.core_key_press(HID_TO_X11[5], 60)
    assert len(events) == 3 and not events[-1]['down']


@native
def test_native_xrandr_enumerates_two_monitors_instead_of_only_primary():
    backend = LinuxBackend(lambda e: True)
    backend.open()  # Keep an X client connected so Xvfb does not reset RandR.
    try:
        subprocess.run(['xrandr', '--setmonitor', 'MouseShareLeft', '960/254x1080/286+0+0', 'none'], check=True)
        subprocess.run(['xrandr', '--setmonitor', 'MouseShareRight', '960/254x1080/286+960+0', 'screen'], check=True)
        monitors = backend.monitors()
        assert len(monitors) == 2
        assert {(m['x'], m['y'], m['w'], m['h']) for m in monitors} == {(0, 0, 960, 1080), (960, 0, 960, 1080)}
        assert backend.bounds() == (0, 0, 1920, 1080)
    finally:
        for name in ('MouseShareLeft', 'MouseShareRight'):
            subprocess.run(['xrandr', '--delmonitor', name], check=True)
        backend.stop()


@native
@pytest.mark.parametrize('hid', [4, 42, 79])
def test_native_captured_hold_forwards_repeats_and_stops_on_release(hid):
    events = []
    backend = LinuxBackend(events.append)
    backend.start()
    api = X11()
    display = api.x.XOpenDisplay(None)
    try:
        assert backend.ready(), backend.error
        # Only this isolated test treats another XTEST client as physical input.
        # Production always excludes every discovered XTEST source.
        backend.test_sources.clear()
        backend.capture(True)
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[hid], True, 0)
        api.x.XSync(display, False)
        wait_for(lambda: sum(e.get('key') == hid and e.get('down', False) for e in events) >= 3)
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[hid], False, 0)
        api.x.XSync(display, False)
        wait_for(lambda: any(e.get('key') == hid and not e.get('down', True) for e in events))
        count = len(events)
        time.sleep(.15)
        assert len(events) == count and not backend.keys
    finally:
        api.xt.XTestFakeKeyEvent(display, HID_TO_X11[hid], False, 0)
        api.x.XSync(display, False)
        backend.stop()
        api.x.XCloseDisplay(display)


@native
def test_native_receiver_repeated_network_down_does_not_restart_xorg_repeat():
    backend = LinuxBackend(lambda e: True)
    api = X11()
    x, display = api.x, api.x.XOpenDisplay(None)
    U, D, Int = C.c_ulong, C.c_void_p, C.c_int
    x.XCreateSimpleWindow.restype = U
    x.XCreateSimpleWindow.argtypes = [D, U, Int, Int, C.c_uint, C.c_uint, C.c_uint, U, U]
    x.XSelectInput.argtypes = [D, U, C.c_long]
    x.XSetInputFocus.argtypes = [D, U, Int, U]
    window = x.XCreateSimpleWindow(display, x.XDefaultRootWindow(display), 10, 10, 100, 100, 0, 0, 0)
    try:
        x.XSelectInput(display, window, 3)
        x.XMapWindow(display, window)
        x.XSetInputFocus(display, window, 1, 0)
        x.XSync(display, False)
        def drain():
            result = []
            while x.XPending(display):
                event = Event()
                x.XNextEvent(display, C.byref(event))
                result.append(event.key.type)
            return result
        types = []
        for _ in range(35):
            backend.key(4, True)
            time.sleep(.04)
            types.extend(drain())
        backend.key(4, False)
        time.sleep(.05)
        types.extend(drain())
        assert types.count(2) >= 4, types
        time.sleep(.15)
        assert not drain() and not backend.injected_keys
    finally:
        backend.stop()
        x.XDestroyWindow(display, window)
        x.XCloseDisplay(display)
