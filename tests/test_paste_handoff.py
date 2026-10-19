"""A verified receive callback must leave native X11 input able to cross again."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest


@pytest.mark.skipif(sys.platform != 'linux' or os.environ.get('MOUSESHARE_X11_TEST') != '1',
                    reason='Native input only on the isolated test X server')
@pytest.mark.parametrize('mode', ['local', 'receiving'])
def test_native_received_file_paste_then_return_and_handoff_again(tmp_path, mode):
    # Bound a regression deadlock to this child, including native connection cleanup.
    code = ('import sys; sys.path.insert(0, "tests"); '
            'from test_paste_handoff import native_scenario; native_scenario(sys.argv[1], sys.argv[2])')
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path), mode],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'xcb'},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'paste and subsequent handoff OK' in result.stdout


def native_scenario(directory, mode):
    from PySide6.QtWidgets import QApplication, QWidget
    from mouseshare.clipboard import ClipboardSync
    from mouseshare.config import Settings
    from mouseshare.engine import Engine
    from mouseshare.file_clipboard import FileClipboard
    from mouseshare.input.linux import Event, HID_TO_X11, LinuxBackend, X11

    app = QApplication([])
    now = [100.0]
    settings = Settings(Path(directory))
    settings.set(side='left')
    engine = Engine(settings, clock=lambda: now[0])
    backend = engine.backend = LinuxBackend(engine.enqueue)
    peer = SimpleNamespace(peer_id='a'*64, peer_name='Windows fixture', connected=True,
                           peer_features=['file-offer-v1'], messages=[])
    peer.send = lambda message: peer.messages.append(message) or True
    engine.session, engine.peer_available = peer, True
    engine.sessions, engine.availability = {peer.peer_id: peer}, {peer.peer_id: True}
    window = QWidget()  # Hidden controller; the paste target is a separate Xlib window.
    window.settings, window.engine, window.backend = settings, engine, backend
    window.network = SimpleNamespace(session=peer, sessions=engine.sessions,
                                      peer_session=engine.sessions.get)
    window.sharing = SimpleNamespace(network=window.network, enabled=lambda kind: True)
    sync = window.clipboard_sync = ClipboardSync(window.sharing, settings)
    control = FileClipboard(window)
    sync.timer.stop()
    control.timer.stop()
    api = X11()
    x, display = api.x, api.x.XOpenDisplay(None)
    U, D, Int = C.c_ulong, C.c_void_p, C.c_int
    x.XCreateSimpleWindow.restype = U
    x.XCreateSimpleWindow.argtypes = [D, U, Int, Int, C.c_uint, C.c_uint, C.c_uint, U, U]
    x.XSelectInput.argtypes = [D, U, C.c_long]
    x.XSetInputFocus.argtypes = [D, U, Int, U]
    target = x.XCreateSimpleWindow(display, x.XDefaultRootWindow(display), 20, 20, 100, 100, 0, 0, 0)
    try:
        x.XSelectInput(display, target, 3)
        x.XMapWindow(display, target)
        x.XSetInputFocus(display, target, 1, 0)
        x.XSync(display, False)
        backend.start()
        assert backend.ready(), backend.error
        assert backend.focus_token() == target and app.activeWindow() is None
        if mode == 'receiving':
            engine.receive(dict(type='enter', edge='right', position=.5))
            assert engine.state == 'receiving'
        backend.key(224, True)
        control.receive(peer, dict(type='file_offer', offer='b'*32, count=1, names=['from Windows.txt']))
        control.action('paste')
        request = next(m for m in peer.messages if m['type'] == 'file_request')
        assert control.claim(peer.peer_id, request['offer'], request['request'])
        received = Path(directory)/'from Windows.txt'
        received.write_text('verified received file', encoding='utf-8')
        rendezvous, pasted = threading.Barrier(2), threading.Event()
        failures = []
        original = backend.clipboard_shortcut

        def paste(action):
            rendezvous.wait(timeout=3)
            original(action)
            pasted.set()

        def remote_release():
            try:
                rendezvous.wait(timeout=3)
                for _ in range(50):
                    if mode == 'receiving':
                        engine.receive(dict(type='key', key=224, down=False))
                    else:
                        backend.key(224, False)
            except Exception as exc:
                failures.append(exc)

        backend.clipboard_shortcut = paste
        remote = threading.Thread(target=remote_release, daemon=True)
        remote.start()
        control.transfer(dict(direction='receive', status='complete', peer=peer.peer_id,
                              request=request['request'], offer=request['offer'], paths=[str(received)]))
        deadline = time.monotonic()+4
        while not pasted.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert pasted.is_set(), 'File completion never finished native paste'
        remote.join(3)
        assert not remote.is_alive() and not failures, failures
        assert not backend.keys and not backend.injected_keys and not backend.injected_buttons
        assert [Path(url.toLocalFile()) for url in app.clipboard().mimeData().urls()] == [received]
        x.XSync(display, False)
        pasted_v = False
        while x.XPending(display):
            event = Event()
            x.XNextEvent(display, C.byref(event))
            pasted_v |= event.key.type == 2 and event.key.keycode == HID_TO_X11[25] and bool(event.key.state & 4)
        assert pasted_v, 'Focused target did not receive Ctrl+V'
        if mode == 'receiving':
            engine.remote_position = (0, 500)
            now[0] += 1
            engine.remote_move(-10, 0)
            now[0] += .1
            engine.remote_move(-10, 0)
            assert peer.messages[-1]['type'] == 'return' and engine.state == 'local'
        now[0] += 1
        engine.physical(dict(type='move', x=500, y=500, dx=10, dy=0))
        engine.physical(dict(type='move', x=0, y=500, dx=-10, dy=0))
        now[0] += .2
        engine.tick()
        assert engine.state == 'pending' and backend.captured
        engine.receive(dict(type='entered'))
        assert engine.state == 'sending'
        engine.release(False)
        print('paste and subsequent handoff OK')
    finally:
        control.stop()
        sync.stop()
        backend.stop()
        x.XDestroyWindow(display, target)
        x.XCloseDisplay(display)
        window.close()
