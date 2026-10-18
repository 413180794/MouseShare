"""On-demand file clipboard. A local paste intent authorizes exactly one transfer."""
from pathlib import Path
import threading
import time
import uuid

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from .clipboard import wayland_session
from .engine import peer_id, supports


class FileClipboard(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.engine, self.backend = window.engine, window.backend
        self.sync, self.service = window.clipboard_sync, window.sharing
        self.local = None
        self.offers, self.pending = {}, {}
        self.lock = threading.RLock()
        self.copy_wait = None
        self.ready_sent = None
        self.sync.files_handler = self.offer_files
        self.sync.on_content = self.content_changed
        self.service.authorize_request = self.claim
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def allowed(self):
        return (self.service.enabled('files') and self.service.enabled('clipboard')
                and self.window.settings.get('clipboard_files', True))

    def sessions(self):
        return [s for s in list(self.window.network.sessions.values()) if s.connected and supports(s, 'file-offer-v1')]

    def send(self, session, message):
        if session and session.connected and supports(session, 'file-offer-v1'):
            return session.send(message)
        return False

    def clear_local(self):
        if self.local:
            for session in self.sessions():
                self.send(session, dict(type='file_clear', offer=self.local['id']))
        self.local = None

    def content_changed(self, paths, sequence):
        self.clear_local()
        for offer in self.offers.values():
            offer['eligible'] = False

    def offer_files(self, paths):
        if not self.allowed():
            return
        paths = [str(Path(p).absolute()) for p in paths]
        if not paths or len(paths) > 4096:
            raise ValueError('每次最多复制 4096 个文件或文件夹')
        names = [Path(p).name for p in paths[:12]]
        if any(not name or len(name) > 255 or any(ord(c) < 32 for c in name) for name in names):
            raise ValueError('文件名无法共享')
        self.clear_local()
        self.local = dict(id=uuid.uuid4().hex, paths=paths, sequence=self.sync.sequence(), names=names)
        self.sync.last_sequence = self.sync.sequence_provider()
        self.sync.active = True
        message = dict(type='file_offer', offer=self.local['id'], count=len(paths), names=names)
        peers = self.sessions()
        for session in peers:
            self.send(session, message)
        # Older clients retain the explicit receive workflow.
        selected = self.window.network.session
        if selected and selected.connected and not supports(selected, 'file-offer-v1'):
            self.service.send_files(paths, clipboard=True)
        self.sync.status('文件已共享：在目标窗口按 Ctrl+Alt+Shift+V 接收并粘贴')
        self.tick()

    def handle_event(self, event):
        kind = event['type']
        if kind == 'control_message':
            self.receive(event['session'], event['message'])
        elif kind == 'clipboard_action':
            session = event.get('session')
            if session and (self.engine.state != 'receiving' or self.engine.session is not session
                            or event.get('flow') != self.engine.flow):
                return
            if session is None and self.engine.state != 'local':
                return
            self.action(event['action'])
        elif kind == 'peer_connected':
            self.send(event['session'], dict(type='paste_ready', ready=bool(self.ready_sent)))

    def receive(self, session, message):
        kind, key = message['type'], peer_id(session)
        if kind == 'file_clear':
            if self.offers.get(key, {}).get('id') == message['offer']:
                self.offers.pop(key, None)
        elif kind == 'file_offer' and self.allowed():
            self.offers[key] = dict(id=message['offer'], names=message['names'], stamp=time.monotonic(),
                                    eligible=True, sequence=self.sync.sequence(), session=session)
            self.sync.status(f"{session.peer_name} 已复制 {message['count']} 项；在目标窗口按共享粘贴键")
        elif kind == 'file_request':
            current = self.local
            if (not self.allowed() or not current or current['id'] != message['offer']
                    or current['sequence'] != self.sync.sequence()):
                self.send(session, dict(type='file_error', request=message['request'], message='源剪贴板已变化，请重新复制'))
                return
            try:
                self.service.send_files(current['paths'], clipboard=True, peer_id=key,
                                        request=message['request'], offer=message['offer'])
            except (ValueError, OSError) as exc:
                self.send(session, dict(type='file_error', request=message['request'], message=str(exc)[:160]))
        elif kind == 'file_error':
            with self.lock:
                pending = self.pending.get(message['request'])
                if pending and pending['peer'] == key:
                    self.pending.pop(message['request'])
                    self.sync.status(message['message'])
        self.tick()

    def choose_offer(self, native=False):
        values = [offer for key, offer in self.offers.items()
                  if self.window.network.peer_session(key) is offer['session']
                  and (not native or offer['eligible'] and offer['sequence'] == self.sync.sequence())]
        selected = peer_id(self.engine.session)
        return max(values, key=lambda o: (peer_id(o['session']) == selected, o['stamp']), default=None)

    def context(self):
        return self.engine.state, self.engine.flow, peer_id(self.engine.session)

    def snapshot(self):
        return dict(focus=self.backend.focus_token(), activity=self.engine.activity_counter,
                    sequence=self.sync.sequence(), context=self.context())

    def unchanged(self, pending):
        return (self.allowed() and self.backend.desktop_active() and not wayland_session()
                and pending['focus'] is not None and QApplication.activeWindow() is None
                and pending['focus'] == self.backend.focus_token()
                and pending['activity'] == self.engine.activity_counter
                and pending['sequence'] == self.sync.sequence() and pending['context'] == self.context())

    def action(self, action):
        if not self.allowed():
            return
        if action == 'copy':
            if QApplication.activeWindow() is not None or not self.backend.ready() or wayland_session():
                self.sync.send_current()
                return
            before = self.sync.sequence()
            self.backend.clipboard_shortcut('copy')
            self.copy_wait = (before, time.monotonic()+1.5, self.backend.focus_token())
            return
        offer = self.choose_offer()
        if not offer:
            # Preserve native text/file paste when no remote file offer exists.
            if self.backend.ready() and not wayland_session() and QApplication.activeWindow() is None:
                self.backend.clipboard_shortcut('paste')
            else:
                self.sync.status('请先在另一台电脑复制文件')
            return
        token = uuid.uuid4().hex
        with self.lock:
            if len(self.pending) >= 2:
                self.sync.status('已有文件正在粘贴，请等待传输完成')
                return
            self.pending[token] = dict(self.snapshot(), peer=peer_id(offer['session']), offer=offer['id'],
                                       claimed=False, deadline=time.monotonic()+1800)
        if not self.send(offer['session'], dict(type='file_request', offer=offer['id'], request=token)):
            with self.lock:
                self.pending.pop(token, None)
            self.sync.status('目标电脑已断开，请重新连接')
        else:
            self.sync.status('正在取回文件；保持目标窗口即可自动粘贴')

    def claim(self, peer, offer, request):
        # Called by a data-channel worker; no GUI or native clipboard API here.
        with self.lock:
            pending = self.pending.get(request)
            if (not pending or pending['peer'] != peer or pending['offer'] != offer
                    or pending['claimed'] or pending['deadline'] < time.monotonic()):
                return False
            pending['claimed'] = True
            return True

    def transfer(self, event):
        token = event.get('request')
        if token and event['direction'] == 'send' and event['status'] in {'error', 'cancelled', 'rejected'}:
            self.send(self.window.network.peer_session(event.get('peer')),
                      dict(type='file_error', request=token, message=event.get('detail', '文件传输未完成')[:160]))
            return
        if not token or event['direction'] != 'receive' or event['status'] not in {'complete', 'error', 'cancelled', 'rejected'}:
            return
        with self.lock:
            pending = self.pending.get(token)
            if not pending or pending['peer'] != event.get('peer') or pending['offer'] != event.get('offer'):
                return
            self.pending.pop(token)
        if event['status'] != 'complete':
            self.sync.status('文件粘贴未完成：' + event['detail'])
            return
        if not self.unchanged(pending):
            self.sync.status('文件已接收；窗口或操作已变化，可在传输记录中点「复制文件」再粘贴')
            return
        self.sync.copy_files(event['paths'])
        pending['sequence'] = self.sync.sequence()
        def paste():
            if self.unchanged(pending):
                self.backend.clipboard_shortcut('paste')
                self.sync.status('文件已送到目标窗口')
            else:
                self.sync.status('文件已复制到剪贴板，可在目标窗口手动粘贴')
        QTimer.singleShot(100, paste)

    def tick(self):
        now = time.monotonic()
        if self.local and (self.local['sequence'] != self.sync.sequence() or not self.allowed()):
            self.clear_local()
        if self.copy_wait:
            sequence, deadline, focus = self.copy_wait
            if focus != self.backend.focus_token() or now > deadline:
                self.copy_wait = None
            elif sequence != self.sync.sequence():
                self.copy_wait = None
                self.sync.send_current()
        with self.lock:
            for key in [k for k, p in self.pending.items() if p['deadline'] < now]:
                self.pending.pop(key)
            for key in [k for k, p in self.pending.items() if self.window.network.peer_session(p['peer']) is None]:
                self.pending.pop(key)
        enabled = (self.allowed() and self.engine.available and self.engine.state in {'local', 'sending', 'receiving'}
                   and not getattr(self.backend, 'shortcut_grab_error', False))
        self.backend.sharing_shortcuts_enabled = bool(enabled)
        ready = bool(enabled and self.choose_offer(native=True) and self.window.settings.get('native_file_paste', True))
        local_ready = ready and self.engine.state == 'local'
        remote_ready = (enabled and self.engine.state == 'sending' and self.window.settings.get('native_file_paste', True)
                        and self.engine.paste_ready.get(peer_id(self.engine.session), False))
        self.backend.native_file_paste_ready = bool(local_ready or remote_ready)
        if self.ready_sent != ready:
            self.ready_sent = ready
            for session in self.sessions():
                self.send(session, dict(type='paste_ready', ready=ready))

    def stop(self):
        self.timer.stop()
        self.clear_local()
        self.backend.native_file_paste_ready = self.backend.sharing_shortcuts_enabled = False
        with self.lock:
            self.pending.clear()
