"""Opt-in login startup using each platform's user-scoped mechanism."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path


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
            raise OSError("请先把 MouseShare 拖入「应用程序」，再开启登录启动")
        path = Path.home() / "Library/LaunchAgents/io.github.makesail.mouseshare.plist"
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"Label": "io.github.makesail.mouseshare", "ProgramArguments": args,
                    "RunAtLoad": True, "ProcessType": "Interactive"}
            path.write_bytes(plistlib.dumps(data))
            os.chmod(path, 0o600)
        else:
            path.unlink(missing_ok=True)

