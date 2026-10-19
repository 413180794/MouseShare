"""Input ownership: one physical source, many authenticated peers, explicit flow tokens."""
import collections
import threading
import time
import uuid

from .i18n import tr
from .displays import crossing, native, normalized, project
from .protocol import OPPOSITE
from .topology import layout_key, neighbor, validate_layout


def at_edge(side, x, y, bounds, margin=2):
    left, top, width, height = bounds
    return {'left': x <= left+margin, 'right': x >= left+width-1-margin,
            'top': y <= top+margin, 'bottom': y >= top+height-1-margin}[side]


def entry_point(edge, ratio, bounds, inset=8):
    x, y, width, height = bounds
    if edge in {'left', 'right'}:
        return (x+inset if edge == 'left' else x+width-1-inset, y+ratio*(height-1))
    return x+ratio*(width-1), y+inset if edge == 'top' else y+height-1-inset


def peer_id(session):
    return getattr(session, 'peer_id', '') if session else ''


def supports(session, feature):
    return feature in getattr(session, 'peer_features', []) if session else False


class Engine:
    def __init__(self, settings, notify=lambda state: None, clock=time.monotonic, *, local_id='', auxiliary=lambda e: None):
        self.settings, self.notify, self.clock = settings, notify, clock
        self.local_id, self.auxiliary = local_id, auxiliary
        self.backend = self.session = None
        self.sessions, self.availability, self.paste_ready = {}, {}, {}
        self.participants = set()
        self.flow = None
        self.controller = False
        self.state = 'local'
        self.peer_available = self.paused = self.system_blocked = False
        self.manual_game = settings.get('game_mode')
        self.auto_reason = self.error = ''
        self.edge_since = self.return_since = None
        self.cooldown = 0
        self.armed = True
        self.rearm_edge = settings.get('side')
        self.last_position = self.remote_position = (0, 0)
        self.incoming_edge = 'left'
        self.handoff_side, self.handoff_ratio = settings.get('side'), 0.5
        self.pending_since = self.entered_at = self.last_auto = 0
        self.pending_events = []
        self.last_status = None
        self.activity_counter = 0
        self.edge_target = None
        self.handoff_point = None
        self.last_screen = None
        self.last_tick = self.clock()
        self.handoff_attempts = self.handoff_timeouts = 0
        self.health_transitions = collections.deque(maxlen=32)
        self.events = collections.deque()
        self.condition = threading.Condition()
        self.stopped = False
        self.thread = None

    @property
    def game(self):
        return bool(self.manual_game or self.auto_reason)

    @property
    def available(self):
        return bool(self.backend and self.backend.ready() and not self.game and not self.paused and not self.system_blocked)

    def layout(self):
        value = self.settings.get('desktop_layout', {})
        return value if self.local_id and value.get('enabled') and self.local_id in value.get('nodes', {}) else None

    def enqueue(self, event):
        with self.condition:
            if self.stopped:
                return False
            if len(self.events) > 2048:
                self.events.clear()
                self.events.append({'type': 'command', 'action': 'panic'})
                self.condition.notify()
                return False
            if event.get('type') == 'move' and self.events and self.events[-1].get('type') == 'move':
                previous = self.events[-1]
                event = {**event, 'dx': previous['dx']+event['dx'], 'dy': previous['dy']+event['dy']}
                self.events[-1] = event
            else:
                self.events.append(event)
            self.condition.notify()
        return True

    def command(self, action, **extra):
        self.enqueue(dict(type='command', action=action, **extra))

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='input-owner')
        self.thread.start()

    def run(self):
        while not self.stopped:
            try:
                with self.condition:
                    if not self.events:
                        self.condition.wait(0.012)
                    batch = [self.events.popleft() for _ in range(min(128, len(self.events)))]
                for event in batch:
                    self.handle(event)
                self.tick()
            except Exception as exc:
                self.error = tr('共享已安全停止（{p0}），请重新检查权限', p0=type(exc).__name__)
                self.paused = True
                self.release(True)
                self.status()

    def send(self, message):
        if self.flow and message['type'] not in {'available', 'blocked'}:
            message = {**message, 'flow': self.flow}
        if self.session and self.session.send(message):
            return True
        if self.state != 'local':
            self.release(True)
        return False

    def announce(self):
        message = {'type': 'available' if self.available else 'blocked'}
        targets = list(self.sessions.values()) or ([self.session] if self.session else [])
        for session in targets:
            session.send(message)

    def broadcast(self, message, feature, exclude=None):
        for session in list(self.sessions.values()):
            if session is not exclude and supports(session, feature):
                session.send(message)

    def release(self, tell_peer=True, *, return_edge=None, return_ratio=None, return_point=None):
        prior, flow = self.state, self.flow
        targets = [self.sessions[k] for k in self.participants if k in self.sessions] if self.controller else []
        if self.session and self.session not in targets:
            targets.append(self.session)
        self.state = 'local'
        self.edge_since = self.return_since = None
        self.edge_target = None
        self.pending_events.clear()
        self.backend.capture(False)
        self.backend.cursor_hidden(False)
        try:
            self.backend.release_all()
        except OSError:
            self.error = tr('系统阻止了按键释放，请检查目标程序权限')
        self.cooldown, self.armed = self.clock()+0.8, False
        self.rearm_edge = (self.incoming_edge if prior in {'receiving', 'standby'} else
                           return_edge or self.handoff_side)
        if prior in {'sending', 'pending'}:
            edge = return_edge or self.handoff_side
            ratio = self.handoff_ratio if return_ratio is None else return_ratio
            point = return_point or (self.handoff_point if return_ratio is None else None)
            screen = self.backend.screen_info()
            self.backend.move(*(native(point, screen) if point else
                                 project(entry_point(edge, ratio, self.backend.bounds()), screen)))
        if tell_peer:
            for session in targets:
                message = {'type': 'release'}
                if flow and supports(session, 'multi-v1'):
                    message['flow'] = flow
                session.send(message)
        self.participants.clear()
        self.controller = False
        self.flow = None

    def apply_layout(self, value, session=None):
        value = validate_layout(value)
        if self.local_id not in value['nodes']:
            if session:
                return
            raise ValueError(tr('布局必须包含本机'))
        if session and (peer_id(session) not in value['nodes'] or layout_key(value) <= layout_key(
                self.settings.get('desktop_layout', {}))):
            return
        self.release(True)
        self.settings.set(desktop_layout=value)
        self.broadcast(dict(type='layout', layout=value), 'layout-v1', exclude=session)
        self.auxiliary(dict(type='layout_applied', layout=value))

    def handle(self, event):
        kind = event['type']
        if kind == 'command':
            self.handle_command(event)
        elif kind == 'connected':
            session = event['session']
            self.sessions[peer_id(session)] = session
            self.availability[peer_id(session)] = False
            if self.session is None:
                self.session = session
                self.peer_available = False
                self.armed = True
            self.announce()
            layout = self.layout()
            if layout and supports(session, 'layout-v1'):
                session.send(dict(type='layout', layout=layout))
            self.auxiliary(dict(type='peer_connected', session=session))
        elif kind == 'disconnected':
            session = event['session']
            key = peer_id(session)
            if self.session is session or key in self.participants:
                self.release(True)
            if self.sessions.get(key) is session:
                self.sessions.pop(key, None)
                self.availability.pop(key, None)
                self.paste_ready.pop(key, None)
            if self.session is session:
                self.session = next(iter(self.sessions.values()), None)
                self.peer_available = self.availability.get(peer_id(self.session), False)
        elif kind == 'network':
            session = event['session']
            if session in self.sessions.values() or session is self.session:
                self.receive(event['message'], session)
        else:
            self.physical(event)
        self.status()

    def handle_command(self, event):
        action = event['action']
        if action == 'game':
            self.manual_game = not self.manual_game
            self.settings.set(game_mode=self.manual_game)
            self.release(True)
            self.announce()
        elif action == 'pause':
            self.paused = not self.paused
            self.release(True)
            self.announce()
        elif action == 'panic':
            self.release(True)
        elif action == 'changed':
            self.release(True)
            self.announce()
        elif action == 'select_peer':
            if self.state == 'local' and event.get('peer') in self.sessions:
                self.session = self.sessions[event['peer']]
                self.peer_available = self.availability.get(event['peer'], False)
        elif action == 'switch_peer':
            if self.state != 'local':
                self.release(True)
            elif self.available:
                target = self.sessions.get(event.get('peer')) if event.get('peer') else self.session
                if target and self.availability.get(peer_id(target), self.peer_available):
                    for key in list(self.backend.keys):
                        self.backend.key(key, False)
                    self.handoff_side = self.settings.get('side')
                    self.handoff_ratio = 0.5
                    self.handoff_point = None
                    self.begin(target, self.handoff_side, 0.5)
        elif action == 'layout':
            self.apply_layout(event['layout'])
        elif action in {'share_copy', 'share_paste'} and self.available:
            operation = 'copy' if action == 'share_copy' else 'paste'
            if self.state == 'sending' and supports(self.session, 'file-offer-v1'):
                self.send(dict(type='clipboard_action', action=operation))
            elif self.state in {'local', 'receiving'}:
                self.auxiliary(dict(type='clipboard_action', action=operation, session=None))
        elif action == 'permissions':
            self.backend.start()
            self.error = self.backend.error
            self.announce()
        elif action == 'stop':
            self.release(True)
            self.stopped = True

    def activity(self, event):
        kind = event['type']
        if ((kind in {'move', 'scroll'} and (event.get('dx') or event.get('dy')))
                or kind == 'button' and event.get('down')
                or kind == 'key' and event.get('down') and event.get('key', 0) < 224):
            self.activity_counter += 1

    def edge_candidates(self, position, bounds):
        return [side for side in ('left', 'right', 'top', 'bottom') if at_edge(side, *position, bounds)]

    def edge_ratio(self, side, position, bounds):
        x, y = position
        left, top, width, height = bounds
        return max(0, min(1, (y-top)/max(1, height-1) if side in {'left', 'right'} else (x-left)/max(1, width-1)))

    def target_at(self, side, ratio):
        layout = self.layout()
        if not layout:
            return (peer_id(self.session), ratio) if side == self.settings.get('side') and self.session else None
        return neighbor(layout['nodes'], self.local_id, side, ratio)

    def screens(self):
        screens = {key: getattr(session, 'peer_screen', {}) or dict(w=1920, h=1080)
                   for key, session in self.sessions.items()}
        screens[self.local_id] = self.backend.screen_info()
        return screens

    def crossing(self, source, side, point):
        layout = self.layout()
        return crossing(layout['nodes'], self.screens(), source, side, point) if layout else None

    def physical(self, event):
        self.activity(event)
        kind = event['type']
        if self.state in {'receiving', 'standby'}:
            self.release(True)
            return
        if self.state in {'sending', 'pending'}:
            message = {k: v for k, v in event.items() if k not in {'x', 'y'}}
            if kind in {'move', 'scroll'}:
                limit = 8192 if kind == 'move' else 100
                for axis in ('dx', 'dy'):
                    message[axis] = max(-limit, min(limit, message[axis]))
            if self.state == 'pending':
                if kind == 'move':
                    return
                if len(self.pending_events) >= 256:
                    self.release(True)
                else:
                    self.pending_events.append(message)
            else:
                self.send(message)
            return
        if kind == 'move':
            self.last_position = event['x'], event['y']
            bounds = self.backend.monitor_at(self.last_position) if self.layout() else self.backend.bounds()
            screen = self.backend.screen_info()
            if not at_edge(self.rearm_edge, *self.last_position, bounds, margin=24):
                self.armed = True
            candidates = []
            for side in self.edge_candidates(self.last_position, bounds):
                ratio = self.edge_ratio(side, self.last_position, self.backend.bounds())
                point = normalized(self.last_position, screen)
                mapped = self.crossing(self.local_id, side, point)
                target = mapped[:2] if mapped else (self.target_at(side, ratio) if not self.layout() else None)
                if target:
                    key, target_ratio = target
                    available = self.availability.get(key, self.peer_available if key == peer_id(self.session) else False)
                    if available:
                        candidates.append((key, side, ratio, target_ratio, mapped[2] if mapped else None, point))
            target = candidates[0] if len(candidates) == 1 else None
            if target and self.armed and self.available:
                if self.edge_since is None or self.edge_target is None or self.edge_target[:2] != target[:2]:
                    self.edge_since = self.clock()
                self.edge_target = target
            else:
                self.edge_since, self.edge_target = None, None
        elif kind in {'key', 'button'}:
            self.edge_since = None

    def begin(self, session, side, ratio, *, keep_capture=False, point=None):
        self.handoff_attempts += 1
        if not keep_capture:
            self.flow = uuid.uuid4().hex if supports(session, 'multi-v1') else None
            self.controller = True
            self.participants = {peer_id(session)}
            self.backend.capture(True)
        self.session = session
        self.peer_available = self.availability.get(peer_id(session), self.peer_available)
        self.state, self.pending_since = 'pending', self.clock()
        self.pending_events.clear()
        self.edge_since = None
        layout = self.layout()
        if layout and supports(session, 'layout-v1'):
            session.send(dict(type='layout', layout=layout))
        message = dict(type='enter', edge=side, position=ratio)
        if point and supports(session, 'monitors-v1'):
            message['point'] = point
        self.send(message)

    def tick(self):
        now = self.clock()
        self.last_tick = now
        if now-self.last_auto > 0.5:
            self.last_auto = now
            if self.state == 'local' and (self.backend.keys or self.backend.buttons):
                self.backend.reconcile_physical()
            screen = self.backend.screen_info()
            if screen != self.last_screen:
                if self.last_screen is not None:
                    self.release(True)
                self.last_screen = screen
                self.broadcast(dict(type='screen', screen=screen), 'monitors-v1')
                self.auxiliary(dict(type='screens_changed'))
            blocked = not self.backend.desktop_active()
            if blocked != self.system_blocked:
                self.system_blocked = blocked
                self.release(True)
                self.announce()
            process, fullscreen = self.backend.foreground()
            games = {name.casefold() for name in self.settings.get('game_processes')}
            reason = tr('游戏进程：{p0}', p0=process) if process.casefold() in games else (
                tr('前台全屏窗口') if fullscreen and self.settings.get('auto_fullscreen') else '')
            if reason != self.auto_reason:
                before = self.game
                self.auto_reason = reason
                if before != self.game:
                    self.release(True)
                    self.announce()
        if self.state == 'pending' and now-self.pending_since > 1.5:
            self.handoff_timeouts += 1
            self.release(True)
        if (self.state == 'local' and self.edge_since is not None and self.edge_target
                and now-self.edge_since >= self.settings.get('dwell_ms')/1000 and now >= self.cooldown
                and self.available and not self.backend.keys and not self.backend.buttons):
            key, side, source_ratio, target_ratio, target_point, source_point = self.edge_target
            session = self.sessions.get(key) or (self.session if key == peer_id(self.session) else None)
            if session:
                self.handoff_side, self.handoff_ratio = side, source_ratio
                screen = self.backend.screen_info()
                monitor = self.backend.monitor_at(self.last_position)
                self.handoff_point = (normalized(entry_point(side, self.edge_ratio(side, self.last_position, monitor),
                                                            monitor), screen) if len(screen['monitors']) > 1 else None)
                self.begin(session, side, target_ratio, point=target_point)
        self.status()

    def health(self):
        """Local operational state, without key values, pointer paths or device IDs."""
        now = self.clock()
        if self.state != 'local':
            blocker = self.state
        elif not self.available:
            blocker = 'local-blocked'
        elif not self.session:
            blocker = 'disconnected'
        elif not self.armed:
            blocker = 'move-inward'
        elif self.backend.keys or self.backend.buttons:
            blocker = 'held-input'
        elif now < self.cooldown:
            blocker = 'cooldown'
        elif self.edge_target and self.edge_since is None:
            blocker = 'dwell-interrupted'
        elif self.edge_since is not None:
            blocker = 'edge-dwell'
        elif not self.peer_available and not any(self.availability.values()):
            blocker = 'peer-blocked'
        else:
            blocker = 'away-from-connected-edge'
        return dict(blocker=blocker, engine_age_ms=round(max(0, now-self.last_tick)*1000),
                    physical_keys=len(self.backend.keys), physical_buttons=len(self.backend.buttons),
                    injected_keys=len(self.backend.injected_keys), injected_buttons=len(self.backend.injected_buttons),
                    attempts=self.handoff_attempts, timeouts=self.handoff_timeouts,
                    recovered_releases=self.backend.recovered_releases,
                    tap_interruptions=getattr(self.backend, 'tap_interruptions', 0))

    def flow_matches(self, message, session):
        return not supports(session, 'multi-v1') or bool(self.flow and message.get('flow') == self.flow)

    def receive(self, message, session=None):
        session = session or self.session
        kind, key = message['type'], peer_id(session)
        if kind == 'screen' and supports(session, 'monitors-v1'):
            from .displays import validate_screen
            screen = validate_screen(message.get('screen'))
            if screen and screen != getattr(session, 'peer_screen', {}):
                if self.state != 'local':
                    self.release(True)
                session.peer_screen = screen
                self.auxiliary(dict(type='screens_changed'))
            return
        if kind in {'available', 'blocked'}:
            self.availability[key] = kind == 'available'
            if session is self.session:
                self.peer_available = kind == 'available'
            if kind == 'blocked' and (session is self.session or key in self.participants):
                self.release(True)
            return
        if kind == 'paste_ready':
            self.paste_ready[key] = message['ready']
            return
        if kind == 'layout':
            self.apply_layout(message['layout'], session)
            return
        if kind in {'file_offer', 'file_clear', 'file_request', 'file_error'}:
            self.auxiliary(dict(type='control_message', session=session, message=message))
            return
        if kind == 'enter':
            if self.state == 'standby' and session is self.session and self.flow_matches(message, session):
                self.backend.cursor_hidden(False)
                self.state = 'local'
            if not self.available or self.backend.keys or self.backend.buttons or self.state != 'local':
                reply = {'type': 'release'}
                if message.get('flow'):
                    reply['flow'] = message['flow']
                session.send(reply)
                if session is self.session and self.state == 'pending' and not self.flow:
                    self.release(True)
                return
            if supports(session, 'multi-v1') and not message.get('flow'):
                return
            self.session, self.flow = session, message.get('flow') if supports(session, 'multi-v1') else None
            self.peer_available = self.availability.get(key, False)
            self.controller = False
            self.incoming_edge = OPPOSITE[message['edge']]
            screen = self.backend.screen_info()
            self.remote_position = (native(message['point'], screen) if message.get('point')
                                    and supports(session, 'monitors-v1') else
                                    project(entry_point(self.incoming_edge, message['position'], self.backend.bounds()), screen))
            self.backend.move(*self.remote_position)
            self.state, self.entered_at, self.return_since = 'receiving', self.clock(), None
            self.send({'type': 'entered'})
            return
        active = session is self.session or self.controller and key in self.participants
        if not active or not self.flow_matches(message, session):
            return
        if kind in {'release', 'return'}:
            ratio = message.get('position') if kind == 'return' else None
            layout = self.layout()
            if ratio is not None and self.controller and layout and not self.flow:
                mapped = neighbor(layout['nodes'], key, OPPOSITE[self.handoff_side], ratio)
                ratio = mapped[1] if mapped and mapped[0] == self.local_id else self.handoff_ratio
            self.release(self.controller, return_ratio=ratio)
        elif kind == 'standby' and self.state == 'receiving':
            self.backend.release_all()
            self.state = 'standby'
            self.backend.cursor_hidden(True)
        elif kind == 'route':
            self.route(message, session)
        elif kind == 'clipboard_action' and self.state == 'receiving':
            self.backend.release_all()
            self.auxiliary(dict(type='clipboard_action', action=message['action'], session=session, flow=self.flow))
        elif kind == 'entered':
            if self.state == 'pending' and self.available:
                self.state = 'sending'
                buffered, self.pending_events = self.pending_events, []
                for event in buffered:
                    self.send(event)
            else:
                self.send({'type': 'release'})
        elif self.state == 'receiving' and self.available:
            self.activity(message)
            if kind == 'move':
                self.remote_move(message['dx'], message['dy'])
            elif kind == 'key':
                code = message['key']
                if self.settings.get('swap_ctrl_meta', False):
                    code = {224: 227, 227: 224, 228: 231, 231: 228}.get(code, code)
                self.backend.key(code, message['down'])
            elif kind == 'button':
                self.backend.button(message['button'], message['down'])
            elif kind == 'scroll':
                self.backend.scroll(message['dx'], message['dy'])

    def route(self, message, session):
        layout = self.layout()
        if not self.controller or self.state != 'sending' or session is not self.session or not layout:
            return
        mapped = self.crossing(peer_id(session), message['edge'], message['point']) if message.get('point') else None
        target = mapped[:2] if mapped else neighbor(layout['nodes'], peer_id(session), message['edge'], message['position'])
        if message.get('point') and not mapped:
            return
        if not target or target[0] != message['target']:
            return
        key, ratio = target
        if key == self.local_id:
            self.release(True, return_edge=OPPOSITE[message['edge']], return_ratio=ratio,
                         return_point=mapped[2] if mapped else None)
            return
        destination = self.sessions.get(key)
        if not destination or not supports(destination, 'multi-v1') or not self.availability.get(key):
            return
        self.send({'type': 'standby'})
        self.participants.add(key)
        self.begin(destination, message['edge'], ratio, keep_capture=True, point=mapped[2] if mapped else None)

    def remote_move(self, dx, dy):
        speed = self.settings.get('sensitivity')
        x, y = self.remote_position
        screen = self.backend.screen_info()
        x, y = project((x+dx*speed, y+dy*speed), screen)
        bounds = self.backend.monitor_at((x, y)) if self.layout() else self.backend.bounds()
        self.remote_position = x, y
        self.backend.move(x, y)
        layout = self.layout()
        candidates = []
        for side in self.edge_candidates((x, y), bounds):
            outward = {'left': dx < 0, 'right': dx > 0, 'top': dy < 0, 'bottom': dy > 0}[side]
            ratio = self.edge_ratio(side, (x, y), self.backend.bounds())
            mapped = self.crossing(self.local_id, side, normalized((x, y), screen))
            target = mapped[:2] if mapped else None
            if outward and (target if layout else side == self.incoming_edge):
                candidates.append((side, ratio, target))
        if (len(candidates) == 1 and self.clock()-self.entered_at > 0.4
                and not self.backend.injected_keys and not self.backend.injected_buttons):
            self.return_since = self.return_since if self.return_since is not None else self.clock()
            if self.clock()-self.return_since > 0.08:
                side, ratio, target = candidates[0]
                if layout and self.flow:
                    message = dict(type='route', edge=side, position=ratio, target=target[0])
                    if supports(self.session, 'monitors-v1'):
                        message['point'] = normalized((x, y), screen)
                    self.send(message)
                    self.return_since = self.clock()+0.7
                elif side == self.incoming_edge:
                    self.send(dict(type='return', position=ratio))
                    self.release(False)
        else:
            self.return_since = None

    def status(self):
        health = self.health()
        if not self.health_transitions or self.health_transitions[-1]['blocker'] != health['blocker']:
            self.health_transitions.append(dict(blocker=health['blocker'], at=round(self.clock(), 3)))
        self.backend.switch_shortcut_enabled = bool(self.available and (self.peer_available or any(self.availability.values())))
        state = dict(state=self.state, game=self.game, manual_game=self.manual_game, auto_reason=self.auto_reason,
                     paused=self.paused, system_blocked=self.system_blocked,
                     connected=bool(self.session), peer_name=self.session.peer_name if self.session else '',
                     peer_available=self.peer_available, ready=bool(self.backend and self.backend.ready()),
                     error=self.error or (self.backend.error if self.backend else ''), active_peer=peer_id(self.session),
                     peers=len(self.sessions), native_paste_ready=self.paste_ready.get(peer_id(self.session), False))
        if state != self.last_status:
            self.last_status = state
            self.notify(state)

    def stop(self):
        self.command('stop')
        if self.thread:
            self.thread.join(2)
        self.backend.stop()
