"""Gesture lifecycle and destination binding, isolated from the user's desktop."""
import os
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from mouseshare.config import Settings
from mouseshare.drop_design import edge_shape
from mouseshare.drop_overlay import EDGE_WIDTH, EdgePortal, edge_regions, hint_geometry, local_files
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
    bounds = app.primaryScreen().geometry()
    geometry = controller.surface.geometry()
    assert bounds.contains(geometry) and geometry != bounds
    assert geometry.right() == bounds.right()
    assert not any(sensor.isVisible() for sensor in controller.sensors)
    window.network.session = SimpleNamespace(peer_id=C, connected=True)
    # Native mouse-up may precede Qt's drop callback; keep a short delivery grace.
    window.backend.buttons.clear()
    controller.refresh()
    assert controller.active
    drop = QDropEvent(QPointF(controller.surface.rect().center()), Qt.DropAction.CopyAction, mime,
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


@pytest.mark.parametrize('side', ['left', 'right', 'top', 'bottom'])
@pytest.mark.parametrize('bounds', [QRect(0, 0, 800, 600), QRect(-1920, -200, 1920, 1080),
                                    QRect(100, 50, 3840, 2160), QRect(0, 0, 900, 1600)])
def test_hint_stays_small_and_attached_near_drag_entry(bounds, side):
    anchors = ([QPoint(bounds.left(), y) for y in (bounds.top(), bounds.center().y(), bounds.bottom())]
               if side == 'left' else
               [QPoint(bounds.right(), y) for y in (bounds.top(), bounds.center().y(), bounds.bottom())]
               if side == 'right' else
               [QPoint(x, bounds.top()) for x in (bounds.left(), bounds.center().x(), bounds.right())]
               if side == 'top' else
               [QPoint(x, bounds.bottom()) for x in (bounds.left(), bounds.center().x(), bounds.right())])
    for anchor in anchors:
        rect = hint_geometry(bounds, side, anchor)
        assert bounds.contains(rect) and rect.contains(anchor)
        assert rect.width()*rect.height() < bounds.width()*bounds.height()*.15
        assert getattr(rect, side)() == getattr(bounds, side)()
        # The screen-facing edge stays painted/hittable at its two ends.
        shape = edge_shape(QRectF(0, 0, rect.width(), rect.height()), side)
        points = {'left': [(1, 1), (1, rect.height()-1)],
                  'right': [(rect.width()-1, 1), (rect.width()-1, rect.height()-1)],
                  'top': [(1, 1), (rect.width()-1, 1)],
                  'bottom': [(1, rect.height()-1), (rect.width()-1, rect.height()-1)]}[side]
        assert all(shape.contains(QPointF(*point)) for point in points)


def test_motion_is_subtle_stationary_and_stops_when_hidden(portal, monkeypatch):
    from PySide6.QtTest import QTest
    monkeypatch.setattr('mouseshare.drop_design.motion_permitted', lambda: True)
    controller, window, peer, calls, app = portal
    assert controller.begin(peer, ['/tmp/file'], side='left', anchor=QPoint(0, 90))
    visual = controller.surface.visual
    before = controller.surface.geometry()
    frame = visual.motion_frame()
    QTest.qWait(120)
    assert visual.motion.isActive() and frame != visual.motion_frame()
    assert abs(visual.motion_frame()[2]) <= 1.8
    assert controller.surface.geometry() == before
    controller.cancel()
    assert not visual.motion.isActive()


def test_reduced_motion_preserves_static_hint(portal, monkeypatch):
    monkeypatch.setattr('mouseshare.drop_design.motion_permitted', lambda: False)
    controller, window, peer, calls, app = portal
    assert controller.begin(peer, ['/tmp/file'])
    assert controller.surface.isVisible()
    assert not controller.surface.visual.motion.isActive()
    assert controller.surface.visual.motion_frame() == (1., .65, 0.)


def test_preview_uses_layout_edge_instead_of_legacy_direction(portal):
    controller, window, peer, calls, app = portal
    window.settings.set(side='right', desktop_layout=dict(enabled=True, nodes={
        A: Rect(0, 180, 320, 180).data(), B: Rect(0, 0, 320, 180).data()}))
    controller.preview()
    assert controller.surface.visual.side == 'top'
    assert controller.surface.geometry().top() == app.primaryScreen().geometry().top()
    assert not calls


@pytest.mark.parametrize('reenter', [False, True])
def test_leaving_hint_cancels_unless_same_drag_returns(portal, reenter, monkeypatch):
    controller, window, peer, calls, app = portal
    assert controller.begin(peer, ['/tmp/file'])
    geometry = controller.surface.geometry()
    # Exercise the expired deadline deterministically: initial font/window setup
    # on a loaded runner can take longer than a short wall-clock qWait.
    deadlines = []
    monkeypatch.setattr('mouseshare.drop_overlay.QTimer.singleShot', lambda _delay, callback: deadlines.append(callback))
    controller.surface.dragLeaveEvent(QDragLeaveEvent())
    if reenter:
        mime = mime_file()  # Qt drag events borrow the MIME pointer; keep its Python owner alive.
        event = QDragEnterEvent(QPoint(20, 100), Qt.DropAction.CopyAction, mime,
                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        controller.surface.dragEnterEvent(event)
        assert event.isAccepted()
    assert deadlines
    for deadline in deadlines:
        deadline()
    assert controller.active == reenter
    assert controller.surface.isVisible() == reenter
    assert controller.surface.geometry() == geometry
    assert not calls


def test_secondary_monitor_drop_sensor_only_on_outer_connected_edge():
    from types import SimpleNamespace
    from mouseshare.drop_overlay import edge_regions
    a, b = 'a'*64, 'b'*64
    layout = dict(enabled=True, nodes={a: dict(x=0, y=0, w=640, h=180),
                                      b: dict(x=640, y=0, w=320, h=180)})
    peers = {b: SimpleNamespace(peer_screen=dict(w=1920, h=1080))}
    desktop = QRect(-1920, 0, 3840, 1080)
    assert not edge_regions(layout, a, QRect(-1920, 0, 1920, 1080), peers, desktop_bounds=desktop)
    routes = edge_regions(layout, a, QRect(0, 0, 1920, 1080), peers, desktop_bounds=desktop)
    assert len(routes) == 1 and routes[0][0:2] == (b, 'right')
    assert routes[0][2].right() == 1919
    assert not edge_regions({}, a, QRect(-1920, 0, 1920, 1080), peers, selected=b, desktop_bounds=desktop)
    assert edge_regions({}, a, QRect(0, 0, 1920, 1080), peers, selected=b, desktop_bounds=desktop)
