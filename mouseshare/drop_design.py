"""Compact edge glass artwork; motion never moves the native drop target."""
import math
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient

from .i18n import render, tr
from .i18n_widgets import QPushButton, QWidget


def edge_shape(rect, side):
    """Rounded inner corners, with a solid receiving edge even at screen corners."""
    path, square = QPainterPath(), QPainterPath()
    path.addRoundedRect(rect, 22, 22)
    strip = {'left': QRectF(rect.left(), rect.top(), 22, rect.height()),
             'right': QRectF(rect.right()-22, rect.top(), 22, rect.height()),
             'top': QRectF(rect.left(), rect.top(), rect.width(), 22),
             'bottom': QRectF(rect.left(), rect.bottom()-22, rect.width(), 22)}[side]
    square.addRect(strip)
    return path.united(square)


def motion_permitted():
    """Honor native reduced-motion preferences where the desktop exposes them."""
    try:
        if sys.platform == 'darwin':
            import AppKit
            return not AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        if sys.platform == 'win32':
            import ctypes
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                return bool(enabled.value)
    except (AttributeError, OSError):
        return False
    return True


class DropVisual(QWidget):
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_name = tr('另一台电脑')
        self.count, self.summary, self.state = 0, '', 'ready'
        self.side = 'right'
        self.blur_available = False
        self.clock = QElapsedTimer()
        self.motion = QTimer(self)
        self.motion.setInterval(33)
        self.motion.timeout.connect(self.update)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.close_button = QPushButton('×', self)
        self.close_button.setAccessibleName(tr('取消文件投递'))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet('QPushButton {color:#b6d0c8; background:rgba(255,255,255,10);'
                                       'border:0; border-radius:10px; font-size:17px; padding:0; min-height:0;}'
                                       'QPushButton:hover {background:rgba(255,255,255,30); color:#ffffff;}')
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.dismissed)

    def set_edge(self, side):
        self.side = side
        self.update()

    def set_context(self, target_name, count=0, summary='', state='ready'):
        self.target_name, self.count, self.summary = target_name, count, summary
        self.state = state
        self.close_button.setAccessibleName(tr('关闭投递提示') if state in {'sending', 'unavailable'} else tr('取消文件投递'))
        self.setAccessibleName(tr('文件投递：')+self.target_name)
        self.update()

    def set_blur_available(self, available):
        self.blur_available = bool(available)
        self.update()

    def showEvent(self, event):
        if motion_permitted():
            self.clock.start()
            self.motion.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.motion.stop()
        super().hideEvent(event)

    def motion_frame(self):
        if not self.motion.isActive():
            return 1., .65, 0.
        seconds = self.clock.elapsed()/1000
        reveal = 1-(1-min(1., seconds/.38))**3
        phase = seconds*math.tau/5.6
        return reveal, .65+.2*math.sin(phase), 1.8*math.sin(phase)

    def resizeEvent(self, event):
        self.close_button.move(self.width()-30, 10)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        vertical = self.side in {'left', 'right'}
        reveal, breath, drift = self.motion_frame()
        path = edge_shape(bounds, self.side)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(15, 31, 37, 98 if self.blur_available else 225))
        edge = {'left': QPointF(0, bounds.center().y()), 'right': QPointF(self.width(), bounds.center().y()),
                'top': QPointF(bounds.center().x(), 0), 'bottom': QPointF(bounds.center().x(), self.height())}[self.side]
        glow = QRadialGradient(edge, max(self.width(), self.height())*.85)
        glow.setColorAt(0, QColor(66, 201, 168, round(34*breath)))
        glow.setColorAt(1, QColor(43, 142, 131, 0))
        painter.fillPath(path, glow)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(204, 241, 231, 35), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        # A soft light on the actual neighboring edge breathes over 5.6 seconds.
        painter.setPen(QPen(QColor(132, 236, 209, round(130*breath*reveal)), 3,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if vertical:
            x = 2 if self.side == 'left' else self.width()-2
            painter.drawLine(QPointF(x, self.height()*.34), QPointF(x, self.height()*.66))
        else:
            y = 2 if self.side == 'top' else self.height()-2
            painter.drawLine(QPointF(self.width()*.35, y), QPointF(self.width()*.65, y))
        painter.setOpacity(reveal)

        def text(rect, value, size, color='#edf8f5', bold=False, center=False):
            font = QFont(self.font())
            font.setPixelSize(size)
            font.setBold(bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            value = painter.fontMetrics().elidedText(render(value), Qt.TextElideMode.ElideRight, max(1, int(rect.width())))
            align = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignHCenter if center else Qt.AlignmentFlag.AlignLeft)
            painter.drawText(rect, align, value)

        heading = tr('已开始发送') if self.state == 'sending' else tr('当前设备暂不可用') if self.state == 'unavailable' else (
            tr('松开发送') if self.count else tr('拖到这里'))
        detail = self.summary or (tr('{p0} 个文件或文件夹', p0=self.count) if self.count else tr('文件与文件夹 · 安全投递'))
        if self.state == 'sending':
            detail = tr('后台传输中')
        elif self.state == 'unavailable':
            detail = self.summary or tr('取消后重新连接设备')
        footer = tr('收起提示') if self.state in {'sending', 'unavailable'} else tr('取消投递')
        if vertical:
            width, height = self.width(), self.height()
            text(QRectF(16, 20, width-48, 18), 'MouseShare', 10, '#9bbcb2')
            icon = QPointF(width/2+(drift if self.side == 'right' else -drift), height*.29)
            self.paint_file(painter, icon, breath)
            text(QRectF(16, height*.45, width-32, 22), heading, 12, '#b9dacf', center=True)
            text(QRectF(14, height*.54, width-28, 28), self.target_name, 16, bold=True, center=True)
            text(QRectF(16, height*.67, width-32, 22), detail, 11, '#a5c2b9', center=True)
            text(QRectF(16, height-39, width-32, 20), 'Esc  ·  '+footer, 11, '#95b7ac', center=True)
        else:
            height = self.height()
            icon = QPointF(46, height/2+(drift if self.side == 'bottom' else -drift))
            self.paint_file(painter, icon, breath)
            left, width = 88, self.width()-126
            text(QRectF(left, 15, width, 19), heading, 11, '#b9dacf')
            text(QRectF(left, 36, width, 25), self.target_name, 16, bold=True)
            text(QRectF(left, 65, width, 18), detail, 11, '#a5c2b9')
            text(QRectF(left, height-29, width, 18), 'Esc  ·  '+footer, 10, '#95b7ac')
        painter.end()

    def paint_file(self, painter, center, breath):
        painter.save()
        painter.translate(center)
        painter.setBrush(QColor(82, 193, 160, round(22*breath)))
        painter.setPen(QPen(QColor(141, 228, 202, round(37*breath)), 1))
        painter.drawEllipse(QPointF(), 27+breath, 27+breath)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#a9e7d4'), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        if self.state == 'sending':
            path.moveTo(-10, 0)
            path.lineTo(-3, 7)
            path.lineTo(11, -8)
        else:
            path.moveTo(-11, 15)
            path.lineTo(-11, -15)
            path.quadTo(-11, -18, -8, -18)
            path.lineTo(4, -18)
            path.lineTo(13, -9)
            path.lineTo(13, 15)
            path.closeSubpath()
            path.moveTo(4, -18)
            path.lineTo(4, -9)
            path.lineTo(13, -9)
            path.moveTo(1, 9)
            path.lineTo(1, -3)
            path.moveTo(-3, 1)
            path.lineTo(1, -3)
            path.lineTo(5, 1)
        painter.drawPath(path)
        painter.restore()
