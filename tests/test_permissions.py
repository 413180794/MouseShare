"""Permission guidance never confuses an OS prompt, a grant and a working input tap."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from mouseshare.permissions import PermissionGuide
from mouseshare.ui import apply_theme


class Backend:
    def __init__(self):
        self.grants = {"accessibility": False, "input_monitoring": False}
        self.requests = []
        self.running = False

    def permission_status(self):
        return self.grants.copy()

    def request_permission(self, kind):
        self.requests.append(kind)

    def ready(self):
        return self.running


@pytest.fixture
def guide():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    backend, retries = Backend(), []
    dialog = PermissionGuide(backend, lambda: retries.append(True), platform="darwin")
    yield dialog, backend, retries
    dialog.close()


def test_native_request_only_for_selected_missing_permission_then_opens_specific_settings(guide, monkeypatch):
    dialog, backend, _ = guide
    urls = []
    monkeypatch.setattr("mouseshare.permissions.QDesktopServices.openUrl",
                        lambda url: urls.append(url.toString()) or True)
    dialog.open_permission("input_monitoring")
    assert backend.requests == ["input_monitoring"]
    assert urls[-1].endswith("?Privacy_ListenEvent")
    # Opening settings alone cannot mark the permission granted.
    assert dialog.rows["input_monitoring"][0].text() == "待开启"
    backend.grants["accessibility"] = True
    dialog.open_permission("accessibility")
    assert backend.requests == ["input_monitoring"]
    assert urls[-1].endswith("?Privacy_Accessibility")


def test_polling_grants_restarts_listener_once_and_waits_for_actual_backend_readiness(guide):
    dialog, backend, retries = guide
    backend.grants["accessibility"] = True
    dialog.refresh()
    assert "1 / 2" in dialog.summary.text()
    assert retries == []
    backend.grants["input_monitoring"] = True
    dialog.refresh()
    dialog.refresh()
    assert retries == [True]
    assert dialog.done_button.text() == "稍后设置"
    backend.running = True
    dialog.refresh()
    assert dialog.done_button.text() == "完成"
    assert "已就绪" in dialog.summary.text()


def test_failed_settings_open_retains_exact_manual_path(guide, monkeypatch):
    dialog, _, _ = guide
    monkeypatch.setattr("mouseshare.permissions.QDesktopServices.openUrl", lambda url: False)
    dialog.open_permission("accessibility")
    assert "系统设置 → 隐私与安全性 → 辅助功能" in dialog.feedback.text()


def test_recheck_does_not_prompt_for_privileges_or_report_grant_from_os_switch_alone(guide):
    dialog, backend, retries = guide
    dialog.recheck()
    assert backend.requests == [] and retries == []
    assert "退出并重新打开" in dialog.feedback.text()
    assert dialog.done_button.text() == "稍后设置"


def test_windows_guide_has_no_mac_permission_steps():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    backend, retries = Backend(), []
    dialog = PermissionGuide(backend, lambda: retries.append(True), platform="win32")
    try:
        assert dialog.rows == {}
        dialog.recheck()
        assert retries == [True] and backend.requests == []
        backend.running = True
        dialog.refresh()
        assert dialog.done_button.text() == "完成"
    finally:
        dialog.close()
