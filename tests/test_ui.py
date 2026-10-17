"""UI reorganizations must preserve saved pairing and all sharing controls."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from mouseshare.app import MainWindow
from mouseshare.config import Settings
from mouseshare.security import Identity
from mouseshare.ui import apply_theme


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance)
    yield instance


@pytest.fixture
def window(app, tmp_path):
    settings = Settings(tmp_path)
    settings.set(peers={"a" * 64: {"name": "Paired PC", "host": "192.168.1.20", "port": 24872}})
    window = MainWindow(settings, Identity(tmp_path), demo=True)
    yield window
    window.shutdown()
    window.close()


def test_settings_save_keeps_pairing_and_all_options(window, app):
    paired = window.settings.get("peers").copy()
    window.stack.setCurrentIndex(1)
    window.device_name.setText("My desktop")
    window.side.setCurrentIndex(window.side.findData("top"))
    window.dwell.setValue(300)
    window.speed.setValue(1.5)
    window.swap.setChecked(True)
    window.games.setText("game.exe; another.exe")
    window.save_settings()
    saved = Settings(window.settings.directory)
    assert saved.get("name") == "My desktop"
    assert saved.get("side") == "top" and saved.get("dwell_ms") == 300
    assert saved.get("sensitivity") == 1.5 and saved.get("swap_ctrl_meta")
    assert saved.get("game_processes") == ["game.exe", "another.exe"]
    assert saved.get("peers") == paired
    # Validation feedback remains visible on settings/game pages.
    window.device_name.setText("")
    window.save_settings()
    assert all("有效" in label.text() for label in window.saved_labels)


def test_game_and_recovery_controls_keep_engine_commands(window, app):
    state = dict(state="local", ready=True, connected=True, peer_name="Paired PC", peer_available=True,
                 game=True, manual_game=True, auto_reason="", paused=False, error="")
    window.show_status(state)
    assert window.game_button.isChecked() and window.game_page_button.isChecked()
    window.game_page_button.clicked.emit()
    window.pause_button.clicked.emit()
    assert [event["action"] for event in window.engine.events] == ["game", "pause"]
    window.show_status({**state, "game": False, "manual_game": False, "paused": True})
    assert not window.game_button.isChecked() and not window.game_page_button.isChecked()
    assert window.pause_button.text() == "恢复共享"
    window.resize(940, 720)
    window.stack.setCurrentIndex(1)
    window.show()
    app.processEvents()
    footer = window.saved_labels[0].parentWidget()
    assert footer.isVisible() and footer.geometry().bottom() < window.stack.height()


def test_discovery_updates_preserve_selected_accessible_device(window, app):
    peer_id = "a" * 64
    window.refresh_peers()
    button = window.peer_buttons[peer_id]
    window.found_peer(dict(id=peer_id, name="Renamed PC", host="192.168.1.30", port=24872,
                           os="Windows", seen=time.monotonic()))
    for _ in range(3):
        window.refresh_peers()
        app.processEvents()
        assert window.peer_buttons[peer_id] is button
        assert window.selected_id() == peer_id
    assert "Renamed PC" in button.text() and "192.168.1.30" in button.text()
    assert "Renamed PC" in button.accessibleName()
    other = "b" * 64
    window.found_peer(dict(id=other, name="Temporary PC", host="192.168.1.40", port=24872,
                           os="Windows", seen=time.monotonic()))
    window.peers[other]["seen"] -= 10
    window.refresh_peers()
    assert len(window.peer_buttons) == 1 and window.selected_id() == peer_id
    assert window.peer_buttons[peer_id] is button
