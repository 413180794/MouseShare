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


def test_unsaved_changes_return_after_successful_save_and_survive_network_notice(window, app):
    assert not any(button.isEnabled() for button in window.save_buttons)
    window.device_name.setText("Saved name")
    assert all(button.isEnabled() for button in window.save_buttons)
    window.save_settings()
    assert all(label.text() == "所有更改已保存" for label in window.saved_labels)
    assert not any(button.isEnabled() for button in window.save_buttons)
    window.device_name.setText("Unsaved name")
    window.notice("对方已断开连接")
    assert window.settings.get("name") == "Saved name"
    assert all(label.text() == "有未保存的更改" for label in window.saved_labels)
    assert all(button.isEnabled() for button in window.save_buttons)
    # Returning the form to its saved values clears the pending state.
    window.device_name.setText("Saved name")
    assert not any(button.isEnabled() for button in window.save_buttons)
    window.games.setText("another-game.exe")
    assert all(label.text() == "有未保存的更改" for label in window.saved_labels)


@pytest.mark.parametrize("changes,expected", [
    ({"ready": False}, "权限设置"),
    ({"game": True}, "游戏保护中"),
    ({"paused": True}, "共享已暂停"),
    ({"connected": False}, "连接另一台电脑"),
    ({"peer_available": False}, "对方暂不可用"),
    ({"system_blocked": True}, "恢复桌面"),
])
def test_blocked_home_prompts_next_action_instead_of_crossing_edge(window, changes, expected):
    state = dict(state="local", ready=True, connected=True, peer_name="Paired PC", peer_available=True,
                 game=False, manual_game=False, auto_reason="", paused=False, error="")
    window.show_status({**state, **changes})
    assert expected in window.edge_hint.text()
    assert "180 ms" not in window.edge_hint.text()
    assert window.permission_cta.isHidden() == changes.get("ready", True)


def test_permission_entry_opens_reusable_guide_without_native_prompt(window, app):
    window.check_permissions()
    guide = window.permission_guide
    assert guide.isVisible()
    window.check_permissions()
    assert window.permission_guide is guide
    guide.close()
    assert not guide.timer.isActive()


def test_sharing_preferences_apply_without_touching_pairing_and_form(window, app):
    panel = window.share_panel
    saved = window.settings.get('peers')
    panel.clipboard_enabled.setChecked(False)
    panel.auto_receive.setChecked(True)
    assert window.settings.get('clipboard_sync') is False
    assert window.settings.get('auto_receive_files') is True
    assert window.settings.get('peers') == saved
    assert window.form_values() == window.saved_form
    window.stack.setCurrentIndex(3)
    window.resize(940, 720)
    window.show()
    app.processEvents()
    assert panel.isVisible() and panel.directory.isReadOnly()


def test_transfer_history_keeps_completed_metadata_and_clear_preserves_files(window, app, tmp_path):
    path = tmp_path / 'received.txt'
    path.write_text('keep me')
    panel = window.share_panel
    event = dict(type='transfer', job='example', direction='receive', title=path.name,
                 status='complete', detail='校验通过', total=7, done=7, paths=[str(path)], clipboard=False)
    panel.transfer(event)
    assert panel.history_path.exists()
    assert path.exists() and 'example' in panel.rows
    panel.clear_history()
    assert path.read_text() == 'keep me' and not panel.rows


def test_progress_updates_keep_cancel_target_and_fit_minimum_window(window, app):
    panel = window.share_panel
    window.stack.setCurrentIndex(3)
    window.resize(940, 720)
    event = dict(type='transfer', job='busy', direction='send', title='long-name-' * 20,
                 status='transferring', detail='传输中', total=1000, done=1, paths=[], clipboard=False)
    panel.transfer(event)
    window.show()
    app.processEvents()
    row = panel.rows['busy']
    cancel = row[4].itemAt(0).widget()
    for amount in range(100, 900, 100):
        panel.transfer({**event, 'done': amount})
        app.processEvents()
        assert row[4].itemAt(0).widget() is cancel
    assert panel.width() <= window.stack.width()
    assert panel.files_enabled.height() >= panel.files_enabled.minimumSizeHint().height()


def test_drag_layout_snaps_rejects_overlap_and_keeps_unsaved_remote_draft(window, app):
    from PySide6.QtCore import QPointF
    from mouseshare.topology import Rect
    editor = window.layout_editor
    local, remote = window.identity.id, 'a'*64
    editor.nodes = {local: Rect(0, 0, 320, 180).data(), remote: Rect(320, 0, 320, 180).data()}
    editor.rebuild()
    item = editor.items[remote]
    item.setPos(327, 65)
    editor.finish_drag(item, QPointF(320, 0))
    assert editor.nodes[remote]['x'] == 320 and editor.nodes[remote]['y'] == 65
    item.setPos(100, 0)
    editor.finish_drag(item, QPointF(320, 65))
    assert item.pos() == QPointF(320, 65) and editor.nodes[remote]['x'] == 320
    editor.save_layout()
    queued = window.engine.events[-1]
    assert queued['action'] == 'layout' and queued['layout']['nodes'][remote]['y'] == 65
    editor.applied(dict(queued['layout'], author=remote, revision=8))
    assert editor.dirty and '草稿保留' in editor.feedback.text()
    editor.applied(queued['layout'])
    assert not editor.dirty
    assert window.nav_group.button(4).text() == '屏幕布局'
