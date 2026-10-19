"""Opt-in login startup using each platform's user-scoped mechanism."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .i18n import tr


def command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--minimized"]
    return [sys.executable, "-m", "mouseshare", "--minimized"]


def set_enabled(enabled):
    args = command()
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            if enabled:
                winreg.SetValueEx(key, "MouseShare", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
            else:
                try:
                    winreg.DeleteValue(key, "MouseShare")
                except FileNotFoundError:
                    pass
    elif sys.platform == "darwin":
        if enabled and getattr(sys, "frozen", False) and not sys.executable.startswith("/Applications/"):
            raise OSError(tr('请先把 MouseShare 拖入「应用程序」，再开启登录启动'))
        path = Path.home() / "Library/LaunchAgents/io.github.makesail.mouseshare.plist"
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"Label": "io.github.makesail.mouseshare", "ProgramArguments": args,
                    "RunAtLoad": True, "ProcessType": "Interactive"}
            path.write_bytes(plistlib.dumps(data))
            os.chmod(path, 0o600)
        else:
            path.unlink(missing_ok=True)

    elif sys.platform.startswith('linux'):
        path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'autostart/mouseshare.desktop'
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desktop_entry(args), encoding='utf-8')
            path.chmod(0o600)
        else:
            path.unlink(missing_ok=True)


def desktop_entry(args):
    # Desktop Entry Exec has its own escaping rules; no shell is involved.
    def quote(arg):
        if '\n' in arg or '\r' in arg or '\0' in arg:
            raise OSError(tr('启动路径包含无效字符'))
        arg = arg.replace('%', '%%')
        for char in ('\\', '"', '`', '$'):
            arg = arg.replace(char, '\\' + char)
        return '"' + arg + '"'
    return ('[Desktop Entry]\nType=Application\nName=MouseShare\n'
            'Comment=Share keyboard, mouse, clipboard and files\nTerminal=false\n'
            'Categories=Utility;Network;\nExec=' + ' '.join(quote(a) for a in args) + '\n')
