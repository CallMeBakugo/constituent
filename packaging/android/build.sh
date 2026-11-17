#!/usr/bin/env bash
set -euo pipefail

# Requires PySide6 and its Android deployment dependencies in a host venv.
# The staged tree and all tool caches are kept outside the source checkout.
repo=$(cd "$(dirname "$0")/../.." && pwd)
stage=$(realpath -m "${1:?Pass an Android staging directory}")
: "${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT}"
: "${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
: "${PYSIDE_ANDROID_WHEEL:?Set PYSIDE_ANDROID_WHEEL}"
: "${SHIBOKEN_ANDROID_WHEEL:?Set SHIBOKEN_ANDROID_WHEEL}"
export ANDROID_USER_HOME="$stage/android-user"
export GRADLE_USER_HOME="$stage/gradle"
export CONSTITUENT_ANDROID_BUILD_CACHE="$stage/build-cache"
export PYTHONFORANDROID_PREREQUISITES_INSTALL_INTERACTIVE=0
export PATH="$JAVA_HOME/bin:$PATH"
if [[ ! -e "$ANDROID_SDK_ROOT/tools" && -x "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]]; then
  ln -s cmdline-tools/latest "$ANDROID_SDK_ROOT/tools"
fi

project="$stage/project"
mkdir -p "$project/constituent" "$ANDROID_USER_HOME"
cp "$repo/packaging/android/main.py" "$project/main.py"
cp "$repo/packaging/constituent.png" "$project/icon.png"
find "$repo/src/constituent" -maxdepth 1 -type f \( -name '*.py' -o -name '*.gz' \) \
  ! -name '__main__.py' -exec cp -t "$project/constituent" -- {} +
cp "$repo/LICENSE" "$project/LICENSE.txt"
cp "$repo/packaging/android/README.md" "$project/Android-runtime-notice.txt"
mkdir -p "$project/licenses"
cp "$repo/packaging/android/licenses/"*.txt "$project/licenses/"
wheel_dir="$stage/runtime-wheels"
mkdir -p "$wheel_dir"
qt_wheel="$wheel_dir/$(basename "$PYSIDE_ANDROID_WHEEL")"
python "$repo/packaging/android/qt_widget_wheel.py" "$PYSIDE_ANDROID_WHEEL" "$qt_wheel"
export CONSTITUENT_QT_WHEEL="$qt_wheel"
cd "$project"

if [[ ! -f buildozer.spec ]]; then
  pyside6-android-deploy --init --no-install --keep-deployment-files -f \
    --name Constituent --sdk-path "$ANDROID_SDK_ROOT" \
    --ndk-path "$ANDROID_SDK_ROOT/ndk/28.2.13676358" \
    --wheel-pyside "$qt_wheel" --wheel-shiboken "$SHIBOKEN_ANDROID_WHEEL"
fi

python - "$repo/pyproject.toml" <<'PY'
from configparser import ConfigParser
from pathlib import Path
import os
import sys
import tomllib

version = tomllib.loads(Path(sys.argv[1]).read_text())["project"]["version"]
major, minor, patch = map(int, version.split("."))
spec = ConfigParser(interpolation=None)
spec.read("buildozer.spec")
spec["app"].update({
    "title": "Constituent", "package.name": "constituent", "package.domain": "org.constituent",
    "source.include_exts": "py,gz,png,txt", "source.exclude_dirs": "deployment,bin",
    "version": version, "icon.filename": "icon.png", "orientation": "portrait",
    "android.permissions": "INTERNET", "android.allow_backup": "False",
    "android.numeric_version": str(major * 10000 + minor * 100 + patch),
    "android.release_artifact": "apk", "android.skip_update": "True",
})
recipes = Path(spec["app"]["p4a.local_recipes"])
from shutil import copytree
pyside_recipe = recipes / "PySide6" / "__init__.py"
lines = pyside_recipe.read_text().splitlines()
pyside_recipe.write_text("\n".join(
    f"    wheel_path = {os.environ['CONSTITUENT_QT_WHEEL']!r}"
    if line.startswith("    wheel_path = ") else line
    for line in lines
) + "\n")
copytree(Path(sys.argv[1]).parent / "packaging/android/recipes", recipes, dirs_exist_ok=True)
spec["buildozer"]["bin_dir"] = str(Path.cwd().parent / "packages")
with open("buildozer.spec", "w") as stream:
    spec.write(stream)
PY

python - <<'PY'
import os
import sys
from buildozer import Buildozer
from buildozer.scripts.client import main

if sys.prefix != sys.base_prefix:
    os.environ.setdefault("VIRTUAL_ENV", sys.prefix)
Buildozer.global_buildozer_dir = property(lambda self: os.environ["CONSTITUENT_ANDROID_BUILD_CACHE"])
sys.argv = ["buildozer", "-v", "android", "release"]
main()
PY
