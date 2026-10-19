"""Qt presentation bindings that update in place without restarting input services."""
from weakref import WeakKeyDictionary

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QSignalBlocker

from .i18n import Message, render

_bindings = WeakKeyDictionary()
_combo_text_role = 0x0100 + 94


def _remember(widget, method, value):
    properties = _bindings.setdefault(widget, {})
    if isinstance(value, Message):
        properties[method] = value
    else:
        properties.pop(method, None)


class _Localized:
    def __init__(self, *args, **kwargs):
        super().__init__(*(render(arg) for arg in args), **kwargs)
        # Text-bearing constructors accept text directly. Other widgets only use setters.
        if isinstance(self, (QtWidgets.QLabel, QtWidgets.QAbstractButton, QtGui.QAction)):
            text = next((arg for arg in args if isinstance(arg, Message)), None)
            if text is not None:
                _remember(self, 'setText', text)

    def setText(self, text):
        _remember(self, 'setText', text)
        super().setText(render(text))

    def setToolTip(self, text):
        _remember(self, 'setToolTip', text)
        super().setToolTip(render(text))

    def setAccessibleName(self, text):
        _remember(self, 'setAccessibleName', text)
        super().setAccessibleName(render(text))

    def setAccessibleDescription(self, text):
        _remember(self, 'setAccessibleDescription', text)
        super().setAccessibleDescription(render(text))

    def setWindowTitle(self, text):
        _remember(self, 'setWindowTitle', text)
        super().setWindowTitle(render(text))

    def setPlaceholderText(self, text):
        _remember(self, 'setPlaceholderText', text)
        super().setPlaceholderText(render(text))


# Explicitly imported by presentation modules; Qt's global classes remain untouched.
QLabel = type('QLabel', (_Localized, QtWidgets.QLabel), {})
QPushButton = type('QPushButton', (_Localized, QtWidgets.QPushButton), {})
QCheckBox = type('QCheckBox', (_Localized, QtWidgets.QCheckBox), {})
QAction = type('QAction', (_Localized, QtGui.QAction), {})
QWidget = type('QWidget', (_Localized, QtWidgets.QWidget), {})
QFrame = type('QFrame', (_Localized, QtWidgets.QFrame), {})
QDialog = type('QDialog', (_Localized, QtWidgets.QDialog), {})
QMainWindow = type('QMainWindow', (_Localized, QtWidgets.QMainWindow), {})
QLineEdit = type('QLineEdit', (_Localized, QtWidgets.QLineEdit), {})
QDoubleSpinBox = type('QDoubleSpinBox', (_Localized, QtWidgets.QDoubleSpinBox), {})
QGraphicsView = type('QGraphicsView', (_Localized, QtWidgets.QGraphicsView), {})
QSystemTrayIcon = type('QSystemTrayIcon', (_Localized, QtWidgets.QSystemTrayIcon), {})


class QComboBox(_Localized, QtWidgets.QComboBox):
    def addItem(self, text, userData=None):
        super().addItem(render(text), userData)
        if isinstance(text, Message):
            # Keep Python objects out of model QVariant serialization.
            self.setItemData(self.count()-1, (text.source, text.values), _combo_text_role)
        _bindings.setdefault(self, {})


class QFormLayout(QtWidgets.QFormLayout):
    def addRow(self, *args):
        if args and isinstance(args[0], Message):
            label = QLabel(args[0])
            label.setWordWrap(True)
            return super().addRow(label, *args[1:])
        return super().addRow(*args)


def retranslate_widgets():
    """Only app-authored Message properties are translated; names and data stay literal."""
    for widget, properties in list(_bindings.items()):
        try:
            for method, message in list(properties.items()):
                getattr(widget, method)(message)
            if isinstance(widget, QComboBox):
                blocker = QSignalBlocker(widget)
                for index in range(widget.count()):
                    value = widget.itemData(index, _combo_text_role)
                    if value:
                        widget.setItemText(index, Message(*value).render())
                del blocker
            if hasattr(widget, 'update'):
                widget.update()
        except RuntimeError:
            # A Qt parent may have deleted its C++ child before Python collects it.
            _bindings.pop(widget, None)
