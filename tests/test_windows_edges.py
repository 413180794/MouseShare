"""Exercise Win32 callback entry points without injecting desktop input."""
import ctypes
import sys
from types import SimpleNamespace

import pytest

from mouseshare.config import Settings
from mouseshare.engine import Engine
from mouseshare.input.base import MARKER

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Win32 mouse callbacks')


def source(tmp_path, monkeypatch, side='right', point=(1919, 500)):
    import mouseshare.input.windows as native

    class Shield:
        def set_enabled(self, enabled):
            pass

    monkeypatch.setattr(native, 'WindowsCursorShield', Shield)
    settings = Settings(tmp_path)
    settings.set(side=side)
    engine = Engine(settings)
    backend = engine.backend = native.WindowsBackend(engine.enqueue)
    backend.running = True
    monkeypatch.setattr(backend, 'bounds', lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(backend, 'monitors', lambda: [
        dict(id='test', x=0, y=0, w=1920, h=1080, primary=True)])
    messages = []
    engine.session = SimpleNamespace(peer_name='Test', peer_features=[],
                                     send=lambda message: messages.append(message) or True)
    engine.peer_available = True
    cursor = list(point)

    def position(pointer):
        p = ctypes.cast(pointer, ctypes.POINTER(native.W.POINT)).contents
        p.x, p.y = cursor
        return 1

    monkeypatch.setattr(native.U, 'GetCursorPos', position)

    def hook(x, y, marker=0):
        value = native.MouseHook(dwExtraInfo=marker)
        value.pt.x, value.pt.y = x, y
        return backend.mouse_proc(0, 0x0200, ctypes.addressof(value))

    def warp(x, y):
        cursor[:] = [round(x), round(y)]
        hook(*cursor, MARKER)

    monkeypatch.setattr(backend, 'move', warp)

    def raw(dx, dy):
        backend.raw_motion(native.RawMouse(lLastX=dx, lLastY=dy), 0)

    def drain():
        while engine.events:
            engine.handle(engine.events.popleft())

    return engine, backend, hook, raw, drain, cursor, messages


@pytest.mark.parametrize('side,point,delta', [
    ('right', (1919, 500), (12, 0)), ('left', (0, 500), (-12, 0)),
    ('top', (700, 0), (0, -12)), ('bottom', (700, 1079), (0, 12)),
])
def test_first_edge_sample_and_continued_pressure_enter_without_retreat(tmp_path, monkeypatch, side, point, delta):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch, side, point)
    backend.capture(False)  # Return/startup invalidates the hook coordinate baseline.
    hook(*point)
    drain()
    assert engine.state == 'local'
    raw(*delta)  # Same cursor pixel, with real outward device movement.
    hook(*point)  # A zero-displacement hook must not cancel the raw direction.
    drain()
    assert engine.state == 'pending' and backend.captured
    assert messages[-1]['type'] == 'enter'
    assert engine.handoff_attempts == 1


def test_peer_becomes_ready_while_cursor_stays_clamped(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    engine.peer_available = False
    for _ in range(3):
        hook(*cursor)
        raw(8, 0)
        drain()
    assert engine.state == 'local'
    engine.peer_available = True
    raw(8, 0)
    drain()
    assert engine.state == 'pending' and engine.handoff_attempts == 1


def test_own_return_warp_seeds_hook_baseline_without_physical_input(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    backend.capture(False)
    backend.move(1911, 500)
    assert not engine.events
    hook(1919, 500)  # First move after return, including absolute/touchpad devices.
    drain()
    assert engine.state == 'pending' and messages[-1]['type'] == 'enter'


def test_repeated_native_callbacks_return_and_reenter_without_retreat(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    for _ in range(25):
        cursor[:] = [1919, 500]
        hook(*cursor)
        raw(8, 0)
        drain()
        assert engine.state == 'pending'
        engine.receive(dict(type='entered'))
        raw(12, 0)
        drain()
        assert engine.state == 'sending' and messages[-1] == dict(type='move', dx=12, dy=0)
        engine.receive(dict(type='return', position=0.5))
        assert engine.state == 'local' and not backend.captured
    assert engine.handoff_attempts == 25


def test_local_raw_fallback_has_no_duplicate_center_motion_or_inward_bounce(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch, point=(900, 500))
    hook(880, 500)
    hook(900, 500)
    drain()
    raw(20, 0)
    assert not engine.events
    cursor[:] = [1919, 500]
    raw(-8, 0)
    raw(0, 8)
    raw(0, 0)
    assert not engine.events and engine.state == 'local'


def test_local_raw_fallback_preserves_held_input_and_game_protection(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    backend.buttons.add(1)
    raw(8, 0)
    drain()
    assert engine.state == 'local'
    backend.buttons.clear()
    engine.manual_game = True
    raw(8, 0)
    drain()
    assert engine.state == 'local'
    engine.manual_game = False
    raw(8, 0)
    drain()
    assert engine.state == 'pending'


def test_return_discards_old_raw_motion_and_inset_pressure_without_bouncing(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    hook(*cursor)
    raw(8, 0)
    drain()
    engine.receive(dict(type='entered'))
    raw(100, 0)  # Queued in the previous capture generation.
    engine.receive(dict(type='return', position=0.5))
    drain()
    raw(100, 0)  # The source cursor is still at the return inset, away from the edge.
    drain()
    assert engine.state == 'local' and engine.handoff_attempts == 1
    cursor[:] = [1919, 500]
    hook(*cursor)
    drain()
    assert engine.state == 'pending' and engine.handoff_attempts == 2


def test_raw_edge_pressure_uses_native_negative_monitor_coordinates(tmp_path, monkeypatch):
    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch, point=(-1, 500))
    monkeypatch.setattr(backend, 'bounds', lambda: (-1920, 0, 1920, 1080))
    monkeypatch.setattr(backend, 'monitors', lambda: [
        dict(id='negative', x=-1920, y=0, w=1920, h=1080, primary=True)])
    raw(8, 0)
    drain()
    assert engine.state == 'pending' and engine.health()['edge_pressure_moves'] == 1


def test_tagged_raw_and_own_warps_never_trigger_handoff(tmp_path, monkeypatch):
    from mouseshare.input.windows import RawMouse

    engine, backend, hook, raw, drain, cursor, messages = source(tmp_path, monkeypatch)
    hook(*cursor, MARKER)
    backend.raw_motion(RawMouse(lLastX=50, ulExtraInformation=MARKER), 0)
    drain()
    assert engine.state == 'local' and engine.handoff_attempts == 0
    assert engine.health()['edge_pressure_moves'] == 0
