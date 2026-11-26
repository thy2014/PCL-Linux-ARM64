#!/bin/sh
# PCL Launcher 本地安装脚本（Linux / ARM64）
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX=${PREFIX:-"$HOME/.local"}
APP_DIR="$PREFIX/share/pcl-launcher"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
RUN_AFTER=0

for arg in "$@"; do
    case "$arg" in
        --run) RUN_AFTER=1 ;;
        --prefix=*) PREFIX=${arg#--prefix=} ;;
        -h|--help)
            echo "用法: $0 [--prefix=DIR] [--run]"
            exit 0
            ;;
    esac
done

APP_DIR="$PREFIX/share/pcl-launcher"
BIN_DIR="$PREFIX/bin"

if ! command -v python3 >/dev/null 2>&1; then
    echo "错误：未找到 python3。请先安装 Python 3.10 或更高版本。" >&2
    exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("错误：需要 Python 3.10+，当前为 %s" % sys.version.split()[0])
PY

if ! python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
from gi.repository import Gtk, WebKit2
PY
then
    echo "提示：桌面窗口需要 Python 3 的 GTK3 + WebKit2GTK 运行时。" >&2
    echo "      Debian/Ubuntu：sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0" >&2
    echo "      Fedora：sudo dnf install python3-gobject webkit2gtk4.1" >&2
    echo "      缺少时仍可用 --browser 模式，但无法使用原生目录选择器。" >&2
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
cp "$HERE/pcl-single.py" "$APP_DIR/pcl-single.py"
cp "$HERE/pcl-launcher.png" "$APP_DIR/pcl-launcher.png"
[ -f "$HERE/README.md" ] && cp "$HERE/README.md" "$APP_DIR/README.md"
[ -f "$HERE/LICENSE" ] && cp "$HERE/LICENSE" "$APP_DIR/LICENSE"
chmod 755 "$APP_DIR/pcl-single.py"

cat > "$BIN_DIR/pcl-launcher" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/pcl-single.py" "\$@"
EOF
chmod 755 "$BIN_DIR/pcl-launcher"

cat > "$DESKTOP_DIR/pcl-launcher.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PCL Launcher
Comment=Plain Craft Launcher 风格 Minecraft 启动器
Exec="$BIN_DIR/pcl-launcher"
Icon=$APP_DIR/pcl-launcher.png
Terminal=false
Categories=Game;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "已安装到：$APP_DIR"
echo "启动命令：$BIN_DIR/pcl-launcher"
echo "也可以从应用菜单打开 PCL Launcher。"
if [ "$RUN_AFTER" -eq 1 ]; then
    exec "$BIN_DIR/pcl-launcher"
fi
