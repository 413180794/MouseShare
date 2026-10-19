"""Bulk channels must preserve input, verify files and clean incomplete batches."""
import hashlib
import os
import time
from pathlib import Path

import pytest

from mouseshare.config import Settings
from mouseshare.network import Network
from mouseshare.security import Identity
from mouseshare.sharing import SharingService, manifest, safe_path, validate_manifest


def wait_for(predicate, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Sharing timed out')


def node(path):
    settings = Settings(path)
    settings.set(receive_directory=str(path / 'inbox'), auto_receive_files=True)
    events, inputs = [], []
    network = Network(Identity(path), settings, lambda s: s.approve(True), lambda s: None,
                      lambda s, m: inputs.append(m), lambda s, e: None, port=0, bind_host='127.0.0.1')
    service = SharingService(network, settings, emit=events.append)
    network.start()
    return network, service, events, inputs


@pytest.fixture
def pair(tmp_path):
    a = node(tmp_path / 'a')
    b = node(tmp_path / 'b')
    a[0].connect('127.0.0.1', b[0].port, b[0].identity.id)
    wait_for(lambda: a[0].session and a[0].session.connected and b[0].session and b[0].session.connected)
    yield a, b
    a[1].stop()
    b[1].stop()
    a[0].stop()
    b[0].stop()


def test_file_folder_and_empty_files_roundtrip_with_live_input(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, messages) = pair
    folder = tmp_path / '资料'
    folder.mkdir()
    (folder / '截图.bin').write_bytes(os.urandom(3 * 1024**2))
    (folder / 'empty.txt').touch()
    (folder / 'empty-folder').mkdir()
    job = send.send_files([folder], clipboard=True)
    for i in range(20):
        assert a.session.send(dict(type='move', dx=i, dy=0))
        time.sleep(0.01)
    wait_for(lambda: send.jobs[job].status in {'complete', 'error'})
    assert send.jobs[job].status == 'complete', send.jobs[job].detail
    target = Path(receive.jobs[job].paths[0])
    assert (target / '截图.bin').read_bytes() == (folder / '截图.bin').read_bytes()
    assert (target / 'empty.txt').stat().st_size == 0
    assert (target / 'empty-folder').is_dir()
    wait_for(lambda: len(messages) == 20)
    assert [message['dx'] for message in messages] == list(range(20))
    assert a.session.connected and b.session.connected
    assert receive.jobs[job].clipboard
    assert not list(target.parent.parent.glob('.mouseshare-*'))
    # Separate batches preserve identical filenames.
    second = send.send_files([folder])
    wait_for(lambda: send.jobs[second].status == 'complete')
    assert receive.jobs[second].paths != receive.jobs[job].paths
    # Also exercise a server-originated bulk channel, using the advertised listening port.
    reverse = receive.send_files([target / 'empty.txt'])
    wait_for(lambda: receive.jobs[reverse].status == 'complete')
    assert Path(send.jobs[reverse].paths[0]).exists()


def test_clipboard_bidirectional_and_rejection_preserve_input(pair):
    (a, send, ae, _), (b, receive, be, _) = pair
    send.send_clipboard(b'{"text":"hello"}')
    wait_for(lambda: any(e['type'] == 'clipboard' for e in be))
    assert next(e['payload'] for e in be if e['type'] == 'clipboard') == b'{"text":"hello"}'
    receive.send_clipboard(b'{"text":"reply"}')
    wait_for(lambda: any(e['type'] == 'clipboard' for e in ae))
    receive.settings.set(clipboard_sync=False)
    before = len([e for e in be if e['type'] == 'clipboard'])
    send.send_clipboard(b'{"text":"disabled"}')
    wait_for(lambda: send.clip_thread is None)
    assert len([e for e in be if e['type'] == 'clipboard']) == before
    assert a.session.connected and b.session.connected


def test_offer_requires_acceptance_and_cancel_cleans_staging(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, _) = pair
    receive.settings.set(auto_receive_files=False)
    source = tmp_path / 'waiting.txt'
    source.write_text('confirmed only')
    job = send.send_files([source])
    wait_for(lambda: job in receive.jobs and receive.jobs[job].status == 'offered')
    assert not list((receive.settings.directory / 'inbox').glob('*'))
    receive.decide(job, False)
    wait_for(lambda: send.jobs[job].status == 'rejected')
    next_job = send.send_files([source])
    wait_for(lambda: next_job in receive.jobs and receive.jobs[next_job].status == 'offered')
    receive.cancel(next_job)
    wait_for(lambda: receive.jobs[next_job].status == 'cancelled')
    assert a.session.connected and b.session.connected


@pytest.mark.parametrize('path', ['../secret', '/absolute', 'C:/x', 'a/../../x', 'a\\b', 'a//b',
                                  'a/./b', 'a./file', 'CON', 'aux.txt', 'a:x', 'a\x00b', 'trailing '])
def test_portable_paths_reject_traversal_and_windows_aliases(path):
    with pytest.raises(ValueError):
        safe_path(path)


def test_manifest_rejects_links_and_case_conflicts(tmp_path):
    source = tmp_path / 'folder'
    source.mkdir()
    (source / 'a').write_text('data')
    if os.name != 'nt':
        (source / 'link').symlink_to(source / 'a')
        with pytest.raises(ValueError):
            manifest([source])
        (source / 'link').unlink()
    with pytest.raises(ValueError):
        manifest([source / 'a', source / 'a'])
    with pytest.raises(ValueError):
        validate_manifest([dict(path='Foo', size=0, directory=False), dict(path='foo', size=0, directory=False)], 0)
    with pytest.raises(ValueError):
        validate_manifest([dict(path='folder/a', size=1, directory=False)], 1)


def test_hash_mismatch_does_not_commit_and_main_connection_survives(pair):
    from mouseshare.network import recv_frame
    from mouseshare.protocol import frame
    import uuid
    (a, send, _, _), (b, receive, _, _) = pair
    key = uuid.uuid4().hex

    def malicious(channel):
        sock = channel.sock
        sock.sendall(frame(dict(type='files', id=key, count=1, total=3, clipboard=False)))
        sock.sendall(frame(dict(type='entry', path='test', size=3, directory=False)))
        assert recv_frame(sock)['accepted']
        sock.sendall(b'abc' + frame(dict(type='hash', sha256=hashlib.sha256(b'wrong').hexdigest())))
        try:
            recv_frame(sock)
        except ConnectionError:
            pass
    a.data_connection(malicious)
    wait_for(lambda: receive.jobs[key].status == 'error')
    assert not list((receive.settings.directory / 'inbox').iterdir())
    assert a.session.connected and b.session.connected


def test_mid_transfer_cancel_removes_partial_files(pair, tmp_path):
    (a, send, _, _), (b, receive, _, _) = pair
    source = tmp_path / 'cancel.bin'
    source.write_bytes(os.urandom(4 * 1024**2))
    def cancel_on_data(event):
        if event['type'] == 'transfer' and event['status'] == 'transferring' and event['done']:
            receive.cancel(event['job'])
    receive.emit = cancel_on_data
    job = send.send_files([source])
    wait_for(lambda: job in receive.jobs and receive.jobs[job].status == 'cancelled')
    wait_for(lambda: not list((receive.settings.directory / 'inbox').glob('*')))
    assert a.session.connected and b.session.connected


def test_data_connection_cannot_pair_a_new_device(pair, tmp_path):
    from mouseshare.network import Session
    import socket
    (a, _, _, _), (b, _, _, _) = pair
    outsider, service, events, _ = node(tmp_path / 'outsider')
    requests = []
    outsider.on_pair = requests.append
    try:
        raw = socket.create_connection(('127.0.0.1', b.port))
        session = Session(outsider, raw, False, b.identity.id, lane='data', work=lambda s: None)
        session.run()
        assert not requests and not outsider.settings.get('peers')
        assert a.session.connected and b.session.connected
    finally:
        service.stop()
        outsider.stop()


def test_manifest_unicode_alias_and_preparation_cancel(tmp_path):
    with pytest.raises(ValueError):
        validate_manifest([dict(path='é', size=0, directory=False), dict(path='e\u0301', size=0, directory=False)], 0)
    source = tmp_path / 'file'
    source.touch()
    def cancelled():
        raise InterruptedError('cancelled')
    with pytest.raises(InterruptedError):
        manifest([source], cancelled)


def test_only_locally_requested_nonce_auto_accepts_and_unsolicited_nonce_is_rejected(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, _) = pair
    receive.settings.set(auto_receive_files=False)
    source = tmp_path / 'paste.txt'
    source.write_text('requested file')
    request, offer = 'a'*32, 'b'*32
    claimed = []
    def authorize(peer, offered, requested):
        valid = peer == a.identity.id and offered == offer and requested == request and not claimed
        if valid:
            claimed.append(requested)
        return valid
    receive.authorize_request = authorize
    job = send.send_files([source], peer_id=b.identity.id, request=request, offer=offer, clipboard=True)
    wait_for(lambda: send.jobs[job].status in {'complete', 'error'})
    assert send.jobs[job].status == 'complete', send.jobs[job].detail
    assert receive.jobs[job].request == request and receive.jobs[job].peer_id == a.identity.id
    replay = send.send_files([source], peer_id=b.identity.id, request=request, offer=offer, clipboard=True)
    wait_for(lambda: send.jobs[replay].status in {'rejected', 'error'})
    assert replay not in receive.jobs
    assert a.session.connected and b.session.connected


def test_bulk_transfer_uses_requested_peer_without_changing_selected_peer(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, _) = pair
    c, other, ce, _ = node(tmp_path / 'c')
    try:
        a.connect('127.0.0.1', c.port, c.identity.id)
        wait_for(lambda: a.peer_session(c.identity.id) and a.peer_session(c.identity.id).connected)
        a.select(b.identity.id)
        source = tmp_path / 'specific.txt'
        source.write_bytes(b'only C')
        job = send.send_files([source], peer_id=c.identity.id)
        wait_for(lambda: send.jobs[job].status in {'complete', 'error'})
        assert send.jobs[job].status == 'complete', send.jobs[job].detail
        assert job in other.jobs and job not in receive.jobs
        assert a.session.peer_id == b.identity.id
    finally:
        other.stop()
        c.stop()


def test_local_paste_destination_never_comes_from_peer_manifest(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, _) = pair
    receive.settings.set(auto_receive_files=False)
    selected = tmp_path/'selected-folder'
    selected.mkdir()
    original = selected/'file.txt'
    original.write_text('existing user file')
    source = tmp_path/'file.txt'
    source.write_text('received copy')
    request, offer = 'a'*32, 'b'*32
    receive.authorize_request = lambda peer, offered, requested: (
        dict(destination=str(selected), max_bytes=1024) if peer == a.identity.id
        and offered == offer and requested == request else False)
    job = send.send_files([source], peer_id=b.identity.id, request=request, offer=offer, clipboard=True)
    wait_for(lambda: send.jobs[job].status in {'complete', 'error'})
    assert send.jobs[job].status == 'complete', send.jobs[job].detail
    received = Path(receive.jobs[job].paths[0])
    assert received.parent.parent == selected and received.read_text() == 'received copy'
    assert original.read_text() == 'existing user file'


def test_prefetch_limit_rejects_transfer_before_writing_bytes(pair, tmp_path):
    (a, send, ae, _), (b, receive, be, _) = pair
    source = tmp_path/'file.txt'
    source.write_bytes(b'larger than the local prefetch allowance')
    receive.authorize_request = lambda *args: dict(destination='', max_bytes=1)
    job = send.send_files([source], peer_id=b.identity.id, request='a'*32, offer='b'*32, clipboard=True)
    wait_for(lambda: send.jobs[job].status in {'complete', 'rejected', 'error'})
    assert send.jobs[job].status != 'complete'
    assert not list((tmp_path/'b/inbox').glob('**/file.txt'))
    assert a.session.connected and b.session.connected
