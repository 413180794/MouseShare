from mouseshare.config import Settings
from mouseshare.engine import Engine
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
    assert {"type": "return"} in engine.session.messages
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

