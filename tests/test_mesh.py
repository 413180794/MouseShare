"""Three real TLS input lanes: A controls B, then C, then B, then returns to A."""
import pytest
from test_end_to_end import make_node, wait_for
from mouseshare.topology import Rect


@pytest.fixture
def mesh(tmp_path):
    nodes = [make_node(tmp_path / name, name, 'right') for name in 'ABC']
    engines, networks = zip(*nodes)
    keys = [network.identity.id for network in networks]
    layout = dict(enabled=True, author=keys[0], revision=1,
                  nodes={key: Rect(index*320, 0, 320, 180).data() for index, key in enumerate(keys)})
    for engine, network in nodes:
        engine.local_id = network.identity.id
        engine.settings.set(desktop_layout=layout)
    for index, a in enumerate(networks):
        for b in networks[index+1:]:
            a.connect('127.0.0.1', b.port, b.identity.id)
    wait_for(lambda: all(len(e.sessions) == 2 and all(e.availability.values()) for e in engines))
    yield engines, networks, keys
    for engine, network in nodes:
        engine.stop()
        network.stop()


def enter(a, b):
    a.enqueue(dict(type='move', x=1919, y=500, dx=6, dy=0))
    wait_for(lambda: a.state == 'sending' and b.state == 'receiving')


def route(a, b, c, side, target):
    # A remains the only physical capture. B reports its own edge, then A
    # verifies the exact neighbor and switches direct authenticated sessions.
    b.session.send(dict(type='route', flow=b.flow, edge=side, position=.5, target=target))
    wait_for(lambda: a.state == 'sending' and c.state == 'receiving')
    wait_for(lambda: b.state == 'standby')
    assert b.backend.cursor_is_hidden and not b.backend.captured


def test_three_node_chain_returns_with_one_capture_and_clears_all_cursors(mesh):
    (a, b, c), _, keys = mesh
    enter(a, b)
    flow = a.flow
    route(a, b, c, 'right', keys[2])
    assert a.flow == flow and a.backend.captured and not c.backend.captured
    a.enqueue(dict(type='key', key=4, down=True))
    wait_for(lambda: c.backend.injected_keys == {4})
    assert not b.backend.injected_keys
    a.enqueue(dict(type='key', key=4, down=False))
    wait_for(lambda: not c.backend.injected_keys)
    route(a, c, b, 'left', keys[1])
    assert not b.backend.cursor_is_hidden
    b.session.send(dict(type='route', flow=b.flow, edge='left', position=.75, target=keys[0]))
    wait_for(lambda: all(e.state == 'local' for e in (a, b, c)))
    assert all(not e.backend.captured and not e.backend.cursor_is_hidden for e in (a, b, c))
    assert a.handoff_side == 'right'
    assert not a.flow


@pytest.mark.parametrize('finish', ['game', 'panic', 'disconnect'])
def test_any_participant_failure_restores_entire_chain(mesh, finish):
    (a, b, c), _, _ = mesh
    enter(a, b)
    route(a, b, c, 'right', c.local_id)
    if finish == 'disconnect':
        a.sessions[b.local_id].stop()
    else:
        b.command(finish)
    wait_for(lambda: all(e.state == 'local' for e in (a, b, c)))
    assert all(not e.backend.captured and not e.backend.cursor_is_hidden for e in (a, b, c))


def test_offline_or_blocked_neighbor_does_not_jump_over_screen_and_stale_flow_is_ignored(mesh):
    (a, b, c), _, _ = mesh
    enter(a, b)
    c.command('game')
    wait_for(lambda: not a.availability[c.local_id])
    b.session.send(dict(type='route', flow=b.flow, edge='right', position=.5, target=c.local_id))
    b.session.send(dict(type='release', flow='0'*32))
    # An ordered clipboard barrier lets us observe both earlier packets delivered.
    b.session.send(dict(type='paste_ready', ready=True))
    wait_for(lambda: a.paste_ready.get(b.local_id))
    assert a.state == 'sending' and b.state == 'receiving' and c.state == 'local'
