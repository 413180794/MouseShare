import json
from pathlib import PurePosixPath
import sys
from types import SimpleNamespace

import pytest

from mouseshare.context_menu import extension_source, parse_request, request, set_enabled


def test_local_paste_requests_validate_directory_and_size(tmp_path):
    assert parse_request(request(str(tmp_path))) == str(tmp_path.resolve())
    assert parse_request(b'show') is None
    for invalid in [b'x'*8193, b'{}', b'[]', request('relative/path'), request(str(tmp_path/'missing')),
                    json.dumps(dict(action='execute', command='whatever')).encode()]:
        with pytest.raises((ValueError, OSError)):
            parse_request(invalid)
    file = tmp_path/'file'
    file.touch()
    with pytest.raises(ValueError):
        parse_request(request(str(file)))


def test_nautilus_extension_uses_argv_without_shell_and_is_reversible(monkeypatch, tmp_path):
    import mouseshare.context_menu as menu
    monkeypatch.setattr(menu.sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    set_enabled(True)
    path = tmp_path/'nautilus-python/extensions/mouseshare_paste.py'
    source = path.read_text()
    compile(source, str(path), 'exec')
    assert 'shell=True' not in source
    set_enabled(False)
    assert not path.exists()


def test_nautilus_action_preserves_unicode_spaces_and_shell_characters(monkeypatch):
    import subprocess
    callbacks, launched = [], []
    class Item:
        def __init__(self, **kwargs):
            pass
        def connect(self, signal, callback):
            callbacks.append(callback)
    monkeypatch.setitem(sys.modules, 'gi', SimpleNamespace(require_version=lambda *a: None))
    monkeypatch.setitem(sys.modules, 'gi.repository', SimpleNamespace(
        GObject=SimpleNamespace(GObject=type('Object', (), {})),
        Nautilus=SimpleNamespace(MenuProvider=type('Provider', (), {}), MenuItem=Item)))
    monkeypatch.setattr(subprocess, 'Popen', lambda args, **kwargs: launched.append(args))
    args = ['/opt/path with $/MouseShare']
    scope = {}
    exec(extension_source(args, 'Receive files here'), scope)
    provider = scope['MouseSharePaste']()
    folder = SimpleNamespace(get_uri=lambda: PurePosixPath('/tmp/中文 $ (files)').as_uri(), is_directory=lambda: True)
    assert len(provider.get_background_items(folder)) == 1
    callbacks[0]()
    assert launched == [args+['--paste-to', '/tmp/中文 $ (files)']]
    assert provider.items(SimpleNamespace(get_uri=lambda: 'smb://server/folder')) == []


@pytest.mark.skipif(sys.platform != 'win32' or not __import__('os').environ.get('GITHUB_ACTIONS'),
                    reason='Registry integration only on an isolated Windows CI runner')
def test_native_explorer_registration_is_quoted_user_scoped_and_removable():
    import winreg
    from mouseshare.context_menu import REGISTRY_KEYS
    try:
        set_enabled(True)
        for index, path in enumerate(REGISTRY_KEYS):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path+r'\command') as key:
                line, kind = winreg.QueryValueEx(key, '')
            assert kind == winreg.REG_SZ and line.endswith('--paste-to "'+('%V' if index == 0 else '%1')+'"')
    finally:
        set_enabled(False)
    for path in REGISTRY_KEYS:
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
