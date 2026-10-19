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

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

from mouseshare.app import MainWindow  # noqa: E402
from mouseshare.branding import icon_image  # noqa: E402
from mouseshare.config import Settings  # noqa: E402
from mouseshare.drop_design import DropVisual  # noqa: E402
from mouseshare.drop_overlay import hint_geometry  # noqa: E402
from mouseshare.i18n import tr  # noqa: E402
from mouseshare.security import Identity  # noqa: E402
from mouseshare.ui import apply_theme, card, text_label  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/design"))
    parser.add_argument('--language', choices=['zh_CN', 'en'], default='zh_CN')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(Path(directory))
        settings.set(name='My Mac', side="left", language=args.language,
                     peers={'a'*64: dict(name='Windows Desktop', host='192.168.1.20')})
        window = MainWindow(settings, Identity(Path(directory)), demo=True)
        peer_id = "a" * 64
        window.peers[peer_id] = dict(id=peer_id, name="Windows Desktop", os="Windows", host="192.168.1.20",
                                     port=24872, seen=time.monotonic())
        window.network.session = SimpleNamespace(peer_id=peer_id, peer_name='Windows Desktop', connected=True,
                                                 peer_features=['sharing-v1'])
        window.network.sessions[peer_id] = window.network.session
        state = dict(state="local", game=False, manual_game=False, auto_reason="", paused=False,
                     connected=True, peer_available=True, peer_name="Windows Desktop", ready=True, error="")
        window.show_status(state)
        window.refresh_peers()
        window.show()
        for i, name in enumerate(["connection", "settings", "game", "sharing", 'layout']):
            window.stack.setCurrentIndex(i)
            app.processEvents()
            window.grab().save(str(args.output / f"{name}.png"))
        original_metadata = window.layout_editor.metadata
        window.layout_editor.update_devices({window.identity.id: dict(name='Ubuntu Desktop', connected=True,
            screen=dict(x=0, y=0, w=3840, h=1080, monitors=[
                dict(id='left', x=0, y=0, w=1920, h=1080), dict(id='right', x=1920, y=0, w=1920, h=1080)])),
            peer_id: dict(name='Windows Laptop', connected=True, screen=dict(w=1920, h=1080))})
        window.layout_editor.reset_nodes()
        app.processEvents()
        window.grab().save(str(args.output / 'layout-multimonitor.png'))
        window.layout_editor.update_devices(original_metadata)
        window.layout_editor.reset_nodes()
        window.share_panel.transfer(dict(type='transfer', job='demo-file', direction='receive',
                                        title='Designs / Project files', status='transferring',
                                        detail=tr('正在接收并校验'), total=200 * 1024**2, done=84 * 1024**2,
                                        paths=[], clipboard=False, speed=12 * 1024**2), persist=False)
        window.stack.setCurrentIndex(3)
        app.processEvents()
        window.grab().save(str(args.output / 'sharing-progress.png'))
        for name, changes in [("offline", dict(connected=False, peer_name="", peer_available=False)),
                              ("locked", dict(game=True, manual_game=True)),
                              ("permissions", dict(ready=False, error=tr('需要辅助功能和输入监控权限；授权后点击重新检查')))]:
            window.stack.setCurrentIndex(0)
            window.show_status({**state, **changes})
            app.processEvents()
            window.grab().save(str(args.output / f"{name}.png"))
        for side in ("top", "bottom", "right"):
            settings.set(side=side)
            window.show_status(state)
            app.processEvents()
            window.grab().save(str(args.output / f"direction-{side}.png"))
        session = SimpleNamespace(peer_name="Windows Desktop", code="482913", approve=lambda ok: None,
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
        window.device_name.setText("My MacBook")
        app.processEvents()
        window.grab().save(str(args.output / "settings-unsaved.png"))
        icon_image(512).save(str(args.output / "icon.png"))
        icon_image(32, True).save(str(args.output / "tray.png"))
        stage = QWidget()
        stage.setObjectName('sampleDesktop')
        stage.resize(1200, 800)
        stage.setStyleSheet('QWidget#sampleDesktop {background:#edf2f3;} QFrame#card {background:#ffffff;}')
        scene = QHBoxLayout(stage)
        scene.setContentsMargins(110, 180, 290, 180)
        sample, files = card('Project files', 'Sample desktop · Local files')
        files.addSpacing(20)
        for filename, size in [('Designs.pdf', '8.2 MiB'), ('Photos', '24 items'), ('Notes.txt', '4 KiB')]:
            row = QHBoxLayout()
            row.addWidget(text_label(filename, 'section'), 1)
            row.addWidget(text_label(size, 'hint'))
            files.addLayout(row)
            files.addSpacing(12)
        files.addStretch()
        scene.addWidget(sample)
        drop = DropVisual(stage)
        drop.set_context('Windows Desktop', 3, 'Designs.pdf · Photos · Notes.txt', state='hover')
        stage.show()
        for side in ('left', 'right', 'top', 'bottom'):
            drop.set_edge(side)
            drop.setGeometry(hint_geometry(stage.rect(), side, QPoint(600, 400)))
            drop.show()
            drop.motion.stop()  # Deterministic sample still; the live hint animates.
            app.processEvents()
            stage.grab().save(str(args.output / f'drop-{side}.png'))
            if side == 'right':
                stage.grab().save(str(args.output / 'drop-overlay.png'))
        stage.close()
        window.shutdown()
    print(f"Rendered UI previews to {args.output}")


if __name__ == "__main__":
    main()
