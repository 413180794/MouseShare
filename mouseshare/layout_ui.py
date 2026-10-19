"""Draggable computer rectangles with explicit save, numeric editing and safe snapping."""
import copy

from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject, QGraphicsScene, QHBoxLayout, QVBoxLayout

from .i18n import exception_text, tr
from .i18n_widgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsView,
    QPushButton,
    QWidget,
)
from .topology import MAX_DEVICES, Rect, default_nodes, validate_layout
from .ui import ACCENT, ACCENT_SOFT, INK, INK_2, LINE, card, text_label


class DeviceNode(QGraphicsObject):
    def __init__(self, editor, key):
        super().__init__()
        self.editor, self.key = editor, key
        self.setFlags(self.GraphicsItemFlag.ItemIsMovable | self.GraphicsItemFlag.ItemIsSelectable)
        self.old_position = QPointF()

    def boundingRect(self):
        node = self.editor.nodes[self.key]
        return QRectF(0, 0, node['w'], node['h'])

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        meta = self.editor.metadata.get(self.key, {})
        local = self.key == self.editor.local_id
        active = local or meta.get('connected')
        painter.setBrush(QColor(ACCENT_SOFT if self.isSelected() else '#ffffff'))
        painter.setPen(QPen(QColor(ACCENT if self.isSelected() else LINE), 3 if self.isSelected() else 1.5))
        rect = self.boundingRect()
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 12, 12)
        font = QFont(painter.font())
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(INK if active else INK_2))
        name = meta.get('name', self.key[:8])
        name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, max(30, int(rect.width()-30)))
        painter.drawText(rect.adjusted(15, 15, -15, -38), Qt.AlignmentFlag.AlignCenter, name)
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(rect.adjusted(10, 30, -10, -10), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         tr('本机') if local else (tr('已连接') if active else tr('离线／未配对')))
        painter.setBrush(QColor(ACCENT if active else '#aab5b9'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(rect.width()-16, 16), 4, 4)

    def mousePressEvent(self, event):
        self.old_position = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.editor.finish_drag(self, self.old_position)


class DesktopView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, 'fitted', False) and self.scene() and self.scene().items():
            self.fitInView(self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)
            self.fitted = True


class LayoutEditor(QWidget):
    def __init__(self, settings, local_id, apply_layout, parent=None):
        super().__init__(parent)
        self.settings, self.local_id, self.apply_layout = settings, local_id, apply_layout
        self.nodes, self.items, self.metadata, self.excluded = {}, {}, {}, set()
        self.dirty = False
        self.saving_revision = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.hint = text_label(tr('拖动电脑屏幕，让相邻边缘接触。错位摆放按实际重叠区域跨屏。'), 'hint', True)
        layout.addWidget(self.hint)
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self.selection_changed)
        self.view = DesktopView(self.scene)
        self.view.setAccessibleName(tr('可拖动的电脑屏幕布局'))
        self.view.setFixedHeight(330)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setStyleSheet('QGraphicsView {background:#eef3f4; border:1px solid #dce5e8; border-radius:12px;}')
        layout.addWidget(self.view)
        tools = QHBoxLayout()
        for label, callback in [(tr('适应画布'), self.fit), ('＋', lambda: self.view.scale(1.2, 1.2)),
                                ('－', lambda: self.view.scale(1/1.2, 1/1.2)), (tr('重置排列'), self.reset_nodes),
                                (tr('移出所选设备'), self.remove_selected)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            tools.addWidget(button)
        layout.addLayout(tools)
        box, body = card(tr('精确位置与显示大小'))
        form = QFormLayout()
        self.device = QComboBox()
        self.device.currentIndexChanged.connect(self.select_combo)
        form.addRow(tr('选择设备'), self.device)
        self.x, self.y, self.height = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for label, spin in [(tr('横向位置'), self.x), (tr('纵向位置'), self.y), (tr('显示高度'), self.height)]:
            spin.setRange(-8192, 8192) if spin is not self.height else spin.setRange(64, 720)
            spin.setDecimals(1)
            spin.setSingleStep(10)
            spin.setAccessibleName(label)
            spin.valueChanged.connect(self.numeric_changed)
            form.addRow(label, spin)
        body.addLayout(form)
        body.addWidget(text_label(tr('显示大小用于匹配不同尺寸／缩放的电脑；不修改系统分辨率。未接触的屏幕不会跨屏。每两台需要直接交接或传文件的电脑都要先完成配对。'), 'hint', True))
        layout.addWidget(box)
        self.enabled = QCheckBox(tr('按此布局跨屏，并同步到已配对的新版本设备'))
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(self.mark_dirty)
        layout.addWidget(self.enabled)
        row = QHBoxLayout()
        self.save = QPushButton(tr('保存并应用布局'))
        self.save.setObjectName('primary')
        self.save.clicked.connect(self.save_layout)
        row.addWidget(self.save)
        reload = QPushButton(tr('重新载入'))
        reload.clicked.connect(self.reload)
        row.addWidget(reload)
        self.feedback = text_label(tr('拖动后保存生效'), 'hint', True)
        row.addWidget(self.feedback, 1)
        layout.insertLayout(1, row)
        layout.removeWidget(self.enabled)
        layout.insertWidget(2, self.enabled)

    def update_devices(self, metadata):
        self.metadata = metadata
        if not self.nodes:
            stored = self.settings.get('desktop_layout')
            if stored and self.local_id in stored.get('nodes', {}):
                self.load(stored)
            else:
                self.nodes = default_nodes(self.local_id, [k for k in metadata if k != self.local_id][:7],
                                           self.settings.get('side'), self.screens())
                self.rebuild()
                self.mark_dirty()
        for key in metadata:
            if key not in self.nodes and key not in self.excluded and len(self.nodes) < MAX_DEVICES:
                right = max(n['x']+n['w'] for n in self.nodes.values())
                width, height = self.screens().get(key, (1920, 1080))
                self.nodes[key] = Rect(right, 0, max(100, min(720, 180*width/max(1, height))), 180).data()
                self.rebuild()
                self.mark_dirty()
        for item in self.items.values():
            item.update()
        selected = self.device.currentData()
        blocker = QSignalBlocker(self.device)
        self.device.clear()
        for key in self.nodes:
            self.device.addItem(metadata.get(key, {}).get('name', key[:8]), key)
        if selected in self.nodes:
            self.device.setCurrentIndex(self.device.findData(selected))
        del blocker
        self.select_combo()

    def screens(self):
        return {key: (meta.get('screen', {}).get('w', 1920), meta.get('screen', {}).get('h', 1080))
                for key, meta in self.metadata.items()}

    def load(self, data):
        self.nodes = copy.deepcopy(data['nodes'])
        self.excluded = set(data.get('excluded', []))
        blocker = QSignalBlocker(self.enabled)
        self.enabled.setChecked(data.get('enabled', False))
        del blocker
        self.rebuild()
        self.dirty = False
        self.save.setEnabled(False)

    def rebuild(self):
        self.items.clear()
        self.scene.clear()
        for key, node in self.nodes.items():
            item = DeviceNode(self, key)
            item.setPos(node['x'], node['y'])
            self.scene.addItem(item)
            self.items[key] = item
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-160, -160, 160, 160))

    def fit(self):
        if self.items:
            self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)

    def mark_dirty(self, *args):
        self.dirty = True
        self.save.setEnabled(True)
        self.feedback.setText(tr('布局有未保存的更改'))

    def finish_drag(self, item, old):
        node = dict(self.nodes[item.key], x=round(item.pos().x()/5)*5, y=round(item.pos().y()/5)*5)
        for key, value in self.nodes.items():
            if key == item.key:
                continue
            for candidate in (value['x']-node['w'], value['x']+value['w']):
                if abs(node['x']-candidate) <= 12:
                    node['x'] = candidate
            for candidate in (value['y']-node['h'], value['y']+value['h']):
                if abs(node['y']-candidate) <= 12:
                    node['y'] = candidate
        try:
            self.validate_nodes({**self.nodes, item.key: node})
        except ValueError as exc:
            item.setPos(old)
            self.feedback.setText(exception_text(exc))
            return
        self.nodes[item.key] = node
        item.setPos(node['x'], node['y'])
        self.mark_dirty()
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-160, -160, 160, 160))
        self.selection_changed()

    def validate_nodes(self, nodes):
        return validate_layout(dict(enabled=True, revision=1, author=self.local_id, nodes=nodes,
                                    excluded=sorted(self.excluded)))

    def selection_changed(self):
        selected = self.scene.selectedItems()
        key = selected[0].key if selected else self.device.currentData()
        if key not in self.nodes:
            return
        blockers = [QSignalBlocker(control) for control in (self.device, self.x, self.y, self.height)]
        self.device.setCurrentIndex(self.device.findData(key))
        node = self.nodes[key]
        self.x.setValue(node['x'])
        self.y.setValue(node['y'])
        self.height.setValue(node['h'])
        del blockers

    def select_combo(self):
        key = self.device.currentData()
        if key in self.items:
            self.scene.clearSelection()
            self.items[key].setSelected(True)
            self.selection_changed()

    def numeric_changed(self, *args):
        key = self.device.currentData()
        if key not in self.nodes:
            return
        old = self.nodes[key]
        node = Rect(self.x.value(), self.y.value(), self.height.value()*old['w']/old['h'], self.height.value()).data()
        self.items[key].prepareGeometryChange()
        self.nodes[key] = node
        self.items[key].setPos(node['x'], node['y'])
        self.items[key].update()
        self.mark_dirty()

    def reset_nodes(self):
        self.excluded.clear()
        self.nodes = default_nodes(self.local_id, [k for k in self.metadata if k != self.local_id][:7], screens=self.screens())
        self.rebuild()
        self.mark_dirty()
        self.fit()

    def remove_selected(self):
        key = self.device.currentData()
        if key and key != self.local_id:
            self.nodes.pop(key, None)
            self.excluded.add(key)
            self.rebuild()
            self.update_devices(self.metadata)
            self.mark_dirty()

    def save_layout(self):
        old = self.settings.get('desktop_layout', {})
        data = dict(enabled=self.enabled.isChecked(), revision=old.get('revision', 0)+1,
                    author=self.local_id, nodes=self.nodes, excluded=sorted(self.excluded))
        try:
            data = validate_layout(data)
        except ValueError as exc:
            self.feedback.setText(exception_text(exc))
            return
        self.saving_revision = data['revision']
        self.apply_layout(data)
        self.feedback.setText(tr('正在应用布局…'))

    def applied(self, data):
        if self.dirty and not (data['author'] == self.local_id and data['revision'] == self.saving_revision):
            self.feedback.setText(tr('另一台电脑已更新布局；当前草稿保留。可重新载入，或保存覆盖。'))
            return
        self.load(data)
        self.update_devices(self.metadata)
        self.feedback.setText(tr('布局已应用，边缘接触处可跨屏'))

    def reload(self):
        data = self.settings.get('desktop_layout')
        if data:
            self.load(data)
            self.update_devices(self.metadata)
            self.fit()
