"""Android launcher for the shared Qt interface."""

import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from constituent.store import Store
from constituent.ui import Window


def main():
    # Use the device's trust anchors for government HTTPS requests.
    os.environ.setdefault("SSL_CERT_DIR", "/system/etc/security/cacerts")
    app = QApplication([])
    app.setApplicationName("Constituent")
    app.setStyle("Fusion")
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    data.mkdir(parents=True, exist_ok=True)
    window = Window(Store(data / "constituent.sqlite3"), data, automatic_refresh=False, mobile=True)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
