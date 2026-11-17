# Android build

Constituent is MIT licensed. The Android build dynamically links the open-source
Qt 6.12.0 and Qt for Python 6.12.0 runtime under LGPL 3.0. The APK
includes Qt Core, Gui, Widgets, and the Android platform plugin. The license texts
are included in [licenses](licenses). The sources are available from
[Qt](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/) and
[Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.12.0).
The Android bootstrap and runtime recipes are from
[python-for-android](https://github.com/kivy/python-for-android/tree/58d21141f17c889bf8585f5665921d72028f8831).
Its recipes identify the versions, licenses, and upstream sources for CPython,
SQLite, OpenSSL and the other bundled dependencies. The Constituent
[SQLite recipe](recipes/sqlite3/__init__.py) enables FTS5.

Build on x86-64 Linux with host Python 3.12, JDK 17, Android SDK
Platform 35, Build Tools 35.0.0, and NDK 28.2.13676358. Download the
matching ARM64 PySide6 and Shiboken6 6.12.0 wheels from
[Qt’s Android wheels](https://download.qt.io/official_releases/QtForPython/).

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install 'PySide6==6.12.0' buildozer wheel setuptools
python -m pip install -r .venv/lib/python3.12/site-packages/PySide6/scripts/requirements-android.txt
export ANDROID_SDK_ROOT=/path/to/android-sdk
export JAVA_HOME=/path/to/jdk-17
export PYSIDE_ANDROID_WHEEL=/path/to/pyside6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl
export SHIBOKEN_ANDROID_WHEEL=/path/to/shiboken6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl
packaging/android/build.sh /path/to/android-staging
```

The unsigned APK is written under the staging directory’s `packages/`. To
replace the runtime libraries, substitute compatible rebuilt wheels, use a
fresh staging directory, and sign the resulting APK with your own key. This
includes rebuilding with library changes for your own use. The official APK
uses a maintainer key to allow in-place updates.
