"""Stage just the Qt runtime modules imported by Constituent on Android."""

import sys
from pathlib import Path
from zipfile import ZipFile

BINDINGS = {"QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so", "libpyside6.abi3.so"}
QT_RUNTIME = {
    *(f"PySide6/Qt/lib/libQt6{module}_arm64-v8a.so" for module in ("Core", "Gui", "Widgets")),
    "PySide6/Qt/plugins/platforms/libplugins_platforms_qtforandroid_arm64-v8a.so",
}
JAR_RUNTIME = {"PySide6/jar/Qt6Android.jar", "PySide6/jar/Qt6AndroidBindings.jar"}


def included(name):
    if name.startswith("PySide6/Qt/"):
        return name in QT_RUNTIME
    if name.startswith("PySide6/jar/"):
        return name in JAR_RUNTIME
    return not name.endswith(".so") or name.removeprefix("PySide6/") in BINDINGS


def stage_wheel(source, target):
    with ZipFile(source) as original, ZipFile(target, "w") as staged:
        for entry in original.infolist():
            if not included(entry.filename):
                continue
            contents = original.read(entry)
            if entry.filename.endswith(".dist-info/RECORD"):
                rows = contents.decode().splitlines(keepends=True)
                contents = "".join(row for row in rows if included(row.split(",", 1)[0])).encode()
            staged.writestr(entry, contents)


if __name__ == "__main__":
    stage_wheel(Path(sys.argv[1]), Path(sys.argv[2]))
