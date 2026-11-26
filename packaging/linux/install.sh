#!/bin/sh
# PCL Launcher 本地安装脚本（Linux / ARM64，安装包已自带 Python 运行时）
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

if [ ! -x "$HERE/PCL-Launcher" ]; then
    echo "错误：当前目录缺少可执行的 PCL-Launcher。" >&2
    exit 1
fi

if ! command -v ldconfig >/dev/null 2>&1 || ! ldconfig -p 2>/dev/null | grep -q 'libgtk-3'; then
    echo "提示：桌面窗口需要系统 GTK3 + WebKit2GTK。" >&2
    echo "      Debian/Ubuntu：sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.0" >&2
    echo "      Fedora：sudo dnf install gtk3 webkit2gtk4.1" >&2
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
install -m 755 "$HERE/PCL-Launcher" "$APP_DIR/PCL-Launcher"
cp "$HERE/pcl-launcher.png" "$APP_DIR/pcl-launcher.png"
[ -f "$HERE/README.md" ] && cp "$HERE/README.md" "$APP_DIR/README.md"
[ -f "$HERE/LICENSE" ] && cp "$HERE/LICENSE" "$APP_DIR/LICENSE"

cat > "$BIN_DIR/pcl-launcher" <<EOF
#!/bin/sh
exec "$APP_DIR/PCL-Launcher" "\$@"
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
