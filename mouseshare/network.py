"""LAN discovery and authenticated TLS sessions, independent of the GUI and input hooks."""
import hashlib
import json
import platform
import queue
import select
import socket
import struct
import threading
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from .i18n import tr
from .protocol import (
    DISCOVERY_PORT,
    INPUT_PORT,
    MAX_FRAME,
    MULTICAST_GROUP,
    VERSION,
    Decoder,
    ProtocolError,
    decode,
    frame,
    valid_input,
)
from .security import check_hello, pairing_code, transcript, unb64


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data.extend(chunk)
    return bytes(data)


def recv_frame(sock):
    size = struct.unpack("!I", recv_exact(sock, 4))[0]
    if not 0 < size <= MAX_FRAME:
        raise ProtocolError("Invalid frame size")
    return decode(recv_exact(sock, size))


class Discovery:
    def __init__(self, identity, settings, on_peer, on_error=lambda message: None, port=INPUT_PORT):
        self.identity, self.settings = identity, settings
        self.on_peer, self.on_error, self.port = on_peer, on_error, port
        self.stop_event = threading.Event()
        self.sock = None

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="discovery").start()

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock = sock
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if platform.system() != "Windows" and hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.bind(("", DISCOVERY_PORT))
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0"))
            except OSError:
                self.on_error(tr('组播不可用，正在使用广播发现；也可以手动输入 IP'))
            sock.settimeout(0.4)
            next_send = 0
            seen = {}
            while not self.stop_event.is_set():
                if time.monotonic() >= next_send:
                    payload = json.dumps({"app": "MouseShare", "v": VERSION, "id": self.identity.id,
                                          "name": self.settings.get("name")[:80], "port": self.port,
                                          "os": platform.system()}).encode()
                    for host in ("255.255.255.255", MULTICAST_GROUP):
                        try:
                            sock.sendto(payload, (host, DISCOVERY_PORT))
                        except OSError:
                            pass
                    next_send = time.monotonic() + 2
                try:
                    raw, address = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                try:
                    peer = json.loads(raw)
                    peer_id = peer.get("id", "")
                    if (peer.get("app") != "MouseShare" or peer.get("v") != VERSION
                            or not isinstance(peer_id, str) or len(peer_id) != 64
                            or any(c not in "0123456789abcdef" for c in peer_id)
                            or peer_id == self.identity.id
                            or type(peer.get("port")) is not int or not 1024 <= peer["port"] <= 65535
                            or not isinstance(peer.get("name"), str) or not 1 <= len(peer["name"]) <= 80):
                        continue
                    if time.monotonic() - seen.get(peer_id, 0) < 1:
                        continue
                    if len(seen) >= 256:
                        seen.clear()
                    seen[peer_id] = time.monotonic()
                    peer["host"] = address[0]
                    self.on_peer(peer)
                except (ValueError, AttributeError, TypeError):
                    continue
        except OSError:
            if not self.stop_event.is_set():
                self.on_error(tr('自动发现端口不可用；请检查防火墙或使用手动 IP 连接'))
        finally:
            if self.sock:
                self.sock.close()

    def stop(self):
        self.stop_event.set()


class Session:
    def __init__(self, owner, raw, server, expected_id=None, lane="input", work=None):
        self.owner, self.raw, self.server, self.expected_id = owner, raw, server, expected_id
        self.peer_id, self.peer_name, self.code = "", "", ""
        self.approval = threading.Event()
        self.accepted = False
        self.stopped = threading.Event()
        self.outgoing = queue.Queue(maxsize=2048)
        self.sock = None
        self.connected = False
        self.lane, self.work = lane, work
        self.peer_features, self.peer_port = [], INPUT_PORT
        self.peer_screen, self.control_session = {}, None
        self.wake_read = self.wake_write = None

    def approve(self, accepted):
        self.accepted = accepted
        self.approval.set()
        if not accepted:
            self.stop()

    def send(self, message):
        if self.stopped.is_set() or not self.connected:
            return False
        try:
            self.outgoing.put_nowait(message)
            if self.wake_write:
                try:
                    self.wake_write.send(b'\0')
                except (BlockingIOError, OSError):
                    pass  # A full wakeup socket already makes the selector ready.
            return True
        except queue.Full:
            self.stop()
            return False

    def stop(self):
        self.stopped.set()
        self.approval.set()
        # Wake blocking reads, including a pairing attempt still awaiting confirmation.
        try:
            (self.sock or self.raw).shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def authenticate(self):
        local = self.owner.identity.hello(self.owner.settings.get("name"))
        local.update(features=["sharing-v1", "multi-v1", "layout-v1", "file-offer-v1", "monitors-v1"],
                     port=self.owner.port, screen=self.owner.screen_provider())
        # Commit before revealing either random nonce. This prevents a middleman
        # choosing its nonce after seeing the other side's SAS input.
        commitment = hashlib.sha256(frame(local)).hexdigest()
        self.sock.sendall(frame({"type": "commit", "hash": commitment, "lane": self.lane}))
        remote_commit = recv_frame(self.sock)
        if remote_commit.get("type") != "commit":
            raise ProtocolError("Missing pairing commitment")
        remote_lane = remote_commit.get("lane", "input")
        if remote_lane not in {"input", "data"}:
            raise ProtocolError("Unknown channel")
        if self.server:
            self.lane = remote_lane
        self.sock.sendall(frame(local))
        remote = recv_frame(self.sock)
        if hashlib.sha256(frame(remote)).hexdigest() != remote_commit.get("hash"):
            raise ProtocolError("Pairing commitment mismatch")
        remote_der, remote_cert, remote_nonce = check_hello(remote)
        self.peer_id, self.peer_name = remote["id"], remote["name"]
        self.peer_screen = remote.get("screen", {})
        from .displays import validate_screen
        self.peer_screen = validate_screen(self.peer_screen)
        self.peer_features = remote.get("features", []) if isinstance(remote.get("features"), list) else []
        self.peer_port = remote.get("port", INPUT_PORT)
        if type(self.peer_port) is not int or not 1 <= self.peer_port <= 65535:
            raise ProtocolError("Invalid peer port")
        if self.peer_id == self.owner.identity.id:
            raise ProtocolError("Cannot connect to this device")
        if self.expected_id and self.peer_id != self.expected_id:
            raise ProtocolError("Discovered device identity changed")
        local_nonce = unb64(local["nonce"])
        if self.server:
            proof = transcript(self.owner.identity.der, remote_der, local_nonce, remote_nonce)
        else:
            if hashlib.sha256(self.sock.getpeercert(binary_form=True)).digest() != hashlib.sha256(remote_der).digest():
                raise ProtocolError("TLS identity mismatch")
            proof = transcript(remote_der, self.owner.identity.der, remote_nonce, local_nonce)
        self.sock.sendall(frame({"type": "proof", "signature": self.owner.identity.sign(proof)}))
        signed = recv_frame(self.sock)
        if signed.get("type") != "proof":
            raise ProtocolError("Missing identity proof")
        remote_cert.public_key().verify(unb64(signed.get("signature")), proof, ec.ECDSA(hashes.SHA256()))
        self.code = pairing_code(proof)
        if self.lane == "input":
            self.owner.claim_input(self)
        trusted = self.peer_id in self.owner.settings.get("peers")
        if self.lane == "data":
            control = self.owner.peer_session(self.peer_id)
            if (not trusted or not control or not control.connected
                    or control.peer_id != self.peer_id or "sharing-v1" not in control.peer_features):
                raise ProtocolError("Data channel requires active paired connection")
            self.control_session = control
        remote_confirmation = None
        if trusted:
            self.accepted = True
        else:
            self.owner.on_pair(self)
            deadline = time.monotonic() + 120
            while not self.approval.wait(0.2):
                if self.stopped.is_set() or self.owner.stopped.is_set() or time.monotonic() > deadline:
                    raise TimeoutError("Pairing expired")
                if remote_confirmation is None and (self.sock.pending()
                        or select.select([self.sock], [], [], 0)[0]):
                    remote_confirmation = recv_frame(self.sock)
                    if (remote_confirmation.get("type") != "confirm"
                            or remote_confirmation.get("accepted") is not True):
                        raise ProtocolError("Pairing declined")
        if self.stopped.is_set():
            raise ConnectionError("Pairing cancelled")
        self.sock.settimeout(125)
        self.sock.sendall(frame({"type": "confirm", "accepted": self.accepted}))
        confirmation = remote_confirmation or recv_frame(self.sock)
        if confirmation.get("type") != "confirm" or confirmation.get("accepted") is not True or not self.accepted:
            raise ProtocolError("Pairing declined")
        if self.lane == "input":
            self.owner.settings.trust(self.peer_id, self.peer_name, self.sock.getpeername()[0])

    def run(self):
        error = tr('连接已结束')
        try:
            self.raw.settimeout(6)
            self.raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            context = self.owner.identity.context(self.server)
            self.sock = context.wrap_socket(self.raw, server_side=self.server,
                                            server_hostname=None if self.server else "MouseShare")
            self.authenticate()
            if self.lane == "data":
                self.sock.settimeout(120)
                self.connected = True
                (self.work or self.owner.on_data)(self)
                self.work_finished = True
                return
            self.sock.settimeout(0.5)
            self.wake_read, self.wake_write = socket.socketpair()
            for wake in (self.wake_read, self.wake_write):
                if wake.family in {socket.AF_INET, socket.AF_INET6}:
                    wake.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.wake_read.setblocking(False)
            self.wake_write.setblocking(False)
            self.connected = True
            self.owner.on_connected(self)
            parser = Decoder()
            last_rx = last_ping = time.monotonic()
            while not self.stopped.is_set() and not self.owner.stopped.is_set():
                now = time.monotonic()
                if now - last_rx > 3.5:
                    raise TimeoutError("Heartbeat timed out")
                if now - last_ping >= 0.7:
                    self.sock.sendall(frame({"type": "ping"}))
                    last_ping = now
                for _ in range(64):
                    try:
                        message = self.outgoing.get_nowait()
                    except queue.Empty:
                        break
                    self.sock.sendall(frame(message))
                if not self.sock.pending():
                    ready = select.select([self.sock, self.wake_read], [], [],
                                          0 if not self.outgoing.empty() else 0.05)[0]
                    if self.wake_read in ready:
                        try:
                            self.wake_read.recv(4096)
                        except BlockingIOError:
                            pass
                    if self.sock not in ready:
                        continue
                raw = self.sock.recv(32768)
                if not raw:
                    raise ConnectionError("Peer disconnected")
                for message in parser.feed(raw):
                    if not valid_input(message):
                        raise ProtocolError("Invalid input message")
                    last_rx = time.monotonic()
                    if message["type"] == "ping":
                        self.sock.sendall(frame({"type": "pong"}))
                    elif message["type"] != "pong":
                        self.owner.on_message(self, message)
        except Exception as exc:
            # Exception class is enough for diagnostics; packet and key contents stay private.
            error = tr('连接已断开（{p0}）', p0=type(exc).__name__)
        finally:
            self.connected = False
            self.stopped.set()
            for wake in (self.wake_read, self.wake_write):
                if wake:
                    wake.close()
            if self.sock:
                self.sock.close()
            else:
                self.raw.close()
            if self.lane == "input":
                self.owner.finished(self, error)
            self.owner.channel_finished(self)


class Network:
    def __init__(self, identity, settings, on_pair, on_connected, on_message, on_disconnected,
                 on_error=lambda message: None, port=INPUT_PORT, bind_host=""):
        self.identity, self.settings = identity, settings
        self.on_pair, self.on_connected, self.on_message = on_pair, on_connected, on_message
        self.on_disconnected, self.on_error = on_disconnected, on_error
        self.port, self.bind_host = port, bind_host
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.session = None
        self.sessions = {}
        self.screen_provider = lambda: {"w": 1920, "h": 1080}
        self.listener = None
        self.dialing = set()
        self.on_data = lambda session: None
        self.channels = set()

    def start(self):
        # Bind synchronously so a firewall/port failure is visible before advertising.
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if platform.system() == "Windows":
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((self.bind_host, self.port))
        self.port = self.listener.getsockname()[1]
        self.listener.listen(4)
        self.listener.settimeout(0.5)
        threading.Thread(target=self.listen, daemon=True, name="TLS-listener").start()

    def listen(self):
        while not self.stopped.is_set():
            try:
                raw, _ = self.listener.accept()
                self.adopt(raw, True)
            except socket.timeout:
                continue
            except OSError:
                break

    def adopt(self, raw, server, expected_id=None):
        with self.lock:
            if self.stopped.is_set() or len(self.channels) >= 32:
                raw.close()
                return
            session = Session(self, raw, server, expected_id)
            self.channels.add(session)
        threading.Thread(target=session.run, daemon=True, name="TLS-session").start()

    def peer_session(self, peer_id):
        return self.sessions.get(peer_id)

    def claim_input(self, session):
        with self.lock:
            current = self.sessions.get(session.peer_id)
            if current is not None and current is not session and not current.stopped.is_set():
                raise ProtocolError("This device is already connected")
            if current is None and len(self.sessions) >= 7:
                raise ProtocolError("At most eight computers are supported")
            self.sessions[session.peer_id] = session
            if self.session is None or self.session.stopped.is_set():
                self.session = session

    def select(self, peer_id):
        session = self.sessions.get(peer_id)
        if session and session.connected:
            self.session = session

    def data_connection(self, work, peer_id=None):
        """Run a bounded bulk channel on the same firewall port as the input lane."""
        control = self.sessions.get(peer_id) if peer_id else self.session
        if not control or not control.connected or "sharing-v1" not in control.peer_features:
            raise ConnectionError(tr('两端均需升级至支持文件共享的版本'))
        raw = socket.create_connection((control.sock.getpeername()[0], control.peer_port), timeout=5)
        channel = Session(self, raw, False, control.peer_id, lane="data", work=work)
        with self.lock:
            if self.stopped.is_set() or len(self.channels) >= 32:
                raw.close()
                raise ConnectionError(tr('传输通道繁忙，请稍后重试'))
            self.channels.add(channel)
        channel.run()
        if not getattr(channel, "work_finished", False):
            raise ConnectionError(tr('传输连接已断开或对方拒绝请求'))

    def channel_finished(self, session):
        with self.lock:
            self.channels.discard(session)
            channels = [c for c in self.channels if c.lane == "data" and c.control_session is session]
        for channel in channels:
            channel.stop()

    def connect(self, host, port=INPUT_PORT, expected_id=None):
        with self.lock:
            key = expected_id or (host, port)
            if key in self.dialing or self.stopped.is_set() or expected_id in self.sessions:
                return
            self.dialing.add(key)

        def dial():
            try:
                raw = socket.create_connection((host, port), timeout=4)
                self.adopt(raw, False, expected_id)
            except OSError:
                self.on_error(tr('连接失败，请检查对方已启动、IP 地址和防火墙'))
            finally:
                with self.lock:
                    self.dialing.discard(key)
        threading.Thread(target=dial, daemon=True, name="TLS-dial").start()

    def finished(self, session, error):
        with self.lock:
            if self.sessions.get(session.peer_id) is session:
                self.sessions.pop(session.peer_id)
            if self.session is session:
                self.session = next((s for s in self.sessions.values() if s.connected), None)
        self.on_disconnected(session, error)

    def stop(self):
        self.stopped.set()
        for channel in list(self.channels):
            channel.stop()
        if self.listener:
            self.listener.close()

