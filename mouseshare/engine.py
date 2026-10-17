"""Single-threaded ownership state machine; native callbacks enqueue and return immediately."""
import collections
import threading
import time

from .protocol import OPPOSITE


def at_edge(side, x, y, bounds, margin=2):
    left, top, width, height = bounds
    return {"left": x <= left + margin, "right": x >= left + width - 1 - margin,
            "top": y <= top + margin, "bottom": y >= top + height - 1 - margin}[side]


def entry_point(edge, ratio, bounds, inset=8):
    x, y, width, height = bounds
    if edge in ("left", "right"):
        return (x + inset if edge == "left" else x + width - 1 - inset,
                y + ratio * (height - 1))
    return x + ratio * (width - 1), y + inset if edge == "top" else y + height - 1 - inset


class Engine:
    def __init__(self, settings, notify=lambda state: None, clock=time.monotonic):
        self.settings, self.notify, self.clock = settings, notify, clock
        self.backend = None
        self.session = None
        self.state = "local"
        self.peer_available = False
        self.paused = False
        self.manual_game = settings.get("game_mode")
        self.auto_reason = ""
        self.system_blocked = False
        self.error = ""
        self.edge_since = None
        self.return_since = None
        self.cooldown = 0
        self.armed = True
        self.last_position = (0, 0)
        self.remote_position = (0, 0)
        self.incoming_edge = "left"
        self.handoff_side = settings.get("side")
        self.handoff_ratio = 0.5
        self.pending_since = 0
        self.pending_events = []
        self.entered_at = 0
        self.last_auto = 0
        self.last_status = None
        self.events = collections.deque()
        self.condition = threading.Condition()
        self.stopped = False
        self.thread = None

    @property
    def game(self):
        return bool(self.manual_game or self.auto_reason)

    @property
    def available(self):
        return bool(self.backend and self.backend.ready() and not self.game
                    and not self.paused and not self.system_blocked)

    def enqueue(self, event):
        with self.condition:
            if self.stopped:
                return False
            if len(self.events) > 2048:
                self.events.clear()
                self.events.append({"type": "command", "action": "panic"})
                self.condition.notify()
                return False
            # Coalesce only adjacent physical moves. Button/key ordering is preserved.
            if (event.get("type") == "move" and self.events
                    and self.events[-1].get("type") == "move"):
                previous = self.events[-1]
                event = {**event, "dx": previous["dx"] + event["dx"], "dy": previous["dy"] + event["dy"]}
                self.events[-1] = event
            else:
                self.events.append(event)
            self.condition.notify()
        return True

    def command(self, action, **extra):
        self.enqueue({"type": "command", "action": action, **extra})

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="input-owner")
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
                self.error = f"共享已安全停止（{type(exc).__name__}），请重新检查权限"
                self.paused = True
                self.release(True)
                self.status()

    def send(self, message):
        if self.session and self.session.send(message):
            return True
        if self.state != "local":
            self.release(False)
        return False

    def announce(self):
        self.send({"type": "available" if self.available else "blocked"})

    def release(self, tell_peer=True):
        prior = self.state
        self.state = "local"
        self.edge_since = self.return_since = None
        self.pending_events.clear()
        self.backend.capture(False)
        try:
            self.backend.release_all()
        except OSError:
            self.error = "系统阻止了按键释放，请检查目标程序权限"
        self.cooldown = self.clock() + 0.8
        self.armed = False
        if prior in {"sending", "pending"}:
            self.backend.move(*entry_point(self.handoff_side, self.handoff_ratio, self.backend.bounds()))
        if tell_peer and self.session:
            self.session.send({"type": "release"})

    def handle(self, event):
        kind = event["type"]
        if kind == "command":
            self.handle_command(event)
            self.status()
            return
        if kind == "connected":
            self.release(False)
            self.session = event["session"]
            self.peer_available = False
            self.armed = True
            self.announce()
        elif kind == "disconnected":
            if self.session is event["session"]:
                self.release(False)
                self.session = None
                self.peer_available = False
        elif kind == "network":
            if self.session is event["session"]:
                self.receive(event["message"])
        else:
            self.physical(event)
        self.status()

    def handle_command(self, event):
        action = event["action"]
        if action == "game":
            self.manual_game = not self.manual_game
            self.settings.set(game_mode=self.manual_game)
            self.release(True)
            self.announce()
        elif action == "pause":
            self.paused = not self.paused
            self.release(True)
            self.announce()
        elif action == "panic":
            self.release(True)
        elif action == "changed":
            self.release(True)
            self.announce()
        elif action == "permissions":
            self.backend.start()
            self.error = self.backend.error
            self.announce()
        elif action == "stop":
            self.release(True)
            self.stopped = True

    def physical(self, event):
        kind = event["type"]
        if self.state == "receiving":
            # Physical activity on the destination immediately returns ownership.
            self.release(True)
            return
        if self.state in {"sending", "pending"}:
            message = {k: v for k, v in event.items() if k not in {"x", "y"}}
            if kind in {"move", "scroll"}:
                limit = 8192 if kind == "move" else 100
                for axis in ("dx", "dy"):
                    message[axis] = max(-limit, min(limit, message[axis]))
            if self.state == "pending":
                # The destination has been placed at its entry edge but has not
                # acknowledged ownership yet. Replaying this motion burst after
                # the ACK can skip the edge on the destination's first frame.
                if kind == "move":
                    return
                if len(self.pending_events) >= 256:
                    self.release(True)
                else:
                    self.pending_events.append(message)
            else:
                self.send(message)
            return
        if kind == "move":
            self.last_position = event["x"], event["y"]
            edge = at_edge(self.settings.get("side"), *self.last_position, self.backend.bounds())
            if not at_edge(self.settings.get("side"), *self.last_position, self.backend.bounds(), margin=24):
                self.armed = True
            if edge and self.armed and self.available and self.peer_available and self.session:
                self.edge_since = self.edge_since if self.edge_since is not None else self.clock()
            else:
                self.edge_since = None
        elif kind in {"key", "button"}:
            self.edge_since = None

    def tick(self):
        now = self.clock()
        if now - self.last_auto > 0.5:
            self.last_auto = now
            blocked = not self.backend.desktop_active()
            if blocked != self.system_blocked:
                self.system_blocked = blocked
                self.release(True)
                self.announce()
            process, fullscreen = self.backend.foreground()
            games = {name.casefold() for name in self.settings.get("game_processes")}
            reason = (f"游戏进程：{process}" if process.casefold() in games else
                      "前台全屏窗口" if fullscreen and self.settings.get("auto_fullscreen") else "")
            if reason != self.auto_reason:
                before = self.game
                self.auto_reason = reason
                if before != self.game:
                    self.release(True)
                    self.announce()
        if self.state == "pending" and now - self.pending_since > 1.5:
            self.release(True)
        if (self.state == "local" and self.edge_since is not None
                and now - self.edge_since >= self.settings.get("dwell_ms") / 1000
                and now >= self.cooldown and self.available and self.peer_available
                and not self.backend.keys and not self.backend.buttons):
            x, y = self.last_position
            left, top, width, height = self.backend.bounds()
            side = self.settings.get("side")
            ratio = (y - top) / max(1, height - 1) if side in {"left", "right"} else (x - left) / max(1, width - 1)
            self.state = "pending"
            self.handoff_side = side
            self.handoff_ratio = max(0, min(1, ratio))
            self.pending_since = now
            self.edge_since = None
            self.backend.capture(True)
            self.send({"type": "enter", "edge": side, "position": self.handoff_ratio})
        self.status()

    def receive(self, message):
        kind = message["type"]
        if kind == "blocked":
            self.peer_available = False
            self.release(False)
        elif kind == "available":
            self.peer_available = True
        elif kind in {"release", "return"}:
            if kind == "return" and self.state == "sending":
                self.handoff_ratio = message.get("position", self.handoff_ratio)
            self.release(False)
        elif kind == "enter":
            if not self.available or self.backend.keys or self.backend.buttons:
                self.send({"type": "release"})
                return
            if self.state != "local":
                # Two simultaneous offers return to local on both sides, avoiding dual capture.
                self.release(True)
                return
            self.incoming_edge = OPPOSITE[message["edge"]]
            self.remote_position = entry_point(self.incoming_edge, message["position"], self.backend.bounds())
            self.backend.move(*self.remote_position)
            self.state = "receiving"
            self.entered_at = self.clock()
            self.return_since = None
            self.send({"type": "entered"})
        elif kind == "entered":
            if self.state == "pending" and self.available:
                self.state = "sending"
                buffered, self.pending_events = self.pending_events, []
                for event in buffered:
                    self.send(event)
            else:
                self.send({"type": "release"})
        elif self.state == "receiving" and self.available:
            if kind == "move":
                self.remote_move(message["dx"], message["dy"])
            elif kind == "key":
                key = message["key"]
                if self.settings.get("swap_ctrl_meta", False):
                    key = {224: 227, 227: 224, 228: 231, 231: 228}.get(key, key)
                self.backend.key(key, message["down"])
            elif kind == "button":
                self.backend.button(message["button"], message["down"])
            elif kind == "scroll":
                self.backend.scroll(message["dx"], message["dy"])

    def remote_move(self, dx, dy):
        speed = self.settings.get("sensitivity")
        x, y = self.remote_position
        left, top, width, height = self.backend.bounds()
        x = max(left, min(left + width - 1, x + dx * speed))
        y = max(top, min(top + height - 1, y + dy * speed))
        self.remote_position = (x, y)
        self.backend.move(x, y)
        outward = {"left": dx < 0, "right": dx > 0, "top": dy < 0, "bottom": dy > 0}[self.incoming_edge]
        if (outward and at_edge(self.incoming_edge, x, y, self.backend.bounds())
                and self.clock() - self.entered_at > 0.4
                and not self.backend.injected_keys and not self.backend.injected_buttons):
            self.return_since = self.return_since if self.return_since is not None else self.clock()
            if self.clock() - self.return_since > 0.08:
                ratio = ((y - top) / max(1, height - 1) if self.incoming_edge in {"left", "right"}
                         else (x - left) / max(1, width - 1))
                self.send({"type": "return", "position": ratio})
                self.release(False)
        else:
            self.return_since = None

    def status(self):
        state = {"state": self.state, "game": self.game, "manual_game": self.manual_game,
                 "auto_reason": self.auto_reason, "paused": self.paused,
                 "system_blocked": self.system_blocked,
                 "connected": bool(self.session), "peer_name": self.session.peer_name if self.session else "",
                 "peer_available": self.peer_available,
                 "ready": bool(self.backend and self.backend.ready()),
                 "error": self.error or (self.backend.error if self.backend else "")}
        if state != self.last_status:
            self.last_status = state
            self.notify(state)

    def stop(self):
        self.command("stop")
        if self.thread:
            self.thread.join(2)
        self.backend.stop()

