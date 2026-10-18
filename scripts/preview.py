"""Render the real Qt UI with isolated sample data and no hooks or network."""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mouseshare.app import MainWindow  # noqa: E402
from mouseshare.config import Settings  # noqa: E402
from mouseshare.security import Identity  # noqa: E402
from mouseshare.ui import apply_theme  # noqa: E402
from mouseshare.branding import icon_image  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/design"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(Path(directory))
        settings.set(name="我的 Mac", side="left")
        window = MainWindow(settings, Identity(Path(directory)), demo=True)
        peer_id = "a" * 64
        window.peers[peer_id] = dict(id=peer_id, name="Windows 台式机", os="Windows", host="192.168.1.20",
                                     port=24872, seen=time.monotonic())
        window.network.session = SimpleNamespace(peer_id=peer_id, connected=True)
        state = dict(state="local", game=False, manual_game=False, auto_reason="", paused=False,
                     connected=True, peer_available=True, peer_name="Windows 台式机", ready=True, error="")
        window.show_status(state)
        window.refresh_peers()
        window.show()
        for i, name in enumerate(["connection", "settings", "game", "sharing"]):
            window.stack.setCurrentIndex(i)
            app.processEvents()
            window.grab().save(str(args.output / f"{name}.png"))
        window.share_panel.transfer(dict(type='transfer', job='demo-file', direction='receive',
                                        title='设计稿 / 项目资料', status='transferring',
                                        detail='正在接收并校验', total=200 * 1024**2, done=84 * 1024**2,
                                        paths=[], clipboard=False, speed=12 * 1024**2), persist=False)
        app.processEvents()
        window.grab().save(str(args.output / 'sharing-progress.png'))
        for name, changes in [("offline", dict(connected=False, peer_name="", peer_available=False)),
                              ("locked", dict(game=True, manual_game=True)),
                              ("permissions", dict(ready=False, error="请为 MouseShare 开启辅助功能和输入监控。"))]:
            window.stack.setCurrentIndex(0)
            window.show_status({**state, **changes})
            app.processEvents()
            window.grab().save(str(args.output / f"{name}.png"))
        for side in ("top", "bottom", "right"):
            settings.set(side=side)
            window.show_status(state)
            app.processEvents()
            window.grab().save(str(args.output / f"direction-{side}.png"))
        session = SimpleNamespace(peer_name="Windows 台式机", code="482913", approve=lambda ok: None,
                                  stopped=SimpleNamespace(is_set=lambda: False))
        window.pair_dialog(session)
        dialog = next(iter(window.dialogs.values()))[0]
        app.processEvents()
        dialog.grab().save(str(args.output / "pairing.png"))
        dialog.reject()
        window.check_permissions()
        app.processEvents()
        window.permission_guide.grab().save(str(args.output / "permission-guide.png"))
        window.permission_guide.accept()
        window.stack.setCurrentIndex(1)
        window.device_name.setText("我的 MacBook")
        app.processEvents()
        window.grab().save(str(args.output / "settings-unsaved.png"))
        icon_image(512).save(str(args.output / "icon.png"))
        icon_image(32, True).save(str(args.output / "tray.png"))
        window.shutdown()
    print(f"Rendered UI previews to {args.output}")


if __name__ == "__main__":
    main()
