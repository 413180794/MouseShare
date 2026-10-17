"""Exercise two real TLS engines with simulated native devices, including a mid-session game lock."""
import time

from mouseshare.config import Settings
from mouseshare.engine import Engine
from mouseshare.input.base import NullBackend
from mouseshare.network import Network
from mouseshare.security import Identity


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Input handoff timed out")


def make_node(path, name, side):
    settings = Settings(path)
    settings.set(name=name, side=side)
    identity = Identity(settings.directory)
    engine = Engine(settings)
    engine.backend = NullBackend(engine.enqueue)
    engine.backend.running = True
    network = Network(identity, settings, lambda s: s.approve(True),
                      lambda s: engine.enqueue({"type": "connected", "session": s}),
                      lambda s, m: engine.enqueue({"type": "network", "session": s, "message": m}),
                      lambda s, m: engine.enqueue({"type": "disconnected", "session": s}),
                      port=0, bind_host="127.0.0.1")
    engine.start()
    network.start()
    return engine, network


def test_two_engines_route_input_and_revoke_on_game_mode(tmp_path):
    source, a = make_node(tmp_path / "a", "Windows", "right")
    target, b = make_node(tmp_path / "b", "Mac", "left")
    try:
        a.connect("127.0.0.1", b.port, b.identity.id)
        wait_for(lambda: source.peer_available and target.peer_available)
        source.enqueue({"type": "move", "x": 1919, "y": 500, "dx": 5, "dy": 0})
        wait_for(lambda: source.state == "sending" and target.state == "receiving")
        source.enqueue({"type": "key", "key": 225, "down": True})
        source.enqueue({"type": "button", "button": 1, "down": True})
        wait_for(lambda: target.backend.injected_keys == {225} and target.backend.injected_buttons == {1})
        assert not source.backend.injected_keys
        target.command("game")
        wait_for(lambda: source.state == target.state == "local" and not source.peer_available)
        assert target.game and not target.backend.injected_keys and not target.backend.injected_buttons
        assert not source.backend.captured
        target.command("game")
        wait_for(lambda: source.peer_available)
        source.backend.physical({"type": "key", "key": 225, "down": False})
        source.backend.physical({"type": "button", "button": 1, "down": False})
    finally:
        source.stop()
        target.stop()
        a.stop()
        b.stop()

