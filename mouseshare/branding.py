"""Shared vector artwork for the app, tray and packaged platform icons."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient, QTransform)

INK = "#14262b"
ACCENT = "#0e9384"

# Classic pointer silhouette, tip at the origin, about 18 × 28 units.
ARROW = [(0, 24), (6.2, 18.3), (10.6, 27.5), (14.4, 25.7), (10, 16.8), (17.6, 16.8)]


def pointer(x, y, scale=1.0):
    path = QPainterPath(QPointF(x, y))
    for dx, dy in ARROW:
        path.lineTo(x + dx * scale, y + dy * scale)
    path.closeSubpath()
    return path


def squircle(rect, n=5.0, steps=160):
    """Continuous-corner tile matching the macOS Big Sur icon grid."""
    cx, cy, a, b = rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
    path = QPainterPath()
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        point = QPointF(cx + a * math.copysign(abs(c) ** (2 / n), c), cy + b * math.copysign(abs(s) ** (2 / n), s))
        path.moveTo(point) if i == 0 else path.lineTo(point)
    path.closeSubpath()
    return path


def _pen(color, width):
    return QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _monitor(p, rect, solid, detailed=True):
    """Glass outline for the source screen, filled panel for the destination."""
    p.setPen(Qt.PenStyle.NoPen)
    if detailed:
        p.setBrush(QColor(255, 255, 255, 240 if solid else 130))
        p.drawRect(QRectF(rect.center().x() - 3, rect.bottom(), 6, 7))
        p.drawRoundedRect(QRectF(rect.center().x() - 11, rect.bottom() + 6, 22, 3.4), 1.7, 1.7)
    if solid:
        fill = QLinearGradient(0, rect.top(), 0, rect.bottom())
        fill.setColorAt(0, QColor("#ffffff"))
        fill.setColorAt(1, QColor("#d7f4ed"))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 6, 6)
    else:
        # Small sizes need a heavier outline to stay visible.
        width = 2.6 if detailed else 6
        p.setPen(_pen(QColor(255, 255, 255, 215 if detailed else 235), width))
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(rect.adjusted(width / 2, width / 2, -width / 2, -width / 2), 5, 5)


def _jump_trail(start, end, lift):
    trail = QPainterPath(start)
    trail.cubicTo(QPointF(start.x() + 4, start.y() - lift), QPointF(end.x() - 4, end.y() - lift - 4), end)
    return trail


def icon_image(size=256, template=False):
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 128, size / 128)
    if template:
        _template(p, size)
    else:
        _color(p, size)
    p.end()
    return image


def _color(p, size):
    # Two screens; the pointer has just jumped from the left one onto the right one.
    detailed = size >= 48
    tile = squircle(QRectF(12, 12, 104, 104))
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(6):
        p.setBrush(QColor(0, 40, 50, 10))
        p.drawPath(QTransform().translate(64, 65.2 + i * .5).scale(1 + i * .008, 1 + i * .008)
                   .translate(-64, -64).map(tile))
    gradient = QLinearGradient(30, 12, 98, 116)
    gradient.setColorAt(0, QColor("#4fe3c4"))
    gradient.setColorAt(.55, QColor("#13a098"))
    gradient.setColorAt(1, QColor("#0b5a72"))
    p.setBrush(gradient)
    p.drawPath(tile)
    shine = QRadialGradient(QPointF(46, 6), 84)
    shine.setColorAt(0, QColor(255, 255, 255, 80))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawPath(tile)
    if detailed:
        left, right = QRectF(20, 50, 41, 31), QRectF(67, 50, 41, 31)
        cursor = pointer(78, 54, .9)
        trail = _jump_trail(QPointF(40.5, 44), QPointF(77, 49), 26)
        for i in range(1, 9):
            t = i / 9
            p.setBrush(QColor(255, 255, 255, int(150 + 100 * t)))
            p.drawEllipse(trail.pointAtPercent(t), 1.1 + 1.3 * t, 1.1 + 1.3 * t)
    else:
        left, right = QRectF(17, 42, 44, 40), QRectF(67, 42, 44, 40)
        cursor = pointer(77, 50, 1.15)
    _monitor(p, left, False, detailed)
    _monitor(p, right, True, detailed)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 40, 50, 60))
    p.drawPath(QTransform().translate(.8, 2).map(cursor))
    p.setPen(_pen("#ffffff", 2.4 if detailed else 3))
    p.setBrush(QColor("#0b5c66"))
    p.drawPath(cursor)


def _template(p, size):
    # Monochrome menu bar mask: outlined source screen, solid destination with a cut-out pointer.
    black = QColor("#000000")
    p.setPen(_pen(black, 9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(8.5, 44.5, 47, 37), 8, 8)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(black)
    p.drawRoundedRect(QRectF(66, 40, 56, 46), 11, 11)
    for x in (32, 94):
        p.drawRoundedRect(QRectF(x - 13, 94, 26, 8), 4, 4)
    if size >= 32:
        trail = _jump_trail(QPointF(32, 34), QPointF(84, 32), 22)
        for i in range(1, 6):
            p.drawEllipse(trail.pointAtPercent(i / 6), 3.6 + 2 * i / 6, 3.6 + 2 * i / 6)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.drawPath(pointer(84, 50, 1.25))


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addPixmap(QPixmap.fromImage(icon_image(size)))
    return icon


def tray_icon(template=False):
    icon = QIcon()
    for size in (16, 22, 32, 44, 64):
        icon.addPixmap(QPixmap.fromImage(icon_image(size, template)))
    icon.setIsMask(template)
    return icon


def _glyph(kind, color, size):
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    p.setPen(_pen(color, 1.6))
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
    elif kind == "play":
        path = QPainterPath(QPointF(7, 5))
        path.lineTo(19, 12)
        path.lineTo(7, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "return":
        p.drawLine(9, 6, 4, 11)
        p.drawLine(4, 11, 9, 16)
        path = QPainterPath(QPointF(4, 11))
        path.lineTo(15, 11)
        path.cubicTo(22, 11, 22, 20, 15, 20)
        p.drawPath(path)
    elif kind == "monitor":
        p.drawRoundedRect(QRectF(3, 4, 18, 12.5), 2, 2)
        p.drawLine(12, 16.5, 12, 20)
        p.drawLine(8, 20, 16, 20)
    elif kind == "laptop":
        p.drawRoundedRect(QRectF(5, 5, 14, 10.5), 1.8, 1.8)
        p.drawLine(QPointF(2.5, 19), QPointF(21.5, 19))
        p.drawLine(QPointF(5, 15.5), QPointF(3, 19))
        p.drawLine(QPointF(19, 15.5), QPointF(21, 19))
    elif kind == "link":
        p.drawRoundedRect(QRectF(2.5, 8.5, 11, 7), 3.5, 3.5)
        p.drawRoundedRect(QRectF(10.5, 8.5, 11, 7), 3.5, 3.5)
    elif kind == "lock":
        p.drawRoundedRect(QRectF(5, 10.5, 14, 10), 2.4, 2.4)
        p.drawArc(QRectF(8, 4, 8, 12), 0, 180 * 16)
        p.drawLine(QPointF(8, 10), QPointF(8, 10.5))
        p.drawLine(QPointF(16, 10), QPointF(16, 10.5))
    p.end()
    pix.setDevicePixelRatio(2)
    return pix


def line_icon(kind, color=INK, size=20, checked=None):
    """Stroke icon; `checked` colors the On state of checkable buttons."""
    icon = QIcon(_glyph(kind, color, size))
    if checked:
        icon.addPixmap(_glyph(kind, checked, size), QIcon.Mode.Normal, QIcon.State.On)
    return icon
