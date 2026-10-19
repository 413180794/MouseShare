"""Bounded, pinned TLS bulk transfers. Input packets stay on their own socket."""
import hashlib
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .i18n import tr
from .network import recv_exact, recv_frame
from .protocol import ProtocolError, frame

MAX_ENTRIES = 4096
MAX_BYTES = 100 * 1024**3
MAX_CLIPBOARD = 8 * 1024**2
CHUNK = 128 * 1024
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def is_link(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def safe_path(value):
    if not isinstance(value, str) or not 1 <= len(value.encode('utf-8')) <= 1024:
        raise ProtocolError(tr('文件路径过长'))
    path = PurePosixPath(value)
    parts = value.split('/')
    if path.is_absolute() or len(parts) > 32:
        raise ProtocolError(tr('无效文件路径'))
    for part in parts:
        if (part in {'', '.', '..'} or part[-1:] in {' ', '.'} or len(part.encode('utf-8')) > 240
                or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
                or part.split('.')[0].upper() in RESERVED):
            raise ProtocolError(tr('文件名包含目标系统不支持的字符'))
    return path


def manifest(paths, check=lambda: None):
    entries, sources, seen = [], {}, set()
    total = 0

    def add(source, relative):
        nonlocal total
        check()
        safe_path(relative)
        key = unicodedata.normalize('NFC', relative).casefold()
        if key in seen or len(entries) >= MAX_ENTRIES:
            raise ValueError(tr('文件名大小写冲突、重复或文件数量超过 4096'))
        seen.add(key)
        info = source.lstat()
        if is_link(source) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError(tr('请传输普通文件或文件夹；链接与特殊文件需先整理'))
        size = info.st_size if stat.S_ISREG(info.st_mode) else 0
        total += size
        if total > MAX_BYTES:
            raise ValueError(tr('单次传输总量上限为 100 GiB'))
        entries.append(dict(path=relative, size=size, directory=stat.S_ISDIR(info.st_mode)))
        sources[relative] = (source, info.st_size, info.st_mtime_ns)
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(source.iterdir(), key=lambda p: p.name.casefold()):
                add(child, relative + '/' + child.name)

    for raw in paths:
        path = Path(raw).absolute()
        # Parent links can change what a displayed path points at.
        if any(is_link(p) for p in [path, *path.parents]):
            raise ValueError(tr('请选取原始文件，避免通过符号链接发送'))
        add(path, path.name)
    if not entries:
        raise ValueError(tr('请选择文件或文件夹'))
    return entries, sources, total


def validate_manifest(entries, total):
    if type(total) is not int or not 0 <= total <= MAX_BYTES or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ProtocolError(tr('无效文件清单'))
    seen, directories, count = set(), set(), 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProtocolError(tr('无效文件清单'))
        path = safe_path(entry.get('path'))
        key = unicodedata.normalize('NFC', str(path)).casefold()
        if (key in seen or type(entry.get('size')) is not int or not 0 <= entry['size'] <= MAX_BYTES
                or type(entry.get('directory')) is not bool):
            raise ProtocolError(tr('文件清单冲突'))
        if str(path.parent) != '.' and unicodedata.normalize('NFC', str(path.parent)).casefold() not in directories:
            raise ProtocolError(tr('缺少父文件夹'))
        seen.add(key)
        if entry['directory']:
            if entry['size'] != 0:
                raise ProtocolError(tr('无效文件夹大小'))
            directories.add(key)
        count += entry['size']
    if count != total:
        raise ProtocolError(tr('文件总量不匹配'))


@dataclass
class Transfer:
    direction: str
    title: str = tr('准备文件…')
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    total: int = 0
    done: int = 0
    status: str = "preparing"
    detail: str = ""
    paths: list = field(default_factory=list)
    clipboard: bool = False
    peer_id: str = ''
    request: str = ''
    offer: str = ''
    cancelled: threading.Event = field(default_factory=threading.Event)
    decision: threading.Event = field(default_factory=threading.Event)
    approved: bool = False
    sock: object = None
    started: float = 0

    def cancel(self):
        self.cancelled.set()
        self.decision.set()
        if self.sock:
            try:
                self.sock.shutdown(2)
            except OSError:
                pass


class SharingService:
    def __init__(self, network, settings, allowed=lambda kind: True, emit=lambda event: None):
        self.network, self.settings, self.allowed, self.emit = network, settings, allowed, emit
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False
        self.clip_pending = None
        self.clip_thread = None
        self.authorize_request = lambda peer, offer, request: False
        network.on_data = self.receive

    def enabled(self, kind):
        return (not self.closed and self.settings.get('clipboard_sync' if kind == 'clipboard' else 'file_sharing', True)
                and self.allowed(kind))

    def update(self, job, status=None, detail=None):
        if status == 'transferring' and job.status != status:
            job.started = time.monotonic()
        if status:
            job.status = status
        if detail is not None:
            job.detail = detail
        self.emit(dict(type='transfer', job=job.id, direction=job.direction, title=job.title,
                       status=job.status, detail=job.detail, total=job.total, done=job.done,
                       paths=list(job.paths), clipboard=job.clipboard, peer=job.peer_id,
                       request=job.request, offer=job.offer,
                       speed=int(job.done / max(0.1, time.monotonic() - job.started)) if job.started else 0))

    def register(self, job):
        with self.lock:
            active = [j for j in self.jobs.values() if j.status not in {'complete', 'cancelled', 'error', 'rejected'}]
            if len(active) >= 2 or job.id in self.jobs:
                raise ValueError(tr('已有两个传输任务，请等待完成'))
            # Keep at most 30 metadata records, never clipboard contents.
            finished = [key for key, value in self.jobs.items() if value not in active]
            for key in finished[:-28]:
                del self.jobs[key]
            self.jobs[job.id] = job
        self.update(job)

    def decide(self, job_id, approved):
        job = self.jobs.get(job_id)
        if job and job.status == 'offered':
            job.approved = approved
            job.decision.set()

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job:
            job.cancel()

    def check(self, job):
        if job.cancelled.is_set() or not self.enabled('files'):
            raise InterruptedError(tr('传输已取消或共享已暂停'))

    def send_files(self, paths, clipboard=False, *, peer_id=None, request='', offer=''):
        session = self.network.peer_session(peer_id) if peer_id else self.network.session
        if not session or not session.connected:
            raise ValueError(tr('目标电脑已断开连接'))
        if session and session.connected and 'sharing-v1' not in getattr(session, 'peer_features', []):
            raise ValueError(tr('文件共享需要两端均升级至 v0.3.0 或更新版本'))
        if not self.enabled('files'):
            raise ValueError(tr('文件共享已关闭，或当前处于暂停／游戏模式'))
        job = Transfer('send', clipboard=clipboard, paths=[str(Path(p).absolute()) for p in paths],
                       peer_id=getattr(session, 'peer_id', ''), request=request, offer=offer)
        self.register(job)
        threading.Thread(target=self._send_files, args=(job, list(paths)), daemon=True, name='file-send').start()
        return job.id

    def _send_files(self, job, paths):
        try:
            entries, sources, job.total = manifest(paths, lambda: self.check(job))
            self.check(job)
            names = [e['path'] for e in entries if '/' not in e['path']]
            job.title = '、'.join(names)[:160]
            self.update(job, 'waiting', tr('等待对方接收'))

            def work(channel):
                channel.kind = 'files'
                sock = job.sock = channel.sock
                header = dict(type='files', id=job.id, count=len(entries), total=job.total, clipboard=job.clipboard)
                if job.request:
                    header.update(request=job.request, offer=job.offer)
                sock.sendall(frame(header))
                for entry in entries:
                    self.check(job)
                    sock.sendall(frame(dict(type='entry', **entry)))
                answer = recv_frame(sock)
                if answer.get('type') != 'accept' or answer.get('accepted') is not True:
                    self.update(job, 'rejected', tr('对方拒绝接收或文件共享不可用'))
                    return
                self.update(job, 'transferring', tr('正在发送'))
                last = 0
                for entry in entries:
                    if entry['directory']:
                        continue
                    source, size, modified = sources[entry['path']]
                    self.check(job)
                    if any(is_link(p) for p in [source, *source.parents]):
                        raise OSError(tr('源文件变成了链接，请重新发送'))
                    fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
                    with os.fdopen(fd, 'rb') as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or (info.st_size, info.st_mtime_ns) != (size, modified):
                            raise OSError(tr('源文件已变化，请重新发送'))
                        digest, remaining = hashlib.sha256(), size
                        while remaining:
                            self.check(job)
                            data = stream.read(min(CHUNK, remaining))
                            if not data:
                                raise OSError(tr('源文件已变化'))
                            sock.sendall(data)
                            digest.update(data)
                            remaining -= len(data)
                            job.done += len(data)
                            if time.monotonic() - last > 0.1:
                                self.update(job)
                                last = time.monotonic()
                        after = os.fstat(stream.fileno())
                        if (after.st_size, after.st_mtime_ns) != (size, modified):
                            raise OSError(tr('源文件已变化，请重新发送'))
                    sock.sendall(frame(dict(type='hash', sha256=digest.hexdigest())))
                if recv_frame(sock).get('type') != 'complete':
                    raise OSError(tr('对方未确认传输完成'))
                self.update(job, 'complete', tr('对方已接收并校验'))
            self.network.data_connection(work, job.peer_id) if job.peer_id else self.network.data_connection(work)
        except Exception as exc:
            if job.status != 'rejected':
                self.update(job, 'cancelled' if job.cancelled.is_set() or isinstance(exc, InterruptedError) else 'error',
                            str(exc) if isinstance(exc, (ValueError, OSError, InterruptedError)) else tr('传输失败，请重新发送'))
        finally:
            job.sock = None

    def send_clipboard(self, payload):
        if len(payload) > MAX_CLIPBOARD or not self.enabled('clipboard'):
            return
        with self.lock:
            self.clip_pending = (payload, self.network.session)
            if self.clip_thread and self.clip_thread.is_alive():
                return
            self.clip_thread = threading.Thread(target=self._clipboard_worker, daemon=True, name='clipboard-send')
            self.clip_thread.start()

    def _clipboard_worker(self):
        while True:
            with self.lock:
                pending, self.clip_pending = self.clip_pending, None
                if pending is None:
                    self.clip_thread = None
                    return
                payload, target = pending
            if target is not self.network.session or not target or not target.connected:
                continue
            if not self.enabled('clipboard'):
                continue
            try:
                def work(channel):
                    channel.kind = 'clipboard'
                    sock = channel.sock
                    sock.sendall(frame(dict(type='clipboard', size=len(payload), sha256=hashlib.sha256(payload).hexdigest())))
                    if recv_frame(sock).get('accepted') is True and self.enabled('clipboard'):
                        sock.sendall(payload)
                        if recv_frame(sock).get('type') == 'complete':
                            self.emit(dict(type='clipboard_status', text=tr('剪贴板已同步')))
                key = getattr(target, 'peer_id', '')
                self.network.data_connection(work, key) if key else self.network.data_connection(work)
            except (OSError, ValueError):
                self.emit(dict(type='clipboard_status', text=tr('剪贴板同步暂不可用')))

    def receive(self, channel):
        control = getattr(channel, 'control_session', None) or self.network.session
        header = recv_frame(channel.sock)
        channel.kind = header.get('type')
        if header.get('type') == 'clipboard':
            self._receive_clipboard(channel.sock, header, control)
        elif header.get('type') == 'files':
            self._receive_files(channel, header)
        else:
            raise ProtocolError("Unknown sharing request")

    def _receive_clipboard(self, sock, header, control):
        size = header.get('size')
        if type(size) is not int or not 0 < size <= MAX_CLIPBOARD:
            raise ProtocolError("Clipboard too large")
        accepted = self.enabled('clipboard')
        sock.sendall(frame(dict(type='accept', accepted=bool(accepted))))
        if not accepted:
            return
        payload = recv_exact(sock, size)
        if hashlib.sha256(payload).hexdigest() != header.get('sha256'):
            raise ProtocolError("Clipboard checksum mismatch")
        if self.enabled('clipboard'):
            self.emit(dict(type='clipboard', payload=payload, control=control))
        sock.sendall(frame(dict(type='complete')))

    def _receive_files(self, channel, header):
        sock, job, staging = channel.sock, None, None
        try:
            count = header.get('count')
            if (not self.enabled('files') or type(count) is not int or not 1 <= count <= MAX_ENTRIES
                    or not isinstance(header.get('id'), str) or not re.fullmatch('[0-9a-f]{32}', header['id'])
                    or type(header.get('clipboard')) is not bool):
                sock.sendall(frame(dict(type='accept', accepted=False)))
                return
            entries = []
            for _ in range(count):
                entry = recv_frame(sock)
                if entry.get('type') != 'entry' or set(entry) != {'type', 'path', 'size', 'directory'}:
                    raise ProtocolError("Missing file entry")
                safe_path(entry.get('path'))
                if type(entry.get('size')) is not int or type(entry.get('directory')) is not bool:
                    raise ProtocolError("Invalid file entry")
                entries.append(entry)
            validate_manifest(entries, header.get('total'))
            names = [e['path'] for e in entries if '/' not in e['path']]
            job = Transfer('receive', title='、'.join(names)[:160], id=header['id'], total=header['total'],
                           clipboard=header['clipboard'], sock=sock, peer_id=getattr(channel, 'peer_id', ''),
                           request=header.get('request', ''), offer=header.get('offer', ''))
            requested = bool(job.request)
            if requested and (not re.fullmatch('[0-9a-f]{32}', str(job.request))
                              or not re.fullmatch('[0-9a-f]{32}', str(job.offer))
                              or not self.authorize_request(job.peer_id, job.offer, job.request)):
                sock.sendall(frame(dict(type='accept', accepted=False)))
                return
            self.register(job)
            self.update(job, 'offered', tr('{p0} 请求发送 {p1} 项', p0=channel.peer_name, p1=len(entries)))
            if requested or self.settings.get('auto_receive_files', False):
                job.approved = True
                job.decision.set()
            deadline = time.monotonic() + 110
            while not job.decision.wait(0.2):
                self.check(job)
                if time.monotonic() > deadline or channel.stopped.is_set():
                    break
            self.check(job)
            if not job.approved:
                sock.sendall(frame(dict(type='accept', accepted=False)))
                self.update(job, 'rejected', tr('已拒绝或接收请求已过期'))
                return
            destination = Path(self.settings.get('receive_directory') or Path.home() / 'Downloads' / 'MouseShare')
            destination.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(destination).free < job.total + 10 * 1024**2:
                raise OSError(tr('接收目录空间不足'))
            staging = Path(tempfile.mkdtemp(prefix='.mouseshare-', dir=destination))
            sock.sendall(frame(dict(type='accept', accepted=True)))
            self.update(job, 'transferring', tr('正在接收并校验'))
            last = 0
            for entry in entries:
                self.check(job)
                target = staging.joinpath(*safe_path(entry['path']).parts)
                if entry['directory']:
                    target.mkdir(mode=0o700)
                    continue
                digest, remaining = hashlib.sha256(), entry['size']
                with target.open('xb') as stream:
                    if os.name != 'nt':
                        target.chmod(0o600)
                    while remaining:
                        self.check(job)
                        data = recv_exact(sock, min(CHUNK, remaining))
                        stream.write(data)
                        digest.update(data)
                        remaining -= len(data)
                        job.done += len(data)
                        if time.monotonic() - last > 0.1:
                            self.update(job)
                            last = time.monotonic()
                check = recv_frame(sock)
                if check.get('type') != 'hash' or digest.hexdigest() != check.get('sha256'):
                    raise ProtocolError(tr('文件校验失败，未保留不完整文件'))
            self.check(job)
            # Commit an entire batch atomically into its own unique folder.
            final = destination / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
            staging.rename(final)
            staging = None
            job.paths = [str(final / name) for name in names]
            self.update(job, 'complete', tr('接收完成，SHA-256 校验通过'))
            sock.sendall(frame(dict(type='complete')))
        except Exception as exc:
            if job:
                self.update(job, 'cancelled' if job.cancelled.is_set() or isinstance(exc, InterruptedError) else 'error',
                            str(exc) if isinstance(exc, (ValueError, OSError)) else tr('接收失败，请重新发送'))
            raise
        finally:
            if staging:
                shutil.rmtree(staging)
            if job:
                job.sock = None

    def cancel_files(self):
        for job in list(self.jobs.values()):
            if job.status in {'preparing', 'waiting', 'offered', 'transferring'}:
                job.cancel()

    def cancel_clipboard(self):
        with self.lock:
            self.clip_pending = None
        for channel in list(self.network.channels):
            if getattr(channel, 'kind', None) == 'clipboard':
                channel.stop()

    def pause(self):
        self.cancel_clipboard()
        self.cancel_files()

    def stop(self):
        self.closed = True
        self.pause()
