"""Locale coverage, content boundaries and live switching without input restarts."""
import ast
import json
import os
import re
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit

from mouseshare.app import MainWindow
from mouseshare.config import Settings
from mouseshare.i18n import language, resolve_language, set_language, tr
from mouseshare.i18n_widgets import retranslate_widgets
from mouseshare.permissions import PermissionGuide
from mouseshare.security import Identity
from mouseshare.ui import apply_theme

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile('[\u3400-\u9fff]')


@pytest.mark.parametrize(('preference', 'system', 'expected'), [
    ('system', 'zh_CN', 'zh_CN'), ('system', 'zh-TW', 'zh_CN'), ('system', 'en_US', 'en'),
    ('system', 'de_DE', 'en'), ('en', 'zh_CN', 'en'), ('zh_CN', 'en_US', 'zh_CN'),
    ('invalid', 'fr_FR', 'en'),
])
def test_locale_resolution(preference, system, expected):
    assert resolve_language(preference, system) == expected


def test_catalog_is_complete_and_placeholders_match():
    catalog = json.loads((ROOT/'mouseshare/locales/en.json').read_text())
    sources = set()
    for path in (ROOT/'mouseshare').rglob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr':
                if node.args and isinstance(node.args[0], ast.Constant) and HAN.search(str(node.args[0].value)):
                    sources.add(node.args[0].value)
    assert sources <= catalog.keys(), sources-catalog.keys()
    def fields(text):
        return {name for _, name, _, _ in Formatter().parse(text) if name is not None}
    for source, english in catalog.items():
        assert english and not HAN.search(english), source
        assert fields(source) == fields(english), source


def test_nested_messages_retranslate_without_touching_parameter_content():
    name = '文件：复制文件 {keep me} 中文.exe'
    message = tr('本机 {p0}；对方 {p1} 位于{p2}', p0=name, p1='My PC', p2=tr('左侧'))
    set_language('en')
    assert message.render() == f'This computer: {name}; My PC is on the left'
    assert (message + ' / ' + name).render().endswith(name)
    assert name in message.render()


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def english_window(app, tmp_path):
    settings = Settings(tmp_path)
    settings.set(language='en', name='中文设备 Preferences.txt')
    window = MainWindow(settings, Identity(tmp_path), demo=True)
    yield window
    window.shutdown()
    window.close()
    app.processEvents()


def visible_text(root):
    for widget in root.findChildren(QLabel) + root.findChildren(QAbstractButton):
        yield widget, widget.text()
    for widget in root.findChildren(QLineEdit):
        yield widget, widget.placeholderText()
    for widget in root.findChildren(QComboBox):
        for index in range(widget.count()):
            yield widget, widget.itemText(index)


def test_all_pages_english_and_user_names_stay_literal(english_window, app):
    window = english_window
    assert language() == 'en'
    assert window.nav_group.button(1).text() == 'Preferences'
    assert window.device_name.text() == '中文设备 Preferences.txt'
    for index in range(5):
        window.stack.setCurrentIndex(index)
        window.resize(940, 720)
        window.show()
        app.processEvents()
        for widget, text in visible_text(window.stack.currentWidget()):
            if text == '中文设备 Preferences.txt':
                continue  # User-authored names in the layout selector stay literal.
            if widget is window.language_choice:
                assert text in ('System default', '简体中文', 'English')
            else:
                assert not HAN.search(text), (index, text)
        for button in window.stack.currentWidget().findChildren(QAbstractButton):
            if button.isVisible() and button.text():
                assert button.width() >= button.sizeHint().width()-2, button.text()
    tray_text = [action.text() for action in window.tray.contextMenu().actions()]
    assert 'Quit' in tray_text and all(not HAN.search(text) for text in tray_text)


@pytest.mark.parametrize('platform', ['darwin', 'win32', 'linux'])
def test_permission_instructions_follow_app_language(app, platform):
    set_language('en')
    backend = SimpleNamespace(permission_status=lambda: dict(accessibility=False, input_monitoring=False),
                              ready=lambda: False, error='', request_permission=lambda kind: None)
    dialog = PermissionGuide(backend, lambda: None, platform=platform, demo=True)
    try:
        assert not HAN.search(dialog.windowTitle())
        assert all(not HAN.search(text) for _, text in visible_text(dialog))
        if platform == 'darwin':
            dialog.open_permission('accessibility')
            assert 'Accessibility' in dialog.feedback.text()
            assert dialog.rows['input_monitoring'][1].text() == 'Enable Input Monitoring'
        set_language('zh_CN')
        retranslate_widgets()
        dialog.refresh()
        assert HAN.search(dialog.windowTitle())
    finally:
        dialog.close()


def test_switch_preserves_connections_transfers_drafts_and_selection(english_window, app):
    window = english_window
    services = (window.engine, window.backend, window.network, window.sharing, window.layout_editor)
    window.device_name.setText('未保存的设备名称')
    window.speed.setValue(2.5)
    node = window.layout_editor.nodes[window.identity.id]
    node['x'] = 55
    window.layout_editor.mark_dirty()
    job = object()
    window.sharing.jobs['active'] = job
    window.stack.setCurrentIndex(1)
    draft = window.form_values()
    window.language_choice.setCurrentIndex(window.language_choice.findData('zh_CN'))
    assert window.nav_group.button(1).text() == '共享设置'
    assert window.device_name.text() == '未保存的设备名称'
    assert window.form_values() == draft
    assert window.layout_editor.nodes[window.identity.id]['x'] == 55
    assert window.layout_editor.dirty
    assert window.sharing.jobs['active'] is job
    assert services == (window.engine, window.backend, window.network, window.sharing, window.layout_editor)
    assert not window.engine.events
    assert window.stack.currentIndex() == 1
    assert Settings(window.settings.directory).get('language') == 'zh_CN'
    assert Settings(window.settings.directory).get('name') == '中文设备 Preferences.txt'
    window.language_choice.setCurrentIndex(window.language_choice.findData('en'))
    assert window.nav_group.button(1).text() == 'Preferences'
    assert 'Unsaved' in window.saved_labels[0].text()
    assert all(not HAN.search(action.text()) for action in window.findChildren(QAction))
    window.sharing.jobs.clear()


def test_old_transfer_status_translates_but_filename_does_not(english_window, app):
    window = english_window
    window.share_panel.transfer(dict(job='history', direction='receive', title='复制文件',
                                    detail='接收完成，SHA-256 校验通过', done=1, total=1, paths=[],
                                    status='complete'), persist=False)
    row = window.share_panel.rows['history']
    assert row[1].text() == 'Receiving · 复制文件'
    assert row[2].text().startswith('Received; SHA-256 verification passed')
    window.language_choice.setCurrentIndex(window.language_choice.findData('zh_CN'))
    assert row[1].text() == '接收 · 复制文件'
    assert row[2].text().startswith('接收完成，SHA-256 校验通过')
