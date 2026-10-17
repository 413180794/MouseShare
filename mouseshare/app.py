"""Qt desktop control panel. All data-plane input handling runs off the GUI thread."""
import argparse
import ctypes
import os
import platform
import socket
import sys
import time

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import __version__
from .config import Settings
from .engine import Engine
from .input import create_backend
from .network import Discovery, Network
from .security import Identity


class Bridge(QObject):
    pair = Signal(object)
    peer = Signal(dict)
    status = Signal(dict)
    error = Signal(str)


def app_icon():
    pix = QPixmap(128, 128)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#16233c"))
    p.drawRoundedRect(0, 0, 128, 128, 28, 28)
    p.setBrush(QColor("#59d8bb"))
    p.drawRoundedRect(15, 28, 44, 48, 6, 6)
    p.setBrush(QColor("#87b7ff"))
    p.drawRoundedRect(69, 49, 44, 48, 6, 6)
    p.setPen(QPen(QColor("#ffffff"), 5))
    p.drawLine(45, 92, 83, 31)
    p.drawLine(83, 31, 64, 38)
    p.drawLine(83, 31, 86, 51)
    p.end()
    return QIcon(pix)


STYLE = """
QMainWindow, QDialog { background: #101724; color: #edf2fc; }
QWidget { color: #edf2fc; font-size: 13px; }
QFrame#card { background: #1a2538; border: 1px solid #293850; border-radius: 12px; }
QLabel#title { font-size: 29px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #9fafc8; }
QLabel#state { font-size: 20px; font-weight: 600; color: #66dfbf; }
QPushButton { background: #2b3d58; border: 1px solid #415674; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #3b5274; }
QPushButton#primary { background: #70dfc3; color: #102a29; border: 0; font-weight: 700; }
QPushButton#game:checked { background: #ebba66; color: #33240a; }
QPushButton:disabled { color: #64738a; background: #253044; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #101b2d; border: 1px solid #3a4c69;
    border-radius: 5px; padding: 6px; selection-background-color: #365e8d; }
QTableWidget { background: #131e30; gridline-color: #293850; border: 0; border-radius: 6px;
    selection-background-color: #2d4968; }
QHeaderView::section { background: #1a2538; padding: 8px; color: #9fafc8; border: 0; }
QCheckBox { spacing: 9px; }
QMenu { background: #1a2538; border: 1px solid #415674; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #365273; }
"""


def card():
    box = QFrame()
    box.setObjectName("card")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return box, layout


class MainWindow(QMainWindow):
    def __init__(self, settings, identity, demo=False):
        super().__init__()
        self.settings, self.identity, self.demo = settings, identity, demo
        self.peers, self.dialogs = {}, {}
        self.closed = False
        self.bridge = Bridge()
        self.bridge.peer.connect(self.found_peer)
        self.bridge.pair.connect(self.pair_dialog)
        self.bridge.status.connect(self.show_status)
        self.bridge.error.connect(self.notice)
        self.engine = Engine(settings, self.bridge.status.emit)
        self.backend = create_backend(self.engine.enqueue)
        self.engine.backend = self.backend
        self.network = Network(identity, settings, self.bridge.pair.emit,
                               lambda s: self.engine.enqueue({"type": "connected", "session": s}),
                               lambda s, m: self.engine.enqueue({"type": "network", "session": s, "message": m}),
                               self.disconnected, self.bridge.error.emit)
        self.discovery = Discovery(identity, settings, self.bridge.peer.emit, self.bridge.error.emit)
        self.setWindowTitle(f"MouseShare · {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(860, 910)
        self.setMinimumSize(720, 720)
        self.build_ui()
        self.build_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_peers)
        self.timer.start(2000)
        if not demo:
            self.backend.start()
            self.engine.start()
            try:
                self.network.start()
                self.discovery.start()
            except OSError:
                self.notice("共享端口 24872 被占用。请检查是否运行了另一份 MouseShare。")
        else:
            self.show_status({"state": "local", "game": False, "manual_game": False, "auto_reason": "",
                              "paused": False, "connected": False, "peer_available": False,
                              "peer_name": "", "ready": False, "error": "演示界面 · 输入共享未启动"})

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)
        title = QLabel("MouseShare")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("一套键鼠，两台电脑。局域网连接，首次配对后自动重连。")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        box, body = card()
        self.state_label = QLabel("正在启动…")
        self.state_label.setObjectName("state")
        body.addWidget(self.state_label)
        self.detail = QLabel("把鼠标移到屏幕边缘，即可切换控制。")
        self.detail.setWordWrap(True)
        body.addWidget(self.detail)
        row = QHBoxLayout()
        self.game_button = QPushButton("游戏模式")
        self.game_button.setObjectName("game")
        self.game_button.setCheckable(True)
        self.game_button.clicked.connect(lambda: self.engine.command("game"))
        row.addWidget(self.game_button)
        self.pause_button = QPushButton("暂停共享")
        self.pause_button.clicked.connect(lambda: self.engine.command("pause"))
        row.addWidget(self.pause_button)
        take_back = QPushButton("立即收回键鼠")
        take_back.clicked.connect(lambda: self.engine.command("panic"))
        row.addWidget(take_back)
        row.addStretch()
        body.addLayout(row)
        hint = QLabel("全局快捷键   Ctrl + Alt + F12 游戏模式    ·    Ctrl + Alt + Esc 收回键鼠\n"
                      "Mac 使用 Control + Option；部分键盘需要同时按 Fn。")
        hint.setObjectName("hint")
        body.addWidget(hint)
        layout.addWidget(box)

        box, body = card()
        body.addWidget(QLabel("附近的电脑"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["电脑", "系统", "IP 地址", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(110)
        self.table.setMaximumHeight(175)
        self.table.doubleClicked.connect(self.connect_selected)
        body.addWidget(self.table)
        row = QHBoxLayout()
        connect = QPushButton("配对 / 连接所选电脑")
        connect.setObjectName("primary")
        connect.clicked.connect(self.connect_selected)
        row.addWidget(connect)
        forget = QPushButton("取消所选配对")
        forget.clicked.connect(self.forget_selected)
        row.addWidget(forget)
        self.manual_ip = QLineEdit()
        self.manual_ip.setPlaceholderText("或输入对方 IPv4")
        self.manual_ip.returnPressed.connect(self.connect_ip)
        row.addWidget(self.manual_ip)
        manual = QPushButton("连接 IP")
        manual.clicked.connect(self.connect_ip)
        row.addWidget(manual)
        body.addLayout(row)
        self.device_info = QLabel(f"本机：{self.settings.get('name')}  ·  指纹：{self.identity.id[:16]}")
        self.device_info.setObjectName("hint")
        self.device_info.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self.device_info)
        layout.addWidget(box)

        box, body = card()
        form = QFormLayout()
        self.device_name = QLineEdit(self.settings.get("name"))
        self.device_name.setMaxLength(80)
        form.addRow("本机名称", self.device_name)
        row = QHBoxLayout()
        self.side = QComboBox()
        for label, value in [("右侧 →", "right"), ("左侧 ←", "left"), ("上方 ↑", "top"), ("下方 ↓", "bottom")]:
            self.side.addItem(label, value)
        self.side.setCurrentIndex(self.side.findData(self.settings.get("side")))
        row.addWidget(self.side)
        row.addWidget(QLabel("边缘停留"))
        self.dwell = QSpinBox()
        self.dwell.setRange(100, 1500)
        self.dwell.setSuffix(" ms")
        self.dwell.setValue(self.settings.get("dwell_ms"))
        row.addWidget(self.dwell)
        row.addWidget(QLabel("速度"))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 4)
        self.speed.setSingleStep(0.25)
        self.speed.setValue(self.settings.get("sensitivity"))
        row.addWidget(self.speed)
        form.addRow("对方在本机的", row)
        self.fullscreen = QCheckBox("Windows 前台全屏时自动锁住键鼠（全屏视频也会触发）")
        self.fullscreen.setChecked(self.settings.get("auto_fullscreen"))
        form.addRow("自动游戏模式", self.fullscreen)
        self.games = QLineEdit("; ".join(self.settings.get("game_processes")))
        self.games.setPlaceholderText("用分号分隔，例如 League of Legends.exe; cs2.exe")
        form.addRow("游戏进程名", self.games)
        self.swap = QCheckBox("接收输入时交换 Ctrl 与 ⌘ / Win（按个人习惯开启）")
        self.swap.setChecked(self.settings.get("swap_ctrl_meta", False))
        form.addRow("修饰键", self.swap)
        self.startup = QCheckBox("登录电脑后自动启动并驻留托盘")
        self.startup.setChecked(self.settings.get("startup"))
        form.addRow("开机启动", self.startup)
        body.addLayout(form)
        row = QHBoxLayout()
        save = QPushButton("保存设置")
        save.clicked.connect(self.save_settings)
        row.addWidget(save)
        permission = QPushButton("授权 / 重新检查权限")
        permission.clicked.connect(self.check_permissions)
        row.addWidget(permission)
        help_button = QPushButton("安装与使用说明")
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/413180794/MouseShare/blob/main/README.md")))
        row.addWidget(help_button)
        row.addStretch()
        body.addLayout(row)
        layout.addWidget(box)
        self.notice_label = QLabel("两台电脑需处于同一局域网。macOS 需要辅助功能及输入监控权限。")
        self.notice_label.setWordWrap(True)
        self.notice_label.setObjectName("hint")
        self.notice_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice_label)
        layout.addStretch()

    def build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("MouseShare")
        menu = QMenu()
        show = QAction("打开 MouseShare", self)
        show.triggered.connect(self.show_normal)
        menu.addAction(show)
        game = QAction("切换游戏模式 · Ctrl+Alt+F12", self)
        game.triggered.connect(lambda: self.engine.command("game"))
        menu.addAction(game)
        release = QAction("立即收回键鼠 · Ctrl+Alt+Esc", self)
        release.triggered.connect(lambda: self.engine.command("panic"))
        menu.addAction(release)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda why: self.show_normal()
                                   if why == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def notice(self, text):
        self.notice_label.setText(text)

    def show_status(self, state):
        self.game_button.setChecked(state["manual_game"])
        self.pause_button.setText("恢复共享" if state["paused"] else "暂停共享")
        peer = state["peer_name"]
        if not state["ready"]:
            title, detail = "等待系统授权", state["error"] or "请点击下方按钮检查权限。"
        elif state["game"]:
            title, detail = "游戏模式 · 键鼠锁定本机", state["auto_reason"] or "手动游戏模式已开启；再次按快捷键即可关闭。"
        elif state["paused"]:
            title, detail = "共享已暂停", state["error"] or "点击恢复共享继续。"
        elif state["state"] == "sending":
            title, detail = "正在控制另一台电脑", f"键鼠输出到 {peer}。从对方屏幕原路返回即可收回。"
        elif state["state"] == "receiving":
            title, detail = "正在接收远端键鼠", f"由 {peer} 控制。操作本机实体键鼠可立即收回。"
        elif state["connected"]:
            title = "已连接 · 本机控制中"
            detail = f"已连接 {peer}。" + ("把鼠标移到设定边缘并稍作停留即可跨屏。" if state["peer_available"]
                                         else "对方已暂停共享、开启游戏模式或等待授权。")
        else:
            title, detail = "等待连接", "启动另一台电脑上的 MouseShare，然后在下方选择电脑进行配对。"
        self.state_label.setText(title)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setText(detail)
        self.tray.setToolTip(f"MouseShare · {title}")

    def found_peer(self, peer):
        if len(self.peers) < 64 or peer["id"] in self.peers:
            peer["seen"] = time.monotonic()
            self.peers[peer["id"]] = peer
        # Deterministic dialer prevents simultaneous automatic connection attempts.
        if (peer["id"] in self.settings.get("peers") and self.identity.id < peer["id"]
                and not self.network.session and not self.demo):
            self.network.connect(peer["host"], peer["port"], peer["id"])
        self.refresh_peers()

    def refresh_peers(self):
        selected = self.selected_id()
        trusted = self.settings.get("peers")
        rows = {key: dict(value, id=key, os="", seen=0) for key, value in trusted.items()}
        rows.update({key: peer for key, peer in self.peers.items()
                     if time.monotonic() - peer["seen"] < 8})
        self.row_ids = list(rows)
        self.table.setRowCount(len(rows))
        for row, (peer_id, peer) in enumerate(rows.items()):
            status = "已配对" if peer_id in trusted else "待配对"
            session = self.network.session
            if session and session.peer_id == peer_id:
                status = "已连接" if session.connected else "连接中"
            elif not peer.get("seen"):
                status = "离线 · 已配对"
            for column, value in enumerate([peer.get("name", "电脑"),
                                            {"Darwin": "macOS", "Windows": "Windows"}.get(peer.get("os"), "—"),
                                            peer.get("host", ""), status]):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
            if peer_id == selected:
                self.table.selectRow(row)
        for key in list(self.dialogs):
            if self.dialogs[key][1].stopped.is_set():
                self.dialogs[key][0].reject()

    def selected_id(self):
        row = self.table.currentRow() if hasattr(self, "table") else -1
        return self.row_ids[row] if hasattr(self, "row_ids") and 0 <= row < len(self.row_ids) else None

    def connect_selected(self):
        peer_id = self.selected_id()
        if not peer_id:
            self.notice("请先在列表中选择一台电脑。")
            return
        peer = self.peers.get(peer_id) or self.settings.get("peers").get(peer_id)
        if self.network.session:
            self.notice("当前已有连接或配对请求。可先取消配对，或等待连接结束。")
            return
        self.notice("正在连接；首次连接请在两台电脑上核对配对码。")
        if not self.demo:
            self.network.connect(peer["host"], peer.get("port", 24872), peer_id)

    def connect_ip(self):
        host = self.manual_ip.text().strip()
        try:
            socket.inet_pton(socket.AF_INET, host)
        except OSError:
            self.notice("请输入有效的 IPv4 地址，例如 192.168.1.20。")
            return
        if not self.demo:
            self.network.connect(host)

    def forget_selected(self):
        peer_id = self.selected_id()
        if not peer_id:
            return
        self.settings.forget(peer_id)
        if self.network.session and self.network.session.peer_id == peer_id:
            self.network.session.stop()
        self.refresh_peers()
        self.notice("配对已取消。下次连接将重新核对配对码。")

    def pair_dialog(self, session):
        dialog = QDialog(self)
        dialog.setWindowTitle("核对两台电脑的配对码")
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        name = QLabel(f"请求连接：{session.peer_name}")
        name.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(name)
        code = QLabel(f"{session.code[:3]}  {session.code[3:]}")
        code.setStyleSheet("font-size: 48px; font-weight: 700; color: #70dfc3; padding: 18px;")
        code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(code)
        label = QLabel("请确认两台电脑显示相同的六位数字，再在两端点击确认。\n配对成功后，对方可以在共享开启时控制本机键鼠。")
        layout.addWidget(label)
        row = QHBoxLayout()
        reject = QPushButton("拒绝")
        accept = QPushButton("两端数字相同，确认配对")
        accept.setObjectName("primary")
        row.addWidget(reject)
        row.addWidget(accept)
        layout.addLayout(row)
        accept.clicked.connect(dialog.accept)
        reject.clicked.connect(dialog.reject)
        key = id(session)
        self.dialogs[key] = dialog, session

        def finished(result):
            session.approve(result == QDialog.DialogCode.Accepted)
            self.dialogs.pop(key, None)
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.show_normal()
        dialog.open()

    def disconnected(self, session, message):
        self.engine.enqueue({"type": "disconnected", "session": session})
        self.bridge.error.emit(message)

    def save_settings(self):
        name = self.device_name.text().strip()
        if not name or any(ord(c) < 32 for c in name):
            self.notice("请填写有效的本机名称。")
            return
        try:
            from .startup import set_enabled
            if self.startup.isChecked() != self.settings.get("startup"):
                set_enabled(self.startup.isChecked())
            self.settings.set(name=name, side=self.side.currentData(), dwell_ms=self.dwell.value(),
                              sensitivity=self.speed.value(), auto_fullscreen=self.fullscreen.isChecked(),
                              game_processes=[s.strip() for s in self.games.text().split(";") if s.strip()],
                              startup=self.startup.isChecked(), swap_ctrl_meta=self.swap.isChecked())
            self.engine.command("changed")
            self.device_info.setText(f"本机：{name}  ·  指纹：{self.identity.id[:16]}")
            self.notice("设置已保存。请在两台电脑上分别设置对方所在方向。")
        except OSError as exc:
            self.notice(str(exc))

    def check_permissions(self):
        if not self.demo:
            self.backend.permissions(request=True)
            self.engine.command("permissions")

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.closed:
            self.hide()
            self.tray.showMessage("MouseShare 正在后台运行", "从托盘菜单退出；Ctrl+Alt+Esc 随时收回键鼠。")
            event.ignore()
        else:
            event.accept()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for dialog, session in list(self.dialogs.values()):
            session.approve(False)
            dialog.reject()
        if not self.demo:
            self.engine.stop()
            self.discovery.stop()
            self.network.stop()
        self.tray.hide()


def main():
    parser = argparse.ArgumentParser(description="MouseShare")
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Show UI without hooks or network")
    parser.add_argument("--smoke-test", action="store_true", help="Validate packaged dependencies then exit")
    args = parser.parse_args()
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv[:1])
    app.setApplicationName("MouseShare")
    app.setOrganizationName("makeSail")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    if args.smoke_test:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            identity = Identity(Path(directory))
            assert identity.context(server=True)
            backend = create_backend(lambda event: True)
            assert backend.bounds()[2] > 0
        print(f"MouseShare {__version__} smoke test OK ({platform.system()} {platform.machine()})")
        return 0
    # A fixed per-user local server prevents a second instance from installing duplicate hooks.
    name = f"MouseShare-{os.environ.get('USERNAME', os.environ.get('USER', 'desktop'))}"
    existing = QLocalSocket()
    existing.connectToServer(name)
    if existing.waitForConnected(400):
        existing.write(b"show")
        existing.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    if not server.listen(name):
        QMessageBox.critical(None, "MouseShare", "无法启动本机控制服务，请重启应用。")
        return 1
    try:
        settings = Settings()
        window = MainWindow(settings, Identity(settings.directory), args.demo)
    except Exception as exc:
        QMessageBox.critical(None, "MouseShare", f"启动失败：{type(exc).__name__}。请检查本机配置文件。")
        return 1

    def activate():
        pending = server.nextPendingConnection()
        if pending:
            pending.close()
            pending.deleteLater()
        window.show_normal()
    server.newConnection.connect(activate)
    app.aboutToQuit.connect(window.shutdown)
    if not args.minimized:
        window.show()
    return app.exec()

