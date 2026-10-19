"""Native file drop/copy surfaces and a transfer inbox; no input-hook work here."""
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDrag
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLayout,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
)

from .clipboard import files_mime, wayland_session
from .i18n import exception_text, status_message, tr
from .i18n_widgets import QCheckBox, QComboBox, QFrame, QLineEdit, QPushButton, QWidget
from .ui import card, text_label


def size_text(value):
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if value < 1024 or unit == 'GiB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{value} B'
        value /= 1024


class DropZone(QFrame):
    files = Signal(list)

    def __init__(self, label=tr('把文件或文件夹拖到这里，发送到另一台电脑'), parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        self.label = text_label(label, 'section', True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setMinimumHeight(80)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            self.files.emit([url.toLocalFile() for url in urls])
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()


class DragFiles(QPushButton):
    def __init__(self, paths, parent=None):
        super().__init__(tr('拖出文件'), parent)
        self.paths = paths
        self.start = None
        self.setToolTip(tr('按住拖到 Finder、资源管理器或支持文件拖放的应用'))

    def mousePressEvent(self, event):
        self.start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.start is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self.start).manhattanLength() >= QApplication.startDragDistance()):
            self.setDown(False)
            drag = QDrag(self)
            drag.setMimeData(files_mime(self.paths, mark=False))
            self.start = None
            drag.exec(Qt.DropAction.CopyAction)
        else:
            super().mouseMoveEvent(event)


class SharePanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window, self.service = window, window.sharing
        self.rows, self.events, self.clip_generations = {}, {}, {}
        self.history_path = window.settings.directory / 'transfers.json'
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.status = text_label(tr('连接后同步新复制的内容；旧剪贴板保留在本机。'), 'hint', True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(text_label(tr('最近传输'), 'section'), 1)
        clear = QPushButton(tr('清空记录'))
        clear.clicked.connect(self.clear_history)
        row.addWidget(clear)
        layout.addLayout(row)
        self.records = QVBoxLayout()
        self.records.setSpacing(10)
        layout.addLayout(self.records)
        self.empty = text_label(tr('还没有传输记录。'), 'hint')
        layout.addWidget(self.empty)
        box, body = card(tr('剪贴板'), tr('在一台电脑复制，在另一台电脑粘贴。'))
        self.clipboard_enabled = QCheckBox(tr('开启剪贴板共享（文字与富文本）'))
        self.clipboard_images = QCheckBox(tr('同步截图和图片'))
        self.clipboard_files = QCheckBox(tr('共享文件剪贴板：粘贴时传输文件'))
        self.native_paste = QCheckBox(tr('支持系统粘贴键：Windows／Linux Ctrl+V，Mac ⌘V'))
        self.prefetch = QCheckBox(tr('预先接收文件，让系统右键「粘贴」可用（每次最多 64 MiB）'))
        self.prefetch.setChecked(window.settings.get('file_clipboard_prefetch', False))
        self.prefetch.toggled.connect(lambda value: self.preference('file_clipboard_prefetch', value))
        for checkbox, key in [(self.clipboard_enabled, 'clipboard_sync'), (self.clipboard_images, 'clipboard_images'),
                              (self.clipboard_files, 'clipboard_files'), (self.native_paste, 'native_file_paste')]:
            checkbox.setChecked(window.settings.get(key, True))
            checkbox.toggled.connect(lambda value, k=key: self.preference(k, value))
            body.addWidget(checkbox)
        body.addWidget(self.prefetch)
        body.addWidget(text_label(tr('专用快捷键：Ctrl+Alt+C 复制，Ctrl+Alt+V 粘贴；原四键快捷键也可用。Mac 使用 Control+Option+C／V。Ctrl+Alt+空格切换到所选电脑，再按一次收回。'), 'hint', True))
        body.addWidget(text_label(tr('右键粘贴需先收到完整文件。预接收会使用网络和磁盘；大文件请使用共享粘贴键按需接收。'), 'hint', True))
        if sys.platform == 'win32' or sys.platform.startswith('linux'):
            self.context_menu = QCheckBox(tr('在文件管理器右键菜单加入「接收文件到此处（MouseShare）」'))
            self.context_menu.setChecked(window.settings.get('file_context_menu', False))
            self.context_menu.toggled.connect(self.toggle_context_menu)
            body.addWidget(self.context_menu)
            body.addWidget(text_label(tr('Windows 11 位于「显示更多选项」。Ubuntu GNOME 需安装 python3-nautilus 并重新打开文件管理器。文件存入所选目录下的独立文件夹。'), 'hint', True))
        self.clipboard_images.setEnabled(self.clipboard_enabled.isChecked())
        self.clipboard_files.setEnabled(self.clipboard_enabled.isChecked())
        actions = QHBoxLayout()
        sync = QPushButton(tr('同步当前剪贴板'))
        sync.clicked.connect(lambda: window.clipboard_sync.send_current() if window.clipboard_sync else None)
        actions.addWidget(sync)
        if wayland_session():
            apply = QPushButton(tr('应用收到的剪贴板'))
            apply.clicked.connect(lambda: window.clipboard_sync.apply_pending() if window.clipboard_sync else None)
            actions.addWidget(apply)
            body.addWidget(text_label(tr('Wayland 会话使用前台手动同步；X11 会话可自动同步。'), 'hint', True))
        body.addLayout(actions)
        layout.addWidget(box)
        box, body = card(tr('文件传输'), tr('文件与文件夹均以副本发送，接收后校验完整性。'))
        self.files_enabled = QCheckBox(tr('开启文件共享'))
        self.files_enabled.setChecked(window.settings.get('file_sharing', True))
        self.files_enabled.toggled.connect(lambda value: self.preference('file_sharing', value))
        body.addWidget(self.files_enabled)
        self.auto_receive = QCheckBox(tr('自动接收已配对电脑的文件'))
        self.auto_receive.setChecked(window.settings.get('auto_receive_files', False))
        self.auto_receive.toggled.connect(lambda value: self.preference('auto_receive_files', value))
        body.addWidget(self.auto_receive)
        self.portal_enabled = QCheckBox(tr('拖文件到边缘时显示柔和毛玻璃提示'))
        self.portal_enabled.setChecked(window.settings.get('edge_drop', False))
        self.portal_enabled.toggled.connect(lambda value: self.preference('edge_drop', value))
        body.addWidget(self.portal_enabled)
        preview = QPushButton(tr('预览投递效果 · 3 秒'))
        preview.clicked.connect(lambda: window.edge_portal.preview())
        body.addWidget(preview)
        body.addWidget(text_label(tr('平时隐藏；拖文件到相邻电脑的边缘后展开。松手提交，Esc 取消，传输在后台继续。'), 'hint', True))
        self.recipient = QComboBox()
        self.recipient.setAccessibleName(tr('文件发送目标'))
        body.addWidget(text_label(tr('文件发送目标'), 'hint'))
        body.addWidget(self.recipient)
        self.drop = DropZone()
        self.drop.files.connect(self.send)
        body.addWidget(self.drop)
        row = QHBoxLayout()
        for title, action in [(tr('选择文件'), self.choose_files), (tr('选择文件夹'), self.choose_directory),
                              (tr('发送已复制的文件'), self.send_copied)]:
            button = QPushButton(title)
            button.clicked.connect(action)
            row.addWidget(button)
        body.addLayout(row)
        row = QHBoxLayout()
        self.directory = QLineEdit(str(self.receive_directory()))
        self.directory.setReadOnly(True)
        self.directory.setAccessibleName(tr('接收目录'))
        row.addWidget(self.directory, 1)
        change = QPushButton(tr('更改目录'))
        change.clicked.connect(self.choose_destination)
        row.addWidget(change)
        open_folder = QPushButton(tr('打开'))
        open_folder.clicked.connect(self.open_destination)
        row.addWidget(open_folder)
        body.addLayout(row)
        body.addWidget(text_label(tr('每批保存到独立文件夹，保留同名文件。单次最多 100 GiB／4096 项。'), 'hint', True))
        layout.addWidget(box)
        try:
            history = json.loads(self.history_path.read_text())
            if isinstance(history, list):
                for event in history[:20]:
                    if isinstance(event, dict) and event.get('status') in {'complete', 'error', 'cancelled', 'rejected'}:
                        self.transfer(event, persist=False)
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def update_recipients(self):
        selected = self.recipient.currentData()
        blocker = QSignalBlocker(self.recipient)
        self.recipient.clear()
        self.recipient.addItem(tr('当前控制／选中的电脑'), '')
        for key, session in list(self.window.network.sessions.items()):
            if session.connected and 'sharing-v1' in getattr(session, 'peer_features', []):
                self.recipient.addItem(session.peer_name, key)
        self.recipient.setCurrentIndex(max(0, self.recipient.findData(selected)))
        del blocker

    def toggle_context_menu(self, enabled):
        from .context_menu import set_enabled
        try:
            set_enabled(enabled)
            self.window.settings.set(file_context_menu=enabled)
            self.status.setText(tr('右键扩展已更新，请重新打开文件管理器'))
        except OSError as exc:
            blocker = QSignalBlocker(self.context_menu)
            self.context_menu.setChecked(not enabled)
            del blocker
            self.window.notice(exception_text(exc))

    def preference(self, key, value):
        self.window.settings.set(**{key: value})
        if key == 'file_sharing' and not value:
            self.service.cancel_files()
        if key == 'clipboard_sync' and not value:
            self.service.cancel_clipboard()
        if key == 'clipboard_sync':
            self.clipboard_images.setEnabled(value)
            self.clipboard_files.setEnabled(value)
        self.status.setText(tr('共享偏好已保存'))
        self.drop.setEnabled(self.window.sharing_allowed('files') and self.window.settings.get('file_sharing', True))

    def receive_directory(self):
        return Path(self.window.settings.get('receive_directory') or Path.home() / 'Downloads' / 'MouseShare')

    def open_destination(self):
        try:
            directory = self.receive_directory()
            directory.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        except OSError as exc:
            self.status.setText(exception_text(exc))

    def choose_destination(self):
        directory = QFileDialog.getExistingDirectory(self, tr('选择接收目录'), str(self.receive_directory()))
        if directory:
            self.window.settings.set(receive_directory=directory)
            self.directory.setText(directory)
            self.status.setText(tr('接收目录已保存；正在接收的任务继续使用原目录'))

    def send(self, paths, clipboard=False):
        if self.window.demo:
            self.status.setText(tr('演示界面：实际传输将在双机连接后启用'))
            return
        try:
            self.service.send_files(paths, clipboard, peer_id=self.recipient.currentData() or None)
        except (OSError, ValueError) as exc:
            self.status.setText(exception_text(exc))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('选择要发送的文件'))
        if paths:
            self.send(paths)

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, tr('选择要发送的文件夹'))
        if path:
            self.send([path])

    def send_copied(self):
        paths = [url.toLocalFile() for url in QApplication.clipboard().mimeData().urls() if url.isLocalFile()]
        if paths:
            self.send(paths, clipboard=True)
        else:
            self.status.setText(tr('请先在 Finder 或资源管理器中复制文件'))

    def transfer(self, event, persist=True):
        key = event['job']
        previous = self.events.get(key)
        self.events[key] = event
        if event['status'] == 'offered' and getattr(self.window, 'clipboard_sync', None):
            self.clip_generations.setdefault(key, self.window.clipboard_sync.sequence())
        if key not in self.rows:
            box, body = card()
            title = text_label('', 'section', True)
            detail = text_label('', 'hint', True)
            title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            progress = QProgressBar()
            progress.setRange(0, 1000)
            buttons = QHBoxLayout()
            body.addWidget(title)
            body.addWidget(detail)
            body.addWidget(progress)
            body.addLayout(buttons)
            self.records.insertWidget(0, box)
            self.rows[key] = (box, title, detail, progress, buttons)
        box, title, detail, progress, buttons = self.rows[key]
        title.setText((tr('发送 · ') if event['direction'] == 'send' else tr('接收 · ')) + event['title'])
        description = status_message(event['detail']) + f"  {size_text(event['done'])} / {size_text(event['total'])}"
        if event['status'] == 'transferring' and event.get('speed'):
            speed = event['speed']
            eta = max(0, int((event['total'] - event['done']) / speed))
            description += tr(' · {p0}/s · 剩余约 {p1} 秒', p0=size_text(speed), p1=eta)
        detail.setText(description)
        progress.setValue(int(event['done'] / max(1, event['total']) * 1000))
        progress.setVisible(event['status'] in {'preparing', 'waiting', 'offered', 'transferring'})
        if previous and previous['status'] == event['status']:
            return  # Keep native action buttons stable while progress updates arrive.
        while buttons.count():
            widget = buttons.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        def button(text, callback):
            item = QPushButton(text)
            item.clicked.connect(callback)
            buttons.addWidget(item)
        status = event['status']
        if status == 'offered':
            button(tr('接收'), lambda: self.service.decide(key, True))
            button(tr('拒绝'), lambda: self.service.decide(key, False))
        elif status in {'preparing', 'waiting', 'transferring'}:
            button(tr('取消'), lambda: self.service.cancel(key))
        elif status in {'error', 'cancelled', 'rejected'} and event['direction'] == 'send' and event.get('paths'):
            button(tr('重新发送'), lambda: self.send(event['paths'], event.get('clipboard', False)))
        elif status == 'complete' and event['direction'] == 'receive' and event.get('paths'):
            paths = event['paths']
            button(tr('打开所在文件夹'), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(paths[0]).parent))))
            button(tr('复制文件'), lambda: self.window.clipboard_sync.copy_files(paths))
            buttons.addWidget(DragFiles(paths))
            if (persist and not wayland_session() and previous and previous['status'] != 'complete' and event.get('clipboard')
                    and not event.get('request')
                    and event.get('peer', '') == getattr(self.window.network.session, 'peer_id', '')
                    and self.window.sharing.enabled('clipboard') and self.window.settings.get('clipboard_files', True)
                    and self.clip_generations.get(key) == self.window.clipboard_sync.sequence()):
                self.window.clipboard_sync.copy_files(paths)
        self.empty.setVisible(not self.rows)
        pending = sum(e['status'] == 'offered' for e in self.events.values())
        self.window.nav_group.button(3).setText(tr('文件待接收 ({p0})', p0=pending) if pending else tr('文件与剪贴板'))
        if persist and status in {'complete', 'error', 'cancelled', 'rejected'}:
            self.save_history()
        for old in list(self.rows)[:-30]:
            if self.events[old]['status'] in {'complete', 'error', 'cancelled', 'rejected'}:
                self.rows.pop(old)[0].deleteLater()
                self.events.pop(old)
        if persist and status == 'offered' and (not previous or previous['status'] != 'offered'):
            self.window.tray.showMessage(tr('收到文件请求'), event['title'] + tr(' · 打开“文件与剪贴板”接收'))
        if persist and status == 'complete' and (not previous or previous['status'] != 'complete'):
            self.window.tray.showMessage(tr('文件传输完成'), event['title'])

    def save_history(self):
        history = [e for e in reversed(list(self.events.values()))
                   if e['status'] in {'complete', 'error', 'cancelled', 'rejected'}][:20]
        try:
            temp = self.history_path.with_suffix('.tmp')
            temp.write_text(json.dumps(history, ensure_ascii=False), encoding='utf-8')
            if os.name != 'nt':
                temp.chmod(0o600)
            temp.replace(self.history_path)
        except OSError:
            self.status.setText(tr('传输记录暂时无法保存'))

    def clear_history(self):
        for key in list(self.rows):
            if self.events[key]['status'] in {'complete', 'error', 'cancelled', 'rejected'}:
                self.rows.pop(key)[0].deleteLater()
                self.events.pop(key)
        self.save_history()
        self.empty.setVisible(not self.rows)
