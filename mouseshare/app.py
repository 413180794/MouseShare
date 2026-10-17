"""Qt desktop control panel. All data-plane input handling runs off the GUI thread."""
import argparse
import ctypes
import os
import platform
import socket
import sys
import time

from PySide6.QtCore import QObject, QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QStackedWidget, QButtonGroup,
                               QVBoxLayout, QWidget, QScrollArea)

from . import __version__
from .branding import app_icon, line_icon, tray_icon
from .ui import ScreenMap, apply_theme, card, text_label
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
        self.resize(1060, 820)
        self.setMinimumSize(940, 720)
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
        shell = QWidget()
        shell.setObjectName("shell")
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(shell)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        rail = QVBoxLayout(sidebar)
        rail.setContentsMargins(18, 30, 18, 18)
        rail.setSpacing(8)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        brand.addWidget(logo)
        brand.addWidget(text_label("MouseShare", "brand"))
        brand.setSpacing(5)
        rail.addLayout(brand)
        rail.addSpacing(24)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()
        self.stack.setObjectName("pages")
        for index, (label, icon) in enumerate([("设备连接", "devices"), ("共享设置", "settings"),
                                                ("游戏模式", "game")]):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setIcon(line_icon(icon, "#537463"))
            button.setIconSize(QSize(19, 19))
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(button, index)
            rail.addWidget(button)
        self.nav_group.button(0).setChecked(True)
        rail.addStretch()
        self.permission_button = QPushButton("系统权限")
        self.permission_button.setObjectName("quiet")
        self.permission_button.setIcon(line_icon("shield", "#65806b", 17))
        self.permission_button.clicked.connect(self.check_permissions)
        rail.addWidget(self.permission_button)
        help_button = QPushButton("使用说明")
        help_button.setObjectName("quiet")
        help_button.setIcon(line_icon("help", "#65806b", 17))
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/413180794/MouseShare/blob/main/README.md")))
        rail.addWidget(help_button)
        rail.addSpacing(12)
        rail.addWidget(text_label(f"VERSION {__version__}", "eyebrow"))
        rail.addWidget(text_label("为你的两台电脑搭一座桥。", "hint", True))
        outer.addWidget(sidebar)
        outer.addWidget(self.stack, 1)
        self.build_home()
        self.build_settings()
        self.build_game_page()
        self.stack.currentChanged.connect(lambda i: self.nav_group.button(i).setChecked(True))

    def make_page(self, title, subtitle):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = QWidget()
        root.setObjectName("page")
        scroll.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 26, 28, 18)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(6)
        labels.addWidget(text_label(title, "title"))
        labels.addWidget(text_label(subtitle, "subtitle", True))
        heading.addLayout(labels, 1)
        layout.addLayout(heading)
        wrapper = QWidget()
        wrapper.setObjectName("page")
        page_layout = QVBoxLayout(wrapper)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(scroll, 1)
        self.page_layouts = getattr(self, "page_layouts", {})
        self.page_layouts[layout] = page_layout
        self.stack.addWidget(wrapper)
        return layout, heading

    def build_home(self):
        layout, heading = self.make_page("设备连接", "一套键鼠，在两台电脑间自由切换。")
        self.status_badge = text_label("正在启动", "statusBadge")
        heading.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        box, body = card()
        box.setObjectName("canvas")
        body.setSpacing(6)
        self.state_label = text_label("正在启动…", "state")
        self.detail = text_label("准备连接你的另一台电脑。", "hint", True)
        body.addWidget(self.state_label)
        body.addWidget(self.detail)
        self.screen_map = ScreenMap()
        self.screen_map.setMinimumHeight(166)
        body.addWidget(self.screen_map)
        self.edge_hint = text_label("", "hint")
        self.edge_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.edge_hint)
        layout.addWidget(box)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.game_button = QPushButton("游戏模式")
        self.game_button.setObjectName("game")
        self.game_button.setIcon(line_icon("game", "#52735d"))
        self.game_button.setCheckable(True)
        self.game_button.setToolTip("把键鼠留在本机，防止游戏中意外跨屏。Ctrl+Alt+F12")
        self.game_button.clicked.connect(lambda: self.engine.command("game"))
        row.addWidget(self.game_button, 1)
        self.pause_button = QPushButton("暂停共享")
        self.pause_button.setIcon(line_icon("pause", "#67806d", 16))
        self.pause_button.clicked.connect(lambda: self.engine.command("pause"))
        row.addWidget(self.pause_button)
        take_back = QPushButton("收回控制")
        take_back.setIcon(line_icon("return", "#67806d", 16))
        take_back.setToolTip("立即释放远端按键并恢复本机控制。Ctrl+Alt+Esc")
        take_back.clicked.connect(lambda: self.engine.command("panic"))
        row.addWidget(take_back)
        layout.addLayout(row)
        box, body = card()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(text_label("附近的设备", "section"))
        top.addStretch()
        self.discovery_label = text_label("自动发现已开启", "hint")
        top.addWidget(self.discovery_label)
        body.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["设备名称", "系统", "局域网地址", "连接状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFixedHeight(100)
        self.table.doubleClicked.connect(self.connect_selected)
        self.table.itemSelectionChanged.connect(self.update_actions)
        body.addWidget(self.table)
        self.empty_label = text_label("在另一台电脑上打开 MouseShare，设备会自动出现在这里。", "hint", True)
        self.empty_label.setContentsMargins(4, 18, 4, 18)
        body.addWidget(self.empty_label)
        row = QHBoxLayout()
        self.connect_button = QPushButton("配对并连接")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.connect_selected)
        row.addWidget(self.connect_button)
        self.forget_button = QPushButton("取消配对")
        self.forget_button.clicked.connect(self.forget_selected)
        row.addWidget(self.forget_button)
        row.addStretch()
        manual = QPushButton("通过 IP 连接")
        manual.setObjectName("quiet")
        manual.setCheckable(True)
        row.addWidget(manual)
        body.addLayout(row)
        self.manual_row = QWidget()
        ip_row = QHBoxLayout(self.manual_row)
        ip_row.setContentsMargins(0, 6, 0, 0)
        self.manual_ip = QLineEdit()
        self.manual_ip.setPlaceholderText("对方的 IPv4 地址，例如 192.168.1.20")
        self.manual_ip.returnPressed.connect(self.connect_ip)
        ip_row.addWidget(self.manual_ip)
        connect_ip = QPushButton("连接")
        connect_ip.clicked.connect(self.connect_ip)
        ip_row.addWidget(connect_ip)
        body.addWidget(self.manual_row)
        self.manual_row.hide()
        manual.toggled.connect(self.manual_row.setVisible)
        layout.addWidget(box)
        self.notice_label = text_label("自动发现同一局域网内的设备，配对后加密连接。", "hint", True)
        layout.addWidget(self.notice_label)
        layout.addStretch()
        self.update_map()
        self.update_actions()

    def build_settings(self):
        layout, _ = self.make_page("共享设置", "让跨屏方式适合你的桌面摆放和使用习惯。")
        box, body = card("屏幕位置", "在两台电脑上分别设置对方的位置。")
        form = QFormLayout()
        form.setSpacing(18)
        self.side = QComboBox()
        for label, value in [("右侧 →", "right"), ("左侧 ←", "left"), ("上方 ↑", "top"), ("下方 ↓", "bottom")]:
            self.side.addItem(label, value)
        self.side.setCurrentIndex(self.side.findData(self.settings.get("side")))
        form.addRow("另一台电脑在本机的", self.side)
        row = QHBoxLayout()
        self.dwell = QSpinBox()
        self.dwell.setRange(100, 1500)
        self.dwell.setSuffix(" ms")
        self.dwell.setValue(self.settings.get("dwell_ms"))
        row.addWidget(self.dwell)
        row.addWidget(text_label("在边缘停留多久后切换", "hint"), 1)
        form.addRow("边缘停留", row)
        row = QHBoxLayout()
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 4)
        self.speed.setSingleStep(0.25)
        self.speed.setSuffix(" ×")
        self.speed.setValue(self.settings.get("sensitivity"))
        row.addWidget(self.speed)
        row.addWidget(text_label("调整本机接收的鼠标速度", "hint"), 1)
        form.addRow("鼠标速度", row)
        body.addLayout(form)
        layout.addWidget(box)
        box, body = card("本机偏好")
        form = QFormLayout()
        form.setSpacing(16)
        self.device_name = QLineEdit(self.settings.get("name"))
        self.device_name.setMaxLength(80)
        form.addRow("设备名称", self.device_name)
        self.swap = QCheckBox("交换 Ctrl 与 ⌘ / Win")
        self.swap.setChecked(self.settings.get("swap_ctrl_meta", False))
        self.swap.setToolTip("接收远端输入时，沿用另一台电脑的复制粘贴修饰键习惯。")
        form.addRow("接收时的修饰键", self.swap)
        self.startup = QCheckBox("登录后自动启动")
        self.startup.setChecked(self.settings.get("startup"))
        form.addRow("开机启动", self.startup)
        body.addLayout(form)
        self.device_info = text_label(f"设备指纹  {self.identity.id[:16]}", "hint")
        body.addWidget(self.device_info)
        layout.addWidget(box)
        box, body = card("随时收回控制")
        modifier = "Control + Option" if sys.platform == "darwin" else "Ctrl + Alt"
        body.addWidget(text_label(f"{modifier} + Esc     立即收回键鼠\n{modifier} + F12     切换游戏模式", "hint", True))
        if sys.platform == "darwin":
            body.addWidget(text_label("部分 Mac 键盘需要同时按 Fn。", "hint"))
        layout.addWidget(box)
        self.add_save_row(layout)
        layout.addStretch()

    def build_game_page(self):
        layout, _ = self.make_page("游戏模式", "专注当前屏幕，让键鼠留在本机。")
        box, body = card("手动锁定", "开启后暂停双向共享。退出游戏后，可随时恢复跨屏。")
        self.game_page_button = QPushButton("开启游戏模式")
        self.game_page_button.setObjectName("game")
        self.game_page_button.setIcon(line_icon("game", "#52735d"))
        self.game_page_button.setCheckable(True)
        self.game_page_button.clicked.connect(lambda: self.engine.command("game"))
        body.addWidget(self.game_page_button)
        self.game_detail = text_label("全局快捷键：Ctrl + Alt + F12", "hint", True)
        body.addWidget(self.game_detail)
        layout.addWidget(box)
        box, body = card("自动保护 · Windows", "前台出现全屏窗口或指定游戏进程时，自动锁定键鼠。")
        self.fullscreen = QCheckBox("全屏时自动开启游戏模式")
        self.fullscreen.setChecked(self.settings.get("auto_fullscreen"))
        self.fullscreen.setEnabled(sys.platform == "win32")
        body.addWidget(self.fullscreen)
        body.addWidget(text_label("全屏视频也会触发，可关闭此项并保留游戏进程检测。", "hint", True))
        body.addSpacing(6)
        body.addWidget(text_label("游戏进程", "section"))
        self.games = QLineEdit("; ".join(self.settings.get("game_processes")))
        self.games.setPlaceholderText("League of Legends.exe; cs2.exe")
        self.games.setEnabled(sys.platform == "win32")
        body.addWidget(self.games)
        body.addWidget(text_label("填写 .exe 文件名，多个进程用英文分号分隔。", "hint", True))
        if sys.platform != "win32":
            body.addWidget(text_label("这台 Mac 可使用手动游戏模式；自动保护在 Windows 端设置。", "hint", True))
        layout.addWidget(box)
        self.add_save_row(layout)
        layout.addStretch()

    def add_save_row(self, layout):
        row = QHBoxLayout()
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        row.addWidget(save)
        self.saved_labels = getattr(self, "saved_labels", [])
        hint = text_label("更改后保存生效", "hint", True)
        self.saved_labels.append(hint)
        row.addWidget(hint)
        row.addStretch()
        footer = QWidget()
        row.setContentsMargins(28, 10, 28, 18)
        footer.setLayout(row)
        self.page_layouts[layout].addWidget(footer)

    def update_actions(self):
        if not hasattr(self, "connect_button"):
            return
        selected = self.selected_id()
        session = self.network.session
        self.connect_button.setEnabled(bool(selected) and not session)
        self.connect_button.setText("已连接" if session and session.connected else "连接中…" if session else "配对并连接")
        self.forget_button.setEnabled(selected in self.settings.get("peers"))

    def update_map(self):
        state = getattr(self, "ui_state", {})
        peer_name = state.get("peer_name") or "等待另一台电脑"
        peer_os = ""
        if state.get("peer_name"):
            peer = next((v for v in self.peers.values() if v.get("name") == peer_name), {})
            peer_os = {"Darwin": "macOS", "Windows": "Windows"}.get(peer.get("os"), "")
        self.screen_map.configure(side=self.settings.get("side"), local_name=self.settings.get("name"),
                                  local_os="macOS" if sys.platform == "darwin" else "Windows",
                                  peer_name=peer_name, peer_os=peer_os, connected=bool(state.get("connected")),
                                  blocked=bool(state.get("game") or state.get("paused") or not state.get("ready")),
                                  owner=state.get("state", "local"))
        direction = {"left": "左侧", "right": "右侧", "top": "上方", "bottom": "下方"}[self.settings.get("side")]
        self.edge_hint.setText(f"移到{direction}边缘，停留 {self.settings.get('dwell_ms')} ms 即可跨屏")

    def build_tray(self):
        self.tray = QSystemTrayIcon(tray_icon(sys.platform == "darwin"), self)
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
        for hint in self.saved_labels:
            hint.setText(text)

    def show_status(self, state):
        self.ui_state = state
        self.game_button.setChecked(state["manual_game"])
        self.game_button.setText("游戏保护中" if state["game"] else "游戏模式")
        self.game_page_button.setChecked(state["manual_game"])
        self.game_page_button.setText("关闭游戏模式" if state["manual_game"] else "开启游戏模式")
        self.game_detail.setText(state["auto_reason"] or ("手动保护已开启，键鼠留在本机。" if state["manual_game"]
                                  else "全局快捷键：Control + Option + F12" if sys.platform == "darwin"
                                  else "全局快捷键：Ctrl + Alt + F12"))
        self.pause_button.setText("恢复共享" if state["paused"] else "暂停共享")
        peer = state["peer_name"]
        if not state["ready"]:
            title, detail = "等待系统授权", state["error"] or "请点击侧栏的系统权限按钮检查。"
        elif state["game"]:
            title, detail = "游戏模式 · 键鼠锁定本机", state["auto_reason"] or "手动游戏模式已开启；再次按快捷键即可关闭。"
        elif state.get("system_blocked"):
            title, detail = "共享已安全暂停", "系统处于锁屏或其他非交互桌面；恢复桌面后可继续使用。"
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
        badge = ("需要授权", "warning") if not state["ready"] else (
            ("游戏模式", "warning") if state["game"] else ("已暂停", "idle")
            if state["paused"] or state.get("system_blocked") else ("已连接", "active")
            if state["connected"] else ("等待连接", "idle"))
        self.status_badge.setText(badge[0])
        self.status_badge.setProperty("tone", badge[1])
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.permission_button.setText("系统权限 · 已就绪" if state["ready"] else "系统权限 · 待授权")
        self.permission_button.setToolTip(state["error"] or "检查辅助功能和输入监控权限")
        self.update_map()
        self.update_actions()
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
                item = QTableWidgetItem(str(value))
                if column == 3:
                    item.setForeground(QColor("#18775b" if status == "已连接" else "#819183"))
                self.table.setItem(row, column, item)
            if peer_id == selected:
                self.table.selectRow(row)
        self.table.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)
        if rows and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self.discovery_label.setText(f"{len(rows)} 台设备 · 自动发现" if rows else "正在自动发现…")
        self.update_map()
        self.update_actions()
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
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)
        name = QLabel(f"请求连接：{session.peer_name}")
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)
        code = QLabel(f"{session.code[:3]}  {session.code[3:]}")
        code.setStyleSheet("font-size: 48px; font-weight: 700; color: #167c67; padding: 18px;")
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
            self.device_info.setText(f"设备指纹  {self.identity.id[:16]}")
            self.update_map()
            for hint in self.saved_labels:
                hint.setText("已保存")
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
    apply_theme(app)
    if args.smoke_test:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            identity = Identity(Path(directory))
            assert identity.context(server=True)
            backend = create_backend(lambda event: True)
            assert backend.bounds()[2] > 0
            assert isinstance(backend.permissions(), bool)
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

