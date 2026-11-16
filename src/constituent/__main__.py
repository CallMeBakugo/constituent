import argparse
import sys
from hashlib import sha256

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
from PySide6.QtWidgets import QApplication

from .store import Store, local_path
from .ui import Window


ACTIVATION_PATH = "/org/constituent/Window"
ACTIVATION_INTERFACE = "org.constituent.Window"


class LauncherActivation(QObject):
    requested = Signal()

    @Slot()
    def showWindow(self):
        self.requested.emit()


def activate_existing(bus, data, activation):
    # A second click on the desktop launcher should show the window already in the tray.
    if not bus.isConnected():
        return False
    profile = sha256(str(data.resolve()).encode()).hexdigest()[:16]
    service = f"org.constituent.App.p{profile}"
    if not bus.registerObject(ACTIVATION_PATH, ACTIVATION_INTERFACE, activation,
                              QDBusConnection.RegisterOption.ExportAllSlots):
        return False
    if bus.registerService(service):
        return False
    message = QDBusMessage.createMethodCall(service, ACTIVATION_PATH, ACTIVATION_INTERFACE, "showWindow")
    return bus.call(message, QDBus.CallMode.Block, 2000).type() == QDBusMessage.MessageType.ReplyMessage


def main():
    parser = argparse.ArgumentParser(description="Track U.S. legislation and contact your representatives.")
    parser.add_argument("--offline", action="store_true", help="Disable automatic refresh.")
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Constituent")
    app.setDesktopFileName("constituent")
    app.setStyle("Fusion")
    data = local_path("XDG_DATA_HOME", ".local/share")
    activation = LauncherActivation()
    if activate_existing(QDBusConnection.sessionBus(), data, activation):
        return 0
    config = local_path("XDG_CONFIG_HOME", ".config")
    window = Window(Store(data / "constituent.sqlite3"), config, automatic_refresh=not args.offline)
    activation.requested.connect(window.restore_window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
