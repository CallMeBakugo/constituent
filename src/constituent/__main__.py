import argparse
import sys

from PySide6.QtWidgets import QApplication

from .store import Store, local_path
from .ui import Window


def main():
    parser = argparse.ArgumentParser(description="Track U.S. legislation and contact your representatives.")
    parser.add_argument("--offline", action="store_true", help="Disable automatic refresh.")
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Constituent")
    app.setDesktopFileName("constituent")
    app.setStyle("Fusion")
    data = local_path("XDG_DATA_HOME", ".local/share")
    config = local_path("XDG_CONFIG_HOME", ".config")
    window = Window(Store(data / "constituent.sqlite3"), config, automatic_refresh=not args.offline)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
