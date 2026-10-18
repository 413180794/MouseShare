"""GUI-thread clipboard adapter, with bounded formats and echo suppression."""
import base64
import hashlib
import json
import struct
import sys

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QObject, QTimer, QUrl
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication

from .sharing import MAX_CLIPBOARD

ORIGIN = 'application/x-mouseshare-origin'
PRIVATE = {'org.nspasteboard.ConcealedType', 'org.nspasteboard.TransientType',
           'application/x-keepassxc', 'x-kde-passwordManagerHint'}
MAX_PIXELS = 16_000_000


def encode_clipboard(mime, images=True):
    if not mime or mime.hasFormat(ORIGIN) or any(mime.hasFormat(kind) for kind in PRIVATE):
        return None, []
    if mime.hasUrls():
        urls = mime.urls()
        if urls and all(url.isLocalFile() for url in urls):
            return None, [url.toLocalFile() for url in urls]
    value = {}
    if mime.hasText():
        value['text'] = mime.text()
    if mime.hasHtml():
        value['html'] = mime.html()
    if sum(len(s.encode('utf-8')) for s in value.values()) > 2 * 1024**2:
        raise ValueError('文字／富文本剪贴板上限为 2 MiB')
    if images and mime.hasImage():
        image = QImage(mime.imageData())
        if image.width() * image.height() > MAX_PIXELS:
            raise ValueError('图片上限为 1600 万像素')
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.isNull() and image.save(buffer, 'PNG'):
            value['png'] = base64.b64encode(bytes(buffer.data())).decode('ascii')
    if not value:
        return None, []
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_CLIPBOARD:
        raise ValueError('剪贴板上限为 8 MiB，请将图片保存为文件后发送')
    return payload, []


def decode_clipboard(payload, images=True):
    if len(payload) > MAX_CLIPBOARD:
        raise ValueError('Clipboard too large')
    value = json.loads(payload)
    if (not isinstance(value, dict) or not value or set(value) - {'text', 'html', 'png'}
            or not all(isinstance(v, str) for v in value.values())):
        raise ValueError('Invalid clipboard content')
    mime = QMimeData()
    if 'text' in value:
        mime.setText(value['text'])
    if 'html' in value:
        mime.setHtml(value['html'])
    if 'png' in value and images:
        png = base64.b64decode(value['png'], validate=True)
        buffer = QBuffer()
        buffer.setData(QByteArray(png))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer, b'PNG')
        size = reader.size()
        if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > MAX_PIXELS:
            raise ValueError('Invalid image dimensions')
        image = reader.read()
        if image.isNull():
            raise ValueError('Invalid image')
        mime.setImageData(image)
    mime.setData(ORIGIN, b'1')
    return mime


def files_mime(paths, mark=True):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    # Explorer should copy, including when the source clipboard was a Cut.
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', struct.pack('<I', 1))
    if mark:
        mime.setData(ORIGIN, b'1')
    return mime


class ClipboardSync(QObject):
    def __init__(self, service, settings, status=lambda text: None, parent=None, clipboard=None):
        super().__init__(parent)
        self.service, self.settings, self.status = service, settings, status
        self.clipboard = clipboard or QApplication.clipboard()
        self.last = None
        self.active = False
        self.generation = 0
        self.last_sequence = None
        if hasattr(self.clipboard, 'dataChanged'):
            self.clipboard.dataChanged.connect(self.changed)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll)
        # Polling also covers background macOS changes; all reads remain on the GUI thread.
        self.timer.start()

    def changed(self):
        self.generation += 1

    def sequence(self):
        if sys.platform == 'darwin':
            from AppKit import NSPasteboard
            return int(NSPasteboard.generalPasteboard().changeCount())
        if sys.platform == 'win32':
            import ctypes
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        return self.generation

    def poll(self):
        session = self.service.network.session
        active = (self.service.enabled('clipboard') and session and session.connected
                  and 'sharing-v1' in getattr(session, 'peer_features', []))
        if not active:
            self.active = False
            self.last = None
            self.last_sequence = None
            return
        try:
            # Qt's macOS dataChanged notification waits for application activation.
            # Native sequence polling detects background copies and avoids re-encoding unchanged images.
            sequence = self.sequence() if self.clipboard is QApplication.clipboard() else None
            if self.active and sequence is not None and sequence == self.last_sequence:
                return
            self.last_sequence = sequence
            payload, paths = encode_clipboard(self.clipboard.mimeData(), self.settings.get('clipboard_images', True))
            fingerprint = hashlib.sha256(payload or json.dumps(paths, ensure_ascii=False).encode()).hexdigest()
            if not self.active:
                self.active, self.last = True, fingerprint
                return  # Never send clipboard contents that predate the connection.
            if fingerprint == self.last:
                return
            self.last = fingerprint
            self.generation += 1
            if paths:
                if self.settings.get('clipboard_files', True) and self.service.enabled('files'):
                    self.service.send_files(paths, clipboard=True)
            elif payload:
                self.service.send_clipboard(payload)
        except (ValueError, OSError) as exc:
            # Deduplicate errors without retaining clipboard contents.
            message = str(exc)
            if self.last != message:
                self.last = message
                self.status(message)

    def apply(self, payload):
        if not self.service.enabled('clipboard'):
            return
        try:
            mime = decode_clipboard(payload, self.settings.get('clipboard_images', True))
            self.clipboard.setMimeData(mime)
            self.generation += 1
            self.status('已收到另一台电脑的剪贴板')
        except (ValueError, TypeError, UnicodeError):
            self.status('剪贴板格式无法读取，请重新复制')

    def copy_files(self, paths):
        self.clipboard.setMimeData(files_mime(paths))
        self.generation += 1
        self.status('文件已复制，可在 Finder／资源管理器中粘贴')

    def stop(self):
        self.timer.stop()
