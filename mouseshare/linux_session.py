"""Observe desktop lock/sleep with bounded read-only D-Bus calls."""
import os
import time

from PySide6.QtCore import QObject, QTimer, SLOT, Slot
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusVariant


class LinuxSession(QObject):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.lock_until = 0
        self.bus = QDBusConnection.systemBus()
        self.path = '/org/freedesktop/login1/session/auto'
        if self.bus.isConnected():
            session_id = os.environ.get('XDG_SESSION_ID')
            if session_id:
                reply = self.call('/org/freedesktop/login1', 'org.freedesktop.login1.Manager',
                                  'GetSession', session_id)
                if reply.arguments() and hasattr(reply.arguments()[0], 'path'):
                    self.path = reply.arguments()[0].path()
            self.bus.connect('org.freedesktop.login1', self.path, 'org.freedesktop.login1.Session',
                             'Lock', self, SLOT('on_lock()'))
            self.bus.connect('org.freedesktop.login1', '/org/freedesktop/login1',
                             'org.freedesktop.login1.Manager', 'PrepareForSleep', self, SLOT('on_sleep(bool)'))
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def call(self, path, interface, method, *args):
        message = QDBusMessage.createMethodCall('org.freedesktop.login1', path, interface, method)
        message.setArguments(list(args))
        return self.bus.call(message, QDBus.CallMode.Block, 300)

    def session_property(self, name):
        reply = self.call(self.path, 'org.freedesktop.DBus.Properties', 'Get',
                          'org.freedesktop.login1.Session', name)
        if reply.type() == QDBusMessage.MessageType.ReplyMessage and reply.arguments():
            value = reply.arguments()[0]
            return value.variant() if isinstance(value, QDBusVariant) else value
        return None

    @Slot()
    def on_lock(self):
        # Drop active grabs before the lock screen tries to acquire them.
        self.lock_until = time.monotonic() + 5
        self.backend.session_locked = True
        if getattr(self.backend, 'captured', False):
            self.backend.capture(False)

    @Slot(bool)
    def on_sleep(self, sleeping):
        if sleeping:
            self.on_lock()
        else:
            self.refresh()

    def refresh(self):
        if self.bus.isConnected():
            locked, active = self.session_property('LockedHint'), self.session_property('Active')
            if type(locked) is bool:
                self.backend.session_locked = locked or active is False or time.monotonic() < self.lock_until

    def stop(self):
        self.timer.stop()
        if self.bus.isConnected():
            self.bus.disconnect('org.freedesktop.login1', self.path, 'org.freedesktop.login1.Session',
                                'Lock', self, SLOT('on_lock()'))
            self.bus.disconnect('org.freedesktop.login1', '/org/freedesktop/login1',
                                'org.freedesktop.login1.Manager', 'PrepareForSleep', self, SLOT('on_sleep(bool)'))
