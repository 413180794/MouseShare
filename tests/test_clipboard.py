import json
import os
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from mouseshare.clipboard import ClipboardSync, ORIGIN, decode_clipboard, encode_clipboard, files_mime
from mouseshare.config import Settings


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_text_rich_image_round_trip_and_no_echo(app):
    mime = QMimeData()
    mime.setText('你好 hello')
    mime.setHtml('<b>你好 hello</b>')
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(0xff123456)
    mime.setImageData(image)
    payload, paths = encode_clipboard(mime)
    result = decode_clipboard(payload)
    assert result.text() == mime.text() and result.html() == mime.html()
    assert result.imageData().pixel(0, 0) == image.pixel(0, 0)
    assert result.hasFormat(ORIGIN)
    assert encode_clipboard(result) == (None, [])
    assert not paths


def test_private_formats_and_file_urls(app, tmp_path):
    mime = QMimeData()
    mime.setText('password')
    mime.setData('org.nspasteboard.ConcealedType', b'')
    assert encode_clipboard(mime) == (None, [])
    raw = QMimeData()
    raw.setUrls([QUrl.fromLocalFile(str(tmp_path / 'file'))])
    payload, paths = encode_clipboard(raw)
    assert payload is None and [Path(p) for p in paths] == [tmp_path / 'file']
    assert encode_clipboard(files_mime([tmp_path / 'file'])) == (None, [])


@pytest.mark.parametrize('payload', [b'[]', b'{"text":2}', b'{"bad":"mime"}', b'{"png":"%%%"}',
                                     b'{"png":"YWJj"}', b'null'])
def test_invalid_clipboard_is_rejected(app, payload):
    with pytest.raises((ValueError, TypeError)):
        decode_clipboard(payload)


def test_poll_only_new_copies_never_stale_or_received_contents(app, tmp_path):
    settings = Settings(tmp_path)
    clipboard = SimpleNamespace(mimeData=lambda: clipboard.mime, setMimeData=lambda mime: setattr(clipboard, 'mime', mime))
    clipboard.mime = QMimeData()
    clipboard.mime.setText('before connection')
    sent, files = [], []
    service = SimpleNamespace(network=SimpleNamespace(session=SimpleNamespace(connected=True, peer_features=['sharing-v1'])),
                              enabled=lambda kind: True, send_clipboard=sent.append,
                              send_files=lambda paths, clipboard: files.append(paths))
    watcher = ClipboardSync(service, settings, clipboard=clipboard)
    try:
        watcher.poll()
        assert not sent
        clipboard.mime = QMimeData()
        clipboard.mime.setText('new copy')
        watcher.poll()
        assert json.loads(sent[0]) == {'text': 'new copy'}
        watcher.poll()
        assert len(sent) == 1
        watcher.apply(b'{"text":"remote copy"}')
        watcher.poll()
        assert len(sent) == 1
        clipboard.mime = QMimeData()
        clipboard.mime.setUrls([QUrl.fromLocalFile(str(tmp_path / 'file'))])
        watcher.poll()
        assert [[Path(p) for p in batch] for batch in files] == [[tmp_path / 'file']]
        service.enabled = lambda kind: False
        watcher.poll()
        clipboard.mime = QMimeData()
        clipboard.mime.setText('paused')
        service.enabled = lambda kind: True
        watcher.poll()
        assert len(sent) == 1
    finally:
        watcher.stop()
