import threading
import time

from mouseshare.config import Settings
from mouseshare.network import Network
from mouseshare.security import Identity


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out")


def make_network(path, auto_approve=True):
    settings = Settings(path)
    identity = Identity(settings.directory)
    pairs, connections, messages, disconnects = [], [], [], []

    def on_pair(session):
        pairs.append(session)
        if auto_approve:
            session.approve(True)
    network = Network(identity, settings, on_pair, connections.append,
                      lambda s, m: messages.append(m), lambda s, e: disconnects.append(s),
                      port=0, bind_host="127.0.0.1")
    network.start()
    return network, pairs, connections, messages, disconnects


def test_real_tls_pair_input_reconnect_and_pin(tmp_path):
    a, ap, ac, am, ad = make_network(tmp_path / "a")
    b, bp, bc, bm, bd = make_network(tmp_path / "b")
    try:
        a.connect("127.0.0.1", b.port, b.identity.id)
        wait_for(lambda: ac and bc)
        assert ap[0].code == bp[0].code
        assert b.identity.id in a.settings.get("peers")
        assert a.identity.id in b.settings.get("peers")
        assert ac[0].sock.cipher()[0]
        ac[0].send({"type": "key", "key": 4, "down": True})
        wait_for(lambda: bm)
        assert bm == [{"type": "key", "key": 4, "down": True}]
        ac[0].stop()
        wait_for(lambda: ad and bd)
        a.connect("127.0.0.1", b.port, b.identity.id)
        wait_for(lambda: len(ac) == 2 and len(bc) == 2)
        assert len(ap) == len(bp) == 1  # Stored pins bypass pairing on reconnect.
    finally:
        a.stop()
        b.stop()


def test_no_input_or_trust_until_both_approve(tmp_path):
    a, ap, ac, am, ad = make_network(tmp_path / "a", False)
    b, bp, bc, bm, bd = make_network(tmp_path / "b", False)
    try:
        a.connect("127.0.0.1", b.port, b.identity.id)
        wait_for(lambda: ap and bp)
        assert not ap[0].send({"type": "key", "key": 4, "down": True})
        ap[0].approve(True)
        time.sleep(0.1)
        assert not ac and not bc
        assert not a.settings.get("peers") and not b.settings.get("peers")
        bp[0].approve(False)
        wait_for(lambda: ad and bd)
        assert not a.settings.get("peers") and not b.settings.get("peers")
    finally:
        a.stop()
        b.stop()


def test_discovery_identity_spoof_is_rejected_before_pairing(tmp_path):
    a, ap, ac, am, ad = make_network(tmp_path / "a")
    b, bp, bc, bm, bd = make_network(tmp_path / "b")
    try:
        a.connect("127.0.0.1", b.port, "f" * 64)
        wait_for(lambda: ad and bd)
        assert not ap and not ac and not bc
    finally:
        a.stop()
        b.stop()


def test_invalid_input_closes_authenticated_connection(tmp_path):
    a, ap, ac, am, ad = make_network(tmp_path / "a")
    b, bp, bc, bm, bd = make_network(tmp_path / "b")
    try:
        a.connect("127.0.0.1", b.port, b.identity.id)
        wait_for(lambda: ac and bc)
        ac[0].send({"type": "key", "key": -100, "down": True})
        wait_for(lambda: bd)
        assert not bm
    finally:
        a.stop()
        b.stop()


def test_concurrent_settings_updates_preserve_all_peers(tmp_path):
    settings = Settings(tmp_path)
    threads = [threading.Thread(target=settings.trust, args=(str(i), "peer", "127.0.0.1")) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(Settings(tmp_path).get("peers")) == 20

