"""User-driven native permission requests with a visible, recoverable guide."""
import sys

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from .ui import StatusBadge, card, text_label


MAC_PERMISSIONS = {
    "accessibility": ("辅助功能", "允许 MouseShare 控制鼠标与键盘，让另一台电脑的输入作用于本机。",
                      "Privacy_Accessibility"),
    "input_monitoring": ("输入监控", "允许读取本机键鼠操作，在跨屏时传给已配对的电脑。",
                         "Privacy_ListenEvent"),
}


class PermissionGuide(QDialog):
    def __init__(self, backend, retry, parent=None, *, platform=None, status_provider=None, demo=False):
        super().__init__(parent)
        self.backend, self.retry = backend, retry
        self.platform = platform or sys.platform
        self.status_provider = status_provider or backend.permission_status
        self.demo = demo
        self._retried = False
        self.rows = {}
        self.setWindowTitle("MouseShare · 键鼠权限设置")
        self.resize(620, 700 if self.platform == "darwin" else 500 if self.platform.startswith('linux') else 380)
        self.setMinimumSize(540, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(12)
        layout.addWidget(text_label("开启键鼠权限" if self.platform == "darwin" else "检查输入服务", "title"))
        layout.addWidget(text_label("按下面两步完成设置；返回这里后会自动检查。" if self.platform == "darwin"
                                    else "Linux 键鼠共享使用当前用户的 X11 图形会话。" if self.platform.startswith('linux')
                                    else "Windows 的键鼠共享通过本机输入服务运行。", "subtitle", True))
        self.summary = text_label("", "section", True)
        layout.addWidget(self.summary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        if self.platform == "darwin":
            for index, (kind, (title, purpose, _)) in enumerate(MAC_PERMISSIONS.items(), 1):
                box, section = card()
                section.setSpacing(10)
                heading = QHBoxLayout()
                heading.addWidget(text_label(f"{index}. {title}", "section"), 1)
                badge = StatusBadge()
                heading.addWidget(badge)
                section.addLayout(heading)
                section.addWidget(text_label(purpose, "hint", True))
                instructions = (f"系统设置 → 隐私与安全性 → {title}\n"
                                "找到 MouseShare，打开右侧开关。若系统要求验证，请使用登录密码或 Touch ID。")
                section.addWidget(text_label(instructions, "hint", True))
                button = QPushButton(f"开启{title}")
                button.setObjectName("primary")
                button.clicked.connect(lambda checked=False, k=kind: self.open_permission(k))
                section.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
                self.rows[kind] = (badge, button)
                body.addWidget(box)
            body.addWidget(text_label("列表里没有 MouseShare？点击「＋」，从「应用程序」选择 MouseShare.app。\n"
                                      "若系统提示「退出并重新打开」，请按提示操作，再回到这里检查。",
                                      "hint", True))
        elif self.platform.startswith('linux'):
            box, section = card('Linux 桌面会话')
            section.addWidget(text_label('X11／Xorg：以登录桌面的普通用户启动 MouseShare，点击「重新检查」。'
                                         '安装 .deb 后系统库会自动安装；便携包请按安装说明补齐依赖。', 'hint', True))
            section.addWidget(text_label('Wayland：请注销，在登录界面的会话菜单选择「Ubuntu on Xorg」或 '
                                         '「Plasma (X11)」，登录后重新打开。当前版本的 Wayland 可使用文件传输；'
                                         '剪贴板提供前台手动同步。', 'hint', True))
            section.addWidget(text_label('无需 root、input 组或放宽 X11 访问控制。远程 SSH 和无图形桌面环境'
                                         '可先完成安装，在实际桌面登录后使用键鼠共享。', 'hint', True))
            body.addWidget(box)
        else:
            box, section = card("Windows 输入服务")
            section.addWidget(text_label("如果输入服务未就绪，先点击「重新检查」。仍无法恢复时，请退出并重新打开 "
                                         "MouseShare，并确认它运行在当前登录的桌面中。", "hint", True))
            section.addWidget(text_label("电脑发现或连接失败时，请检查两台电脑是否在同一局域网，以及 Windows "
                                         "专用网络的 MouseShare 防火墙规则。", "hint", True))
            body.addWidget(box)
        body.addStretch()
        self.feedback = text_label("", "hint", True)
        layout.addWidget(self.feedback)
        actions = QHBoxLayout()
        check = QPushButton("重新检查")
        check.clicked.connect(self.recheck)
        actions.addWidget(check)
        actions.addStretch()
        self.done_button = QPushButton("稍后设置")
        self.done_button.clicked.connect(self.accept)
        actions.addWidget(self.done_button)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    def open_permission(self, kind):
        title, _, anchor = MAC_PERMISSIONS[kind]
        try:
            if not self.demo and not self.status_provider().get(kind, False):
                self.backend.request_permission(kind)
        except Exception:
            self.feedback.setText("系统授权请求未完成，请在下面的系统设置页面手动开启。")
        if self.demo:
            self.feedback.setText(f"演示：将请求{title}并打开对应的系统设置页面。")
            return
        url = QUrl(f"x-apple.systempreferences:com.apple.preference.security?{anchor}")
        if QDesktopServices.openUrl(url):
            self.feedback.setText(f"已打开「{title}」。开启 MouseShare 的开关后返回此处。")
        else:
            self.feedback.setText(f"请手动打开：系统设置 → 隐私与安全性 → {title}，然后开启 MouseShare。")
        self.refresh()

    def recheck(self):
        self._retried = False
        if self.platform != "darwin":
            self.retry()
        self.refresh()
        status = self.status_provider()
        if self.platform == "darwin" and not all(status.get(k, False) for k in MAC_PERMISSIONS):
            self.feedback.setText("若开关已开启但状态仍未更新，请退出并重新打开 MouseShare，再检查一次。")

    def refresh(self):
        if self.platform == "darwin":
            status = self.status_provider()
            for kind, (badge, button) in self.rows.items():
                granted = status.get(kind, False)
                badge.set_status("已开启" if granted else "待开启", "active" if granted else "warning")
                title = MAC_PERMISSIONS[kind][0]
                button.setText(f"打开{title}设置" if granted else f"开启{title}")
            granted = all(status.get(kind, False) for kind in MAC_PERMISSIONS)
            count = sum(bool(status.get(kind)) for kind in MAC_PERMISSIONS)
            if granted and not self.backend.ready() and not self._retried:
                self._retried = True
                self.retry()
            elif not granted:
                self._retried = False
            ready = granted and self.backend.ready()
            self.summary.setText("两项权限已开启，键鼠共享已就绪。" if ready else
                                 "权限已开启，正在检查输入服务。若仍未就绪，请退出并重新打开 MouseShare。" if granted
                                 else f"已完成 {count} / 2 项，继续开启下方权限。")
        else:
            ready = self.backend.ready()
            self.summary.setText("输入服务已就绪。" if ready else getattr(self.backend, 'error', '') or "输入服务暂未就绪，请重新检查。")
        self.done_button.setText("完成" if ready else "稍后设置")
        role = "primary" if ready else ""
        if self.done_button.objectName() != role:
            self.done_button.setObjectName(role)
            self.done_button.style().unpolish(self.done_button)
            self.done_button.style().polish(self.done_button)

    def showEvent(self, event):
        self.refresh()
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
