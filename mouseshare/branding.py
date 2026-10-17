"""Shared vector artwork for the app, tray and packaged platform icons."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

INK = "#183b37"
ACCENT = "#157e6c"


def icon_image(size=256, template=False):
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 128, size / 128)
    if template:
        p.setPen(QPen(QColor("#000000"), 8, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(12, 22, 65, 58), 9, 9)
        p.drawRoundedRect(QRectF(51, 48, 65, 58), 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000000"))
        arrow = QPainterPath(QPointF(65, 59))
        for x, y in [(65, 90), (73, 82), (82, 98), (89, 94), (80, 78), (92, 77)]:
            arrow.lineTo(x, y)
        arrow.closeSubpath()
        p.drawPath(arrow)
    else:
        gradient = QLinearGradient(18, 10, 100, 120)
        gradient.setColorAt(0, QColor("#249f89"))
        gradient.setColorAt(1, QColor("#075347"))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(8, 8, 112, 112), 26, 26)
        p.setPen(QPen(QColor("#ace0d2"), 3))
        p.setBrush(QColor("#20ffffff"))
        p.drawRoundedRect(QRectF(27, 31, 49, 48), 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3800382e"))
        p.drawRoundedRect(QRectF(51, 49, 51, 51), 8, 8)
        p.setBrush(QColor("#f5faf6"))
        p.drawRoundedRect(QRectF(50, 46, 51, 50), 7, 7)
        p.setPen(QPen(QColor("#c4e8df"), 2))
        p.drawLine(57, 56, 93, 56)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#086450"))
        arrow = QPainterPath(QPointF(63, 62))
        for x, y in [(63, 84), (69, 78), (76, 90), (82, 87), (75, 75), (85, 75)]:
            arrow.lineTo(x, y)
        arrow.closeSubpath()
        p.drawPath(arrow)
        p.setBrush(QColor("#d1eee6"))
        p.drawEllipse(QPointF(35, 39), 1.5, 1.5)
        p.drawEllipse(QPointF(41, 39), 1.5, 1.5)
    p.end()
    return image


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(icon_image(size)))
    return icon


def tray_icon(template=False):
    icon = QIcon()
    for size in (16, 22, 32, 44, 64):
        icon.addPixmap(QPixmap.fromImage(icon_image(size, template)))
    icon.setIsMask(template)
    return icon


def line_icon(kind, color=INK, size=20):
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "devices":
        p.drawRoundedRect(QRectF(2.5, 4, 13, 10), 2, 2)
        p.drawLine(9, 14, 9, 18)
        p.drawLine(5, 18, 12, 18)
        p.drawRoundedRect(QRectF(15, 10, 6.5, 10), 1.5, 1.5)
    elif kind == "settings":
        for y, x in [(5, 8), (12, 16), (19, 10)]:
            p.drawLine(3, y, x - 3, y)
            p.drawLine(x + 3, y, 21, y)
            p.drawEllipse(QPointF(x, y), 2.8, 2.8)
    elif kind == "game":
        path = QPainterPath(QPointF(7, 7))
        path.cubicTo(2, 7, 0, 20, 5, 19)
        path.lineTo(9, 16)
        path.lineTo(15, 16)
        path.lineTo(19, 19)
        path.cubicTo(24, 20, 22, 7, 17, 7)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(5, 11, 10, 11)
        p.drawLine(7.5, 8.5, 7.5, 13.5)
        p.drawEllipse(QPointF(16.5, 10.5), 0.65, 0.65)
        p.drawEllipse(QPointF(19, 13), 0.65, 0.65)
    elif kind == "shield":
        path = QPainterPath(QPointF(12, 3))
        path.lineTo(20, 6)
        path.lineTo(19, 14)
        path.cubicTo(18, 18, 14, 20, 12, 21)
        path.cubicTo(10, 20, 6, 18, 5, 14)
        path.lineTo(4, 6)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(8, 12, 11, 15)
        p.drawLine(11, 15, 16, 9)
    elif kind == "help":
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.drawArc(QRectF(8, 6, 8, 8), 0, 180 * 16)
        p.drawLine(12, 10, 12, 14)
        p.drawPoint(12, 18)
    elif kind == "pause":
        p.drawLine(8, 5, 8, 19)
        p.drawLine(16, 5, 16, 19)
    elif kind == "return":
        p.drawLine(9, 6, 4, 11)
        p.drawLine(4, 11, 9, 16)
        path = QPainterPath(QPointF(4, 11))
        path.lineTo(15, 11)
        path.cubicTo(22, 11, 22, 20, 15, 20)
        p.drawPath(path)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)
