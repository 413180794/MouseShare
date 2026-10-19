"""Atomic settings and per-device identity; never store keyboard contents."""
import json
import os
import platform
import threading
from pathlib import Path

from .games import CATALOG_VERSION, DEFAULT_PROCESSES, upgrade_defaults


def data_dir() -> Path:
    if platform.system() == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif platform.system() == "Darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "MouseShare"


class Settings:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.directory.chmod(0o700)
        self.path = self.directory / "settings.json"
        self.lock = threading.RLock()
        self.values = {
            "name": platform.node() or "My computer",
            "side": "right", "sensitivity": 1.0,
            "game_mode": False, "auto_fullscreen": True,
            "game_processes": list(DEFAULT_PROCESSES), "game_catalog_version": CATALOG_VERSION,
            "peers": {}, "startup": False,
            "language": "system",
        }
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Invalid settings file")
            self.values.update(loaded)
            upgrade_defaults(self.values)
        if self.get("side") not in ("left", "right", "top", "bottom"):
            self.values["side"] = "right"

    def get(self, key, default=None):
        with self.lock:
            # Return snapshots so background threads cannot mutate settings accidentally.
            return json.loads(json.dumps(self.values.get(key, default)))

    def set(self, **values):
        with self.lock:
            self.values.update(values)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.values, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)

    def trust(self, peer_id, name, host):
        with self.lock:
            peers = self.get("peers")
            peers[peer_id] = {"name": name, "host": host}
            self.set(peers=peers)

    def forget(self, peer_id):
        with self.lock:
            peers = self.get("peers")
            peers.pop(peer_id, None)
            self.set(peers=peers)

