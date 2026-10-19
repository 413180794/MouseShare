"""Gesture lifecycle and destination binding, isolated from the user's desktop."""
import os
import time
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from mouseshare.config import Settings
from mouseshare.drop_overlay import EDGE_WIDTH, EdgePortal, edge_regions, local_files
from mouseshare.topology import Rect

A, B, C = (letter*64 for letter in 'abc')


@pytest.fixture
def portal(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.settings = Settings(tmp_path)
    window.settings.set(edge_drop=True)
    calls = []
    peer = SimpleNamespace(peer_id=B, peer_name='Windows 台式机', connected=True, peer_features=['sharing-v1'])
    window.demo = False
    window.identity = SimpleNamespace(id=A)
    window.backend = SimpleNamespace(buttons=set())
    window.engine = SimpleNamespace(state='local', availability={B: True})
    window.ui_state = dict(state='local', peer_available=True)
    window.network = SimpleNamespace(session=peer, sessions={B: peer})
    window.network.peer_session = window.network.sessions.get
    window.sharing = SimpleNamespace(enabled=lambda kind: True, send_files=lambda paths, **kw: calls.append((paths, kw)))
    window.share_panel = SimpleNamespace(status=QLabel())
    controller = EdgePortal(window)
    controller.timer.stop()
    yield controller, window, peer, calls, app
    controller.close()
    window.close()


def mime_file(path='/tmp/example.txt'):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    return mime


def test_partial_edges_match_layout_overlap_and_multiple_destinations():
    nodes = {A: Rect(0, 0, 320, 360).data(), B: Rect(320, 0, 320, 180).data(), C: Rect(320, 180, 320, 180).data()}
    layout = dict(enabled=True, nodes=nodes)
    regions = edge_regions(layout, A, QRect(100, 50, 1920, 1080), {B: object(), C: object()})
    assert [(key, side, rect.getRect()) for key, side, rect in regions] == [
        (B, 'right', (100+1920-EDGE_WIDTH, 50, EDGE_WIDTH, 540)),
        (C, 'right', (100+1920-EDGE_WIDTH, 590, EDGE_WIDTH, 540))]
    assert edge_regions(layout, A, QRect(0, 0, 1920, 1080), {}) == []


def test_local_file_mime_is_bounded_and_rejects_text_or_remote_urls():
    assert local_files(mime_file()) == ['/tmp/example.txt']
    mime = QMimeData()
    mime.setText('hello')
    assert not local_files(mime)
    mime.setUrls([QUrl('https://example.com/file')])
    assert not local_files(mime)
    mime.setUrls([QUrl.fromLocalFile('/tmp/example')]*4097)
    assert not local_files(mime)


def test_idle_has_no_hint_and_sensors_only_arm_while_mouse_is_held(portal):
    controller, window, peer, calls, app = portal
    controller.refresh()
    assert not controller.sensors and not controller.surface.isVisible()
    window.backend.buttons.add(1)
    controller.refresh()
    assert len(controller.sensors) == 1 and controller.sensors[0].isVisible()
    mime = QMimeData()
    mime.setText('ordinary text selection')
    event = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.sensors[0].dragEnterEvent(event)
    assert not event.isAccepted() and not controller.active
    window.backend.buttons.clear()
    controller.refresh()
    assert not any(sensor.isVisible() for sensor in controller.sensors)
    assert not calls


def test_drop_targets_original_peer_once_even_if_selection_changes(portal):
    controller, window, peer, calls, app = portal
    window.backend.buttons.add(1)
    controller.refresh()
    mime = mime_file()
    enter = QDragEnterEvent(QPoint(2, 2), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.sensors[0].dragEnterEvent(enter)
    assert enter.isAccepted() and controller.active and controller.surface.isVisible()
    assert controller.surface.geometry() == app.primaryScreen().geometry()
    window.network.session = SimpleNamespace(peer_id=C, connected=True)
    # Native mouse-up may precede Qt's drop callback; keep a short delivery grace.
    window.backend.buttons.clear()
    controller.refresh()
    assert controller.active
    drop = QDropEvent(QPointF(200, 200), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.surface.dropEvent(drop)
    assert drop.isAccepted()
    assert calls == [(['/tmp/example.txt'], dict(peer_id=B))]
    assert controller.surface.visual.state == 'sending'
    assert controller.surface.visual.close_button.accessibleName() == '关闭投递提示'
    controller.surface.dropEvent(drop)
    assert len(calls) == 1


@pytest.mark.parametrize('cause', ['disconnect', 'replacement', 'pause', 'handoff', 'setting', 'peer_game'])
def test_changed_state_dismisses_overlay_and_never_sends(portal, cause):
    controller, window, peer, calls, app = portal
    window.backend.buttons.add(1)
    assert controller.begin(peer, ['/tmp/file'])
    if cause == 'disconnect':
        peer.connected = False
    elif cause == 'replacement':
        window.network.sessions[B] = SimpleNamespace(peer_id=B, connected=True)
    elif cause == 'pause':
        window.sharing.enabled = lambda kind: False
    elif cause == 'handoff':
        window.engine.state = 'sending'
    elif cause == 'setting':
        window.settings.set(edge_drop=False)
    else:
        window.engine.availability[B] = False
    controller.refresh()
    assert not controller.active and not controller.surface.isVisible()
    assert not controller.submit(peer, ['/tmp/file']) and not calls


def test_cancelled_native_drag_recovers_even_if_mouse_position_stays_inside(portal):
    controller, window, peer, calls, app = portal
    assert controller.begin(peer, ['/tmp/file'])
    window.backend.buttons.clear()
    controller.released_at = time.monotonic()-.3
    controller.refresh()
    assert not controller.active and not controller.surface.isVisible() and not calls


def test_preview_is_short_cancellable_and_never_sends_files(portal):
    controller, window, peer, calls, app = portal
    controller.preview()
    assert controller.previewing and controller.surface.isVisible()
    assert not controller.submit(peer, ['/tmp/file'])
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert controller.eventFilter(window, event)
    assert not controller.surface.isVisible() and not controller.active
    controller.preview()
    controller.preview_deadline = time.monotonic()-1
    controller.refresh()
    assert not controller.surface.isVisible() and not calls




def test_remote_controlled_file_drag_arms_sensors_and_context_change_cancels(portal):
    controller, window, peer, calls, app = portal
    window.engine.state = 'receiving'
    window.engine.flow = '1'*32
    window.ui_state['state'] = 'receiving'
    window.backend.injected_buttons = {1}
    controller.refresh()
    assert controller.sensors and controller.sensors[0].isVisible()
    assert controller.begin(peer, ['/tmp/file'])
    window.engine.flow = '2'*32
    assert not controller.submit(peer, ['/tmp/file'])
    controller.refresh()
    assert not controller.active and not calls


def test_dropping_on_close_control_cancels_instead_of_sending(portal):
    controller, window, peer, calls, app = portal
    assert controller.begin(peer, ['/tmp/file'])
    app.processEvents()
    position = QPointF(controller.surface.visual.close_button.geometry().center())
    mime = mime_file()
    event = QDropEvent(position, Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    controller.surface.dropEvent(event)
    assert not event.isAccepted() and not controller.active and not calls
