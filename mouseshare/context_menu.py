"""Opt-in, per-user file-manager commands and bounded local paste requests."""
import json
import os
from pathlib import Path
import subprocess
import sys

from .i18n import tr

REGISTRY_KEYS = (r'Software\Classes\Directory\Background\shell\MouseSharePaste',
                 r'Software\Classes\Directory\shell\MouseSharePaste')


def command():
    return [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'mouseshare']


def request(destination=None):
    return json.dumps(dict(action='paste' if destination else 'show', destination=destination),
                      ensure_ascii=False).encode('utf-8')+b'\n'


def parse_request(data):
    if len(data) > 8192:
        raise ValueError('Local request too large')
    if data == b'show':
        return None
    value = json.loads(data)
    if not isinstance(value, dict) or value.get('action') not in {'show', 'paste'}:
        raise ValueError('Invalid local request')
    if value['action'] == 'show':
        return None
    path = value.get('destination')
    if not isinstance(path, str) or '\0' in path or not Path(path).is_absolute():
        raise ValueError('Invalid destination')
    target = Path(path).resolve(strict=True)
    if not target.is_dir():
        raise ValueError('Destination is not a directory')
    return str(target)


def extension_source(args, title):
    # argv is a JSON literal decoded by Python, never interpreted by a shell.
    header = 'COMMAND = json.loads('+repr(json.dumps(args))+')\nTITLE = '+repr(title)+'\n'
    return '''# Installed by MouseShare. Remove from MouseShare > Clipboard to disable.
import json
import subprocess
from urllib.parse import urlparse, unquote
import gi
try:
    gi.require_version('Nautilus', '4.0')
except ValueError:
    gi.require_version('Nautilus', '3.0')
from gi.repository import GObject, Nautilus
'''+header+'''class MouseSharePaste(GObject.GObject, Nautilus.MenuProvider):
    def items(self, folder):
        uri = urlparse(folder.get_uri())
        if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
            return []
        path = unquote(uri.path)
        item = Nautilus.MenuItem(name='MouseShare::Paste', label=TITLE, tip=TITLE)
        item.connect('activate', lambda *unused: subprocess.Popen(COMMAND + ['--paste-to', path], close_fds=True))
        return [item]
    def get_background_items(self, *args):
        return self.items(args[-1])
    def get_file_items(self, *args):
        files = args[-1]
        return self.items(files[0]) if len(files) == 1 and files[0].is_directory() else []
'''


def set_enabled(enabled):
    title = str(tr('接收文件到此处（MouseShare）'))
    if sys.platform == 'win32':
        import winreg
        for index, path in enumerate(REGISTRY_KEYS):
            if enabled:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                    winreg.SetValueEx(key, '', 0, winreg.REG_SZ, title)
                    winreg.SetValueEx(key, 'Icon', 0, winreg.REG_SZ, subprocess.list2cmdline([sys.executable]))
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path+r'\command') as key:
                    # Explorer replaces its own %V/%1 placeholder, including spaces.
                    line = subprocess.list2cmdline(command())+' --paste-to "'+('%V' if index == 0 else '%1')+'"'
                    winreg.SetValueEx(key, '', 0, winreg.REG_SZ, line)
            else:
                for name in (path+r'\command', path):
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, name)
                    except FileNotFoundError:
                        pass
    elif sys.platform.startswith('linux'):
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))
        path = root/'nautilus-python/extensions/mouseshare_paste.py'
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(extension_source(command(), title), encoding='utf-8')
            path.chmod(0o600)
        else:
            path.unlink(missing_ok=True)
    else:
        raise OSError(tr('此右键扩展支持 Windows 资源管理器和 Ubuntu GNOME 文件管理器'))
