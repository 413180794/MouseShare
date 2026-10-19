"""Transient desktop file drop: invisible while idle, bound to an authenticated peer."""
from pathlib import Path
import time

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .backdrop import Backdrop
from .drop_design import DropVisual
from .topology import Rect

EDGE_WIDTH = 14


def local_files(mime):
    urls = mime.urls() if mime and mime.hasUrls() else []
    if not urls or len(urls) > 4096 or not all(url.isLocalFile() and url.toLocalFile() for url in urls):
        return []
    return [url.toLocalFile() for url in urls]


def edge_regions(layout, local_id, bounds, peers, legacy_side='right', selected=''):
    """Map touching desktop rectangles to primary-screen logical edge strips."""
    left, top, width, height = bounds.x(), bounds.y(), bounds.width(), bounds.height()
    result = []
    nodes = layout.get('nodes', {}) if layout and layout.get('enabled') else {}
    if local_id not in nodes:
        peers = {selected: peers[selected]} if selected in peers else {}
        nodes = {}
    a = Rect.parse(nodes[local_id]) if nodes else None
    for key in peers:
        if nodes and key not in nodes:
            continue
        b = Rect.parse(nodes[key]) if nodes else None
        for side in ('left', 'right', 'top', 'bottom') if nodes else (legacy_side,):
            vertical = side in {'left', 'right'}
            if nodes:
                distance = {'left': abs(a.x-b.x-b.w), 'right': abs(a.x+a.w-b.x),
                            'top': abs(a.y-b.y-b.h), 'bottom': abs(a.y+a.h-b.y)}[side]
                start, end = ((max(a.y, b.y), min(a.y+a.h, b.y+b.h)) if vertical
                              else (max(a.x, b.x), min(a.x+a.w, b.x+b.w)))
                if distance > 1 or end-start < 8:
                    continue
                offset, span = ((a.y, a.h) if vertical else (a.x, a.w))
                start, end = (start-offset)/span, (end-offset)/span
            else:
                start, end = 0, 1
            if vertical:
                lo, hi = round(start*height), round(end*height)
                geometry = QRect(left if side == 'left' else left+width-EDGE_WIDTH,
                                 top+lo, EDGE_WIDTH, max(1, hi-lo))
            else:
                lo, hi = round(start*width), round(end*width)
                geometry = QRect(left+lo, top if side == 'top' else top+height-EDGE_WIDTH,
                                 max(1, hi-lo), EDGE_WIDTH)
            result.append((key, side, geometry))
    return result


FLAGS = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)


class EdgeSensor(QWidget):
    def __init__(self, owner, session, geometry):
        super().__init__(None, FLAGS)
        self.owner, self.session = owner, session
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle('MouseShare 拖放感应区')
        self.setAcceptDrops(True)
        self.setGeometry(geometry)

    def paintEvent(self, event):
        # Nonzero alpha is required for Windows OLE hit testing. This window is
        # only visible while the physical left mouse button is held.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def dragEnterEvent(self, event):
        paths = local_files(event.mimeData())
        if paths and self.owner.begin(self.session, paths):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if local_files(event.mimeData()) and self.owner.session is self.session and self.owner.active:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = local_files(event.mimeData())
        if paths and self.owner.submit(self.session, paths):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()


class DropSurface(QWidget):
    def __init__(self, owner):
        super().__init__(None, FLAGS)
        self.owner = owner
        self.setWindowTitle('MouseShare · 文件投递')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAcceptDrops(True)
        self.visual = DropVisual(self)
        self.visual.dismissed.connect(owner.cancel)
        self.backdrop = Backdrop(self)

    def resizeEvent(self, event):
        self.visual.setGeometry(self.rect())
        super().resizeEvent(event)

    def present(self, geometry):
        self.setGeometry(geometry)
        self.visual.setGeometry(self.rect())
        if not self.isVisible():
            self.visual.set_blur_available(False)
            self.show()
            self.visual.set_blur_available(self.backdrop.show())
        self.raise_()

    def dismiss(self):
        self.backdrop.close()
        self.hide()

    def dragEnterEvent(self, event):
        paths = local_files(event.mimeData())
        if not self.owner.previewing and paths and self.owner.valid_session(self.owner.session):
            self.owner.describe(paths)
            self.owner.enter_generation += 1
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self.owner.previewing and local_files(event.mimeData()) and self.owner.valid_session(self.owner.session):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.owner.leaving()
        event.accept()

    def dropEvent(self, event):
        paths = local_files(event.mimeData())
        if self.visual.close_button.geometry().contains(event.position().toPoint()):
            self.owner.cancel()
            event.ignore()
            return
        if not self.owner.previewing and paths and self.owner.submit(self.owner.session, paths):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            self.owner.cancel()
            event.ignore()

    def mousePressEvent(self, event):
        if self.owner.previewing:
            self.owner.cancel()
        event.accept()

    def closeEvent(self, event):
        self.backdrop.close()
        super().closeEvent(event)


class EdgePortal(QObject):
    """No idle hint/window; arm native file-drag targets only while dragging."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.sensors = []
        self.routes_key = None
        self.surface = DropSurface(self)
        self.active = self.previewing = self.submitted = self.closed = False
        self.session = None
        self.control_context = None
        self.enter_generation = 0
        self.released_at = None
        self.cooldown = 0
        self.preview_deadline = 0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QApplication.instance().installEventFilter(self)

    def eligible(self):
        state = getattr(self.window, 'ui_state', {})
        return (not self.closed and not self.window.demo and self.window.settings.get('edge_drop', False)
                and self.window.sharing.enabled('files') and state.get('state') in {'local', 'receiving'}
                and self.window.engine.state in {'local', 'receiving'})

    def context(self):
        return self.window.engine.state, getattr(self.window.engine, 'flow', None)

    def valid_session(self, session):
        if not session or not self.eligible():
            return False
        return (session.connected and self.window.network.peer_session(session.peer_id) is session
                and 'sharing-v1' in getattr(session, 'peer_features', [])
                and self.window.engine.availability.get(session.peer_id, False))

    def screen(self):
        return QApplication.primaryScreen()

    def refresh(self):
        if self.closed:
            return
        now = time.monotonic()
        if self.previewing:
            if now >= self.preview_deadline:
                self.cancel()
            return
        if (not self.eligible() or self.active and (not self.valid_session(self.session)
                or self.control_context != self.context())):
            self.cancel()
            self.hide_sensors()
            return
        if self.active and self.submitted:
            return  # The short completion timer owns dismissal after a drop.
        held = 1 in self.window.backend.buttons or 1 in getattr(self.window.backend, 'injected_buttons', set())
        if self.active:
            if not held:
                if self.released_at is None:
                    self.released_at = now
                elif now-self.released_at >= .18:
                    self.cancel()
            else:
                self.released_at = None
        if self.active:
            return
        if not held or now < self.cooldown:
            self.hide_sensors()
            return
        screen = self.screen()
        if not screen:
            return
        peers = {key: session for key, session in list(self.window.network.sessions.items()) if self.valid_session(session)}
        layout = self.window.settings.get('desktop_layout', {})
        selected = getattr(self.window.network.session, 'peer_id', '')
        regions = edge_regions(layout, self.window.identity.id, screen.geometry(), peers,
                               self.window.settings.get('side'), selected)
        key = tuple((peer, side, rect.x(), rect.y(), rect.width(), rect.height(), id(peers[peer]))
                    for peer, side, rect in regions)
        if key != self.routes_key:
            self.destroy_sensors()
            self.routes_key = key
            self.sensors = [EdgeSensor(self, peers[peer], rect) for peer, side, rect in regions]
        for sensor in self.sensors:
            sensor.show()

    def begin(self, session, paths):
        if self.previewing or time.monotonic() < self.cooldown or not self.valid_session(session):
            return False
        if self.active and self.session is not session:
            return False
        screen = self.screen()
        if not screen:
            return False
        self.active, self.session, self.submitted = True, session, False
        self.control_context = self.context()
        self.enter_generation += 1
        self.released_at = None
        self.describe(paths)
        self.surface.present(screen.geometry())
        return True

    def describe(self, paths):
        names = [Path(path).name for path in paths[:2]]
        summary = ' · '.join(names)
        if len(paths) > 2:
            summary += f' 等 {len(paths)} 项'
        elif len(paths) > 1:
            summary = f'{len(paths)} 项 · '+summary
        self.surface.visual.set_context(self.session.peer_name, len(paths), summary, 'hover')

    def submit(self, session, paths):
        if (self.previewing or self.submitted or not self.active or session is not self.session
                or not self.valid_session(session) or self.control_context != self.context()):
            return False
        self.submitted = True
        try:
            self.window.sharing.send_files(paths, peer_id=session.peer_id)
            self.surface.visual.set_context(session.peer_name, len(paths), state='sending')
            self.window.share_panel.status.setText('已提交文件，传输进度显示在下方记录中')
        except (OSError, ValueError) as exc:
            self.window.share_panel.status.setText(str(exc))
            self.surface.visual.set_context(session.peer_name, summary=str(exc), state='unavailable')
        token = self.enter_generation
        QTimer.singleShot(450, lambda: self.cancel() if self.enter_generation == token else None)
        return True

    def leaving(self):
        token = self.enter_generation
        QTimer.singleShot(80, lambda: self.cancel() if self.active and not self.submitted
                          and self.enter_generation == token else None)

    def preview(self):
        if self.closed:
            return
        self.cancel()
        screen = self.screen()
        if not screen:
            return
        self.previewing, self.active = True, True
        self.preview_deadline = time.monotonic()+3
        session = self.window.network.session
        name = session.peer_name if session and session.connected else '另一台电脑'
        self.surface.visual.set_context(name, summary='预览 · 3 秒后自动收起')
        self.surface.present(screen.geometry())

    def eventFilter(self, watched, event):
        if self.active and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            previewing = self.previewing
            self.cancel()
            return previewing
        return False

    def cancel(self):
        self.enter_generation += 1
        self.active = self.previewing = self.submitted = False
        self.session, self.released_at = None, None
        self.control_context = None
        self.cooldown = time.monotonic()+.3
        self.surface.dismiss()
        self.hide_sensors()

    def hide_sensors(self):
        for sensor in self.sensors:
            sensor.hide()

    def destroy_sensors(self):
        for sensor in self.sensors:
            sensor.close()
            sensor.deleteLater()
        self.sensors = []
        self.routes_key = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.cancel()
        self.destroy_sensors()
        self.surface.close()
        self.surface.deleteLater()
        QApplication.instance().removeEventFilter(self)


def run_preview(app, smoke=False):
    """A bounded standalone preview: no identity, network, hooks or real files."""
    from types import SimpleNamespace
    host = QWidget()
    host.demo = True
    host.network = SimpleNamespace(session=SimpleNamespace(peer_name='Windows 台式机', connected=True))
    controller = EdgePortal(host)
    controller.preview()
    controller.preview_deadline = time.monotonic()+12
    app.aboutToQuit.connect(controller.close)
    if smoke:
        def check():
            try:
                assert controller.surface.isVisible()
                assert controller.surface.geometry() == app.primaryScreen().geometry()
                assert not controller.surface.isActiveWindow()
                assert not controller.surface.backdrop.error, controller.surface.backdrop.error
                controller.surface.dismiss()
                controller.surface.present(app.primaryScreen().geometry())
                assert not controller.surface.backdrop.error, controller.surface.backdrop.error
                print('MouseShare drop overlay smoke OK; native blur='+str(controller.surface.visual.blur_available), flush=True)
                app.exit(0)
            except Exception as exc:
                print('MouseShare drop overlay smoke failed: '+repr(exc), flush=True)
                app.exit(1)
        QTimer.singleShot(100, check)
    else:
        controller.surface.visual.dismissed.connect(app.quit)
        QTimer.singleShot(12000, app.quit)
    result = app.exec()
    controller.close()
    return result
