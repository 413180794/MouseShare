import pytest

from mouseshare.config import Settings
from mouseshare.engine import Engine, entry_point
from mouseshare.input.base import NullBackend


class FakeBackend(NullBackend):
    def __init__(self):
        super().__init__(lambda event: True)
        self.running = True
        self.moves = []
        self.process = ""
        self.fullscreen = False

    def move(self, x, y):
        self.moves.append((x, y))

    def foreground(self):
        return self.process, self.fullscreen


class FakeSession:
    peer_name = "Peer"

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


def setup(tmp_path):
    settings = Settings(tmp_path)
    now = [100.0]
    engine = Engine(settings, clock=lambda: now[0])
    engine.backend = FakeBackend()
    engine.session = FakeSession()
    engine.peer_available = True
    return engine, now


def hit_edge(engine, now):
    engine.physical({"type": "move", "x": 1919, "y": 500, "dx": 10, "dy": 0})
    now[0] += 0.2
    engine.tick()


def test_handoff_waits_for_ack_then_routes_and_returns(tmp_path):
    engine, now = setup(tmp_path)
    hit_edge(engine, now)
    assert engine.state == "pending" and engine.backend.captured
    engine.physical({"type": "key", "key": 4, "down": True})
    assert engine.session.messages[-1]["type"] == "enter"
    engine.receive({"type": "entered"})
    assert engine.state == "sending"
    assert engine.session.messages[-1] == {"type": "key", "key": 4, "down": True}
    engine.receive({"type": "return"})
    assert engine.state == "local" and not engine.backend.captured
    assert not engine.armed


def test_keyboard_only_switch_establishes_ownership_and_reclaims_safely(tmp_path):
    engine, now = setup(tmp_path)
    engine.backend.keys = {224, 226, 44}
    engine.handle_command(dict(action='switch_peer'))
    assert engine.state == 'pending' and engine.backend.captured
    engine.receive(dict(type='entered'))
    engine.physical(dict(type='key', key=4, down=True))
    engine.physical(dict(type='key', key=4, down=False))
    assert engine.session.messages[-2:] == [dict(type='key', key=4, down=True), dict(type='key', key=4, down=False)]
    engine.handle_command(dict(action='switch_peer'))
    assert engine.state == 'local' and not engine.backend.captured
    engine.manual_game = True
    engine.handle_command(dict(action='switch_peer'))
    assert engine.state == 'local'


@pytest.mark.parametrize("side,position", [
    ("right", (1919, 300)), ("left", (0, 300)),
    ("bottom", (700, 1079)), ("top", (700, 0)),
])
def test_fast_pending_motion_does_not_skip_target_entry_edge(tmp_path, side, position):
    source, now = setup(tmp_path / "source")
    target, _ = setup(tmp_path / "target")
    source.settings.set(side=side)
    target.backend.bounds = lambda: (100, 50, 2560, 1440)
    source.physical({"type": "move", "x": position[0], "y": position[1], "dx": 800, "dy": 600})
    now[0] += 0.2
    source.tick()
    target.receive(source.session.messages[-1])
    entry = target.remote_position
    # High polling rates and a delayed ownership ACK must not replay a burst
    # that transports the target cursor halfway across its screen on entry.
    for _ in range(30):
        source.physical({"type": "move", "x": position[0], "y": position[1], "dx": 900, "dy": 700})
    source.physical({"type": "key", "key": 4, "down": True})
    source.physical({"type": "key", "key": 4, "down": False})
    before = len(source.session.messages)
    source.receive({"type": "entered"})
    for message in source.session.messages[before:]:
        target.receive(message)
    assert target.backend.moves == [entry]
    assert not target.backend.injected_keys
    assert [m["down"] for m in source.session.messages[before:]] == [True, False]
    # Fresh movement after the ACK still follows the user's chosen sensitivity.
    target.settings.set(sensitivity=1.5)
    dx, dy = (-6 if side == "left" else 6), (-4 if side == "top" else 4)
    source.physical({"type": "move", "x": 960, "y": 540, "dx": dx, "dy": dy})
    target.receive(source.session.messages[-1])
    assert target.remote_position == (entry[0] + dx * 1.5, entry[1] + dy * 1.5)


def test_game_mode_blocks_both_directions_and_releases_modifiers(tmp_path):
    engine, now = setup(tmp_path)
    engine.receive({"type": "enter", "edge": "left", "position": 0.5})
    engine.receive({"type": "key", "key": 225, "down": True})
    engine.receive({"type": "button", "button": 1, "down": True})
    assert engine.backend.injected_keys == {225}
    engine.handle_command({"action": "game"})
    assert engine.state == "local" and engine.game
    assert not engine.backend.injected_keys and not engine.backend.injected_buttons
    hit_edge(engine, now)
    assert engine.state == "local"
    engine.receive({"type": "enter", "edge": "left", "position": 0.5})
    assert engine.state == "local"


def test_auto_fullscreen_and_game_process(tmp_path):
    engine, now = setup(tmp_path)
    engine.backend.fullscreen = True
    engine.tick()
    assert engine.game
    engine.backend.fullscreen = False
    now[0] += 1
    engine.tick()
    assert not engine.game
    engine.backend.process = "LEAGUE OF LEGENDS.EXE"
    now[0] += 1
    engine.tick()
    assert engine.game


def test_no_switch_with_held_input_or_during_cooldown(tmp_path):
    engine, now = setup(tmp_path)
    engine.backend.keys.add(225)
    hit_edge(engine, now)
    assert engine.state == "local"
    engine.backend.keys.clear()
    engine.backend.buttons.add(1)
    engine.tick()
    assert engine.state == "local"
    engine.backend.buttons.clear()
    engine.release()
    hit_edge(engine, now)
    assert engine.state == "local"


def test_disconnect_cleans_up_receiving_and_pending_timeout(tmp_path):
    engine, now = setup(tmp_path)
    engine.receive({"type": "enter", "edge": "right", "position": 0.5})
    engine.receive({"type": "key", "key": 224, "down": True})
    engine.handle({"type": "disconnected", "session": engine.session})
    assert engine.session is None and not engine.backend.injected_keys
    engine.session = FakeSession()
    engine.peer_available = engine.armed = True
    now[0] += 2
    hit_edge(engine, now)
    assert engine.state == "pending"
    now[0] += 2
    engine.tick()
    assert engine.state == "local" and not engine.backend.captured


def test_receiver_return_edge_and_local_takeover(tmp_path):
    engine, now = setup(tmp_path)
    engine.receive({"type": "enter", "edge": "right", "position": 0.5})
    assert engine.state == "receiving"
    now[0] += 1
    engine.remote_move(-100, 0)
    now[0] += 0.1
    engine.remote_move(-10, 0)
    assert engine.state == "local"
    assert {"type": "return", "position": 0.5} in engine.session.messages
    engine.receive({"type": "enter", "edge": "right", "position": 0.5})
    engine.physical({"type": "key", "key": 4, "down": True})
    assert engine.state == "local"


def test_simultaneous_enter_returns_to_local(tmp_path):
    engine, now = setup(tmp_path)
    hit_edge(engine, now)
    engine.receive({"type": "enter", "edge": "left", "position": 0.5})
    assert engine.state == "local" and not engine.backend.captured


def test_modifier_swap_and_release(tmp_path):
    engine, now = setup(tmp_path)
    engine.settings.set(swap_ctrl_meta=True)
    engine.receive({"type": "enter", "edge": "right", "position": 0.5})
    engine.receive({"type": "key", "key": 224, "down": True})
    assert engine.backend.injected_keys == {227}
    engine.release()
    assert not engine.backend.injected_keys


def test_hotkeys_are_local_and_not_forwarded():
    events = []
    backend = NullBackend(events.append)
    backend.captured = True
    for key in [224, 226, 41]:
        backend.physical({"type": "key", "key": key, "down": True})
    assert not backend.captured
    assert events[-1] == {"type": "command", "action": "panic"}


def test_locked_desktop_revokes_input_and_blocks_handoff(tmp_path):
    engine, now = setup(tmp_path)
    engine.receive({"type": "enter", "edge": "right", "position": 0.5})
    engine.receive({"type": "key", "key": 225, "down": True})
    engine.backend.desktop_active = lambda: False
    engine.tick()
    assert engine.system_blocked and engine.state == "local"
    assert not engine.backend.injected_keys and not engine.available
    hit_edge(engine, now)
    assert engine.state == "local"
    engine.backend.desktop_active = lambda: True
    now[0] += 1
    engine.tick()
    assert not engine.system_blocked and engine.available


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
@pytest.mark.parametrize("finish", ["return", "panic", "disconnected", "timeout"])
def test_source_returns_to_edge_with_mapped_position(tmp_path, side, finish):
    source, now = setup(tmp_path / "source")
    target, target_now = setup(tmp_path / "target")
    bounds = (100, 50, 2560, 1440)
    source.backend.bounds = lambda: bounds
    source.settings.set(side=side)
    target.backend.bounds = lambda: (-200, 70, 1920, 1080)
    position = entry_point(side, 0.25, bounds, inset=0)
    source.physical({"type": "move", "x": position[0], "y": position[1], "dx": 10, "dy": 10})
    now[0] += 0.2
    source.tick()
    assert source.state == "pending" and source.backend.moves == []
    target.receive(source.session.messages[-1])
    if finish != "timeout":
        source.receive({"type": "entered"})
    ratio = 0.25
    if finish == "return":
        # Return at a different height/width from the original handoff. The
        # target's normalized position must map back across unequal screens.
        target.remote_position = entry_point(target.incoming_edge, 0.8, target.backend.bounds(), inset=0)
        target_now[0] += 1
        dx, dy = {"left": (10, 0), "right": (-10, 0),
                  "top": (0, 10), "bottom": (0, -10)}[side]
        target.remote_move(dx, dy)
        target_now[0] += 0.1
        target.remote_move(dx, dy)
        source.receive(target.session.messages[-1])
        ratio = 0.8
    elif finish == "panic":
        source.handle_command({"action": "panic"})
    elif finish == "disconnected":
        source.handle({"type": "disconnected", "session": source.session})
    else:
        now[0] += 2
        source.tick()
    assert source.state == "local" and not source.backend.captured
    assert source.backend.moves == [pytest.approx(entry_point(side, ratio, bounds))]



def test_two_monitor_source_enters_peer_and_returns_to_correct_physical_display(tmp_path):
    from types import SimpleNamespace
    from test_displays import dual
    from mouseshare.topology import Rect
    source, now = setup(tmp_path/'source')
    target, target_now = setup(tmp_path/'target')
    a, b = 'a'*64, 'b'*64
    source.local_id, target.local_id = a, b
    source.backend.monitors = lambda: dual()['monitors']
    source.backend.bounds = lambda: (-1920, 0, 3840, 1080)
    layout = dict(enabled=True, revision=1, author=a,
                  nodes={a: Rect(0, 0, 640, 180).data(), b: Rect(640, 0, 320, 180).data()})
    for engine, own, peer, screen in [(source, a, b, target.backend.screen_info()),
                                       (target, b, a, source.backend.screen_info())]:
        engine.settings.set(desktop_layout=layout)
        engine.session = SimpleNamespace(peer_id=peer, peer_name=peer[:1], peer_screen=screen,
                                          peer_features=['multi-v1', 'layout-v1', 'monitors-v1'], messages=[])
        engine.session.send = lambda message, session=engine.session: session.messages.append(message) or True
        engine.sessions = {peer: engine.session}
        engine.availability = {peer: True}
    source.physical(dict(type='move', x=1919, y=700, dx=20, dy=0))
    now[0] += .2
    source.tick()
    enter = next(m for m in reversed(source.session.messages) if m['type'] == 'enter')
    target.receive(enter)
    source.receive(target.session.messages[-1])
    assert source.state == 'sending' and target.state == 'receiving'
    assert target.backend.moves[-1] == pytest.approx((8, 700))
    target.remote_position = (0, 300)
    target_now[0] += 1
    target.remote_move(-10, 0)
    target_now[0] += .1
    target.remote_move(-10, 0)
    route = target.session.messages[-1]
    assert route['type'] == 'route' and route['target'] == a
    source.receive(route)
    assert source.state == 'local' and source.backend.moves[-1] == pytest.approx((1911, 300))
