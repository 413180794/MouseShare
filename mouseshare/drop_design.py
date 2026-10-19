"""Foreground artwork for the transient glass file-drop surface."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QPushButton, QWidget


class DropVisual(QWidget):
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_name = '另一台电脑'
        self.count, self.summary, self.state = 0, '', 'ready'
        self.blur_available = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.close_button = QPushButton('×', self)
        self.close_button.setAccessibleName('取消文件投递')
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet('QPushButton {color:#ecf7f4; background:rgba(255,255,255,16);'
                                       'border:1px solid rgba(255,255,255,32); border-radius:21px; font-size:26px;}'
                                       'QPushButton:hover {background:rgba(255,255,255,35);}')
        self.close_button.setFixedSize(42, 42)
        self.close_button.clicked.connect(self.dismissed)

    def set_context(self, target_name, count=0, summary='', state='ready'):
        self.target_name, self.count, self.summary = str(target_name), count, str(summary)
        self.state = state
        self.close_button.setAccessibleName('关闭投递提示' if state in {'sending', 'unavailable'} else '取消文件投递')
        self.setAccessibleName('文件投递：'+self.target_name)
        self.update()

    def set_blur_available(self, available):
        self.blur_available = bool(available)
        self.update()

    def resizeEvent(self, event):
        self.close_button.move(self.width()-70, 28)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        painter.fillRect(bounds, QColor(9, 19, 25, 96 if self.blur_available else 222))
        cx, cy = bounds.center().x(), bounds.center().y()-10
        glow = QRadialGradient(QPointF(cx, cy-100), min(560, self.width()*.55))
        glow.setColorAt(0, QColor(61, 174, 155, 33))
        glow.setColorAt(1, QColor(24, 58, 67, 0))
        painter.fillRect(bounds, glow)
        scale = max(.65, min(1.15, min(self.width()/1200, self.height()/800)))
        width, height = min(620, self.width()-64), min(440, self.height()-120)
        panel = QRectF(cx-width/2, cy-height/2, width, height)
        for radius, alpha in [(28, 3), (18, 5), (9, 8)]:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(panel.adjusted(-radius, -radius/2, radius, radius), 28, 28)
        painter.setBrush(QColor(23, 39, 45, 190))
        painter.setPen(QPen(QColor(214, 248, 238, 46), 1))
        painter.drawRoundedRect(panel, 26, 26)
        painter.setPen(QPen(QColor(132, 229, 207, 70), 1))
        painter.drawLine(QPointF(panel.left()+38, panel.top()+1), QPointF(panel.right()-38, panel.top()+1))

        def text(rect, value, size, color='#edf8f5', bold=False):
            font = QFont(self.font())
            font.setPixelSize(max(11, round(size*scale)))
            font.setBold(bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            value = painter.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, int(rect.width()))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, value)

        top = panel.top()
        text(QRectF(panel.left()+20, top+20, width-40, 25), 'M O U S E S H A R E', 12, '#9bb9b4', True)
        center = QPointF(cx, top+104)
        painter.setBrush(QColor(50, 143, 125, 31))
        painter.setPen(QPen(QColor(126, 223, 197, 40), 1))
        painter.drawEllipse(center, 40*scale, 40*scale)
        painter.save()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#9cebd7'), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(-17, 18)
        path.lineTo(-17, -17)
        path.quadTo(-17, -22, -12, -22)
        path.lineTo(5, -22)
        path.lineTo(17, -10)
        path.lineTo(17, 18)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(5, -22), QPointF(5, -10))
        painter.drawLine(QPointF(5, -10), QPointF(17, -10))
        painter.drawLine(QPointF(0, 11), QPointF(0, -5))
        painter.drawLine(QPointF(-6, 1), QPointF(0, -5))
        painter.drawLine(QPointF(6, 1), QPointF(0, -5))
        painter.restore()
        heading = '已开始发送' if self.state == 'sending' else '当前设备暂不可用' if self.state == 'unavailable' else (
            '松开发送到' if self.count else '把文件拖到这里')
        text(QRectF(panel.left()+24, top+164, width-48, 36), heading, 22, '#c4d8d3')
        text(QRectF(panel.left()+28, top+205, width-56, 55), self.target_name, 34, bold=True)
        detail = self.summary or (f'{self.count} 个文件或文件夹' if self.count else '文件与文件夹 · 安全投递')
        if self.state == 'sending':
            detail = '可返回桌面，文件在后台传输'
        elif self.state == 'unavailable':
            detail = self.summary or '取消后重新连接设备'
        text(QRectF(panel.left()+32, top+277, width-64, 28), detail, 15, '#adcbc3')
        text(QRectF(panel.left()+20, panel.bottom()-78, width-40, 25),
             '文件以副本发送，对方确认后接收', 13, '#8ca9a2')
        painter.setBrush(QColor(80, 196, 159))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx-37, panel.bottom()-31), 3, 3)
        text(QRectF(cx-27, panel.bottom()-45, 94, 28),
             '投递效果预览' if self.state == 'ready' else '已配对 · 加密', 12, '#a7c9bd')
        # Keep cancellation reachable even on the smallest supported preview.
        baseline = min(self.height()-42, panel.bottom()+60)
        key = QRectF(cx-77, baseline-13, 43, 26)
        painter.setPen(QPen(QColor(216, 242, 234, 46), 1))
        painter.setBrush(QColor(229, 248, 243, 10))
        painter.drawRoundedRect(key, 6, 6)
        text(key, 'Esc', 12, '#d7eae4')
        text(QRectF(cx-22, baseline-13, 99, 26),
             '收起提示' if self.state in {'sending', 'unavailable'} else '取消投递', 13, '#adc5bd')
