"""Local paste authorization and focus/clipboard/activity protection, with no OS injection."""
import os
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication, QWidget
from mouseshare.clipboard import ClipboardSync
from mouseshare.config import Settings
from mouseshare.engine import Engine
from mouseshare.file_clipboard import FileClipboard
from mouseshare.input.base import NullBackend


@pytest.fixture
def hub(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    settings = window.settings = Settings(tmp_path)
    window.engine = Engine(settings)
    backend = window.backend = window.engine.backend = NullBackend(lambda event: True)
    backend.running = True
    focus = [123]
    backend.focus_token = lambda: focus[0]
    calls, messages = [], []
    backend.clipboard_shortcut = calls.append
    peer = SimpleNamespace(peer_id='b'*64, connected=True, peer_features=['sharing-v1', 'file-offer-v1'],
                           peer_name='Remote', send=lambda m: messages.append(m) or True)
    window.network = SimpleNamespace(session=peer, sessions={peer.peer_id: peer},
                                      peer_session=lambda key: peer if key == peer.peer_id else None)
    window.engine.session = peer
    window.engine.sessions = window.network.sessions
    window.sharing = SimpleNamespace(network=window.network, enabled=lambda kind: True,
                                     send_files=lambda *a, **kw: calls.append((a, kw)))
    mime = QMimeData()
    mime.setText('local clipboard')
    sequence = [1]
    clipboard = SimpleNamespace(mimeData=lambda: clipboard.mime, mime=mime)
    def set_mime(value):
        clipboard.mime = value
        sequence[0] += 1
    clipboard.setMimeData = set_mime
    window.clipboard_sync = ClipboardSync(window.sharing, settings, clipboard=clipboard)
    window.clipboard_sync.sequence = lambda: sequence[0]
    window.clipboard_sync.timer.stop()
    monkeypatch.setattr(QApplication, 'activeWindow', staticmethod(lambda: None))
    control = FileClipboard(window)
    control.timer.stop()
    yield control, peer, calls, messages, sequence, focus, app
    control.stop()
    window.clipboard_sync.stop()
    window.close()


def offer(hub):
    control, peer, *_ = hub
    control.receive(peer, dict(type='file_offer', offer='a'*32, names=['demo.txt'], count=1))


def test_offer_only_sends_metadata_and_native_paste_is_opt_in(hub, tmp_path):
    control, peer, calls, messages, sequence, _, _ = hub
    control.offer_files([tmp_path / 'demo.txt'])
    assert not calls
    assert messages[0] == dict(type='file_offer', offer=control.local['id'], count=1, names=['demo.txt'])
    assert sequence == [1]
    offer(hub)
    assert control.backend.native_file_paste_ready
    control.window.settings.set(native_file_paste=False)
    control.tick()
    assert not control.backend.native_file_paste_ready
    control.action('paste')
    assert any(m['type'] == 'file_request' for m in messages)


@pytest.mark.parametrize('change', ['none', 'focus', 'activity', 'clipboard', 'flow'])
def test_matching_request_pastes_only_into_unchanged_original_context(hub, change, tmp_path):
    control, peer, calls, messages, sequence, focus, app = hub
    offer(hub)
    control.action('paste')
    request = next(m for m in messages if m['type'] == 'file_request')
    assert not control.claim('c'*64, request['offer'], request['request'])
    assert control.claim(peer.peer_id, request['offer'], request['request'])
    assert not control.claim(peer.peer_id, request['offer'], request['request'])
    if change == 'focus':
        focus[0] = 456
    elif change == 'activity':
        control.engine.activity_counter += 1
    elif change == 'clipboard':
        sequence[0] += 1
    elif change == 'flow':
        control.engine.flow = 'c'*32
    control.transfer(dict(type='transfer', status='complete', direction='receive', request=request['request'],
                          offer=request['offer'], peer=peer.peer_id, paths=[str(tmp_path / 'demo.txt')]))
    from PySide6.QtTest import QTest
    QTest.qWait(140)
    app.processEvents()
    assert calls == (['paste'] if change == 'none' else [])
    assert sequence[0] == (2 if change in {'none', 'clipboard'} else 1)


def test_local_copy_revokes_native_offer_and_changed_source_rejects_request(hub, tmp_path):
    control, peer, calls, messages, sequence, *_ = hub
    offer(hub)
    sequence[0] += 1
    control.tick()
    assert not control.backend.native_file_paste_ready
    control.offer_files([tmp_path / 'demo.txt'])
    token = control.local['id']
    sequence[0] += 1
    control.receive(peer, dict(type='file_request', offer=token, request='d'*32))
    assert not calls and any(m['type'] == 'file_error' for m in messages)


def test_shared_hotkey_does_not_drop_capture_and_paste_shortcut_uses_platform_modifier():
    backend = NullBackend(lambda event: events.append(event) or True)
    events = []
    backend.capture(True)
    backend.sharing_shortcuts_enabled = True
    for key in [224, 226, 225, 25]:
        backend.physical(dict(type='key', key=key, down=True))
    assert events[-1] == dict(type='command', action='share_paste') and backend.captured
    backend.copy_modifier = {227, 231}
    backend.clipboard_shortcut('paste')
    assert not backend.injected_keys and backend.captured


def test_three_computer_paste_uses_latest_offer_even_when_controller_is_an_older_source(hub):
    control, peer, calls, messages, sequence, *_ = hub
    offer(hub)
    newer = SimpleNamespace(peer_id='c'*64, connected=True, peer_name='Third computer',
                            peer_features=peer.peer_features, send=lambda m: messages.append(m) or True)
    control.window.network.sessions[newer.peer_id] = newer
    control.window.network.peer_session = control.window.network.sessions.get
    control.receive(newer, dict(type='file_offer', offer='c'*32, names=['newer.txt'], count=1))
    assert control.engine.session is peer
    control.action('paste')
    request = next(m for m in reversed(messages) if m['type'] == 'file_request')
    assert request['offer'] == 'c'*32
