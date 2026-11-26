#!/bin/sh
# PCL Launcher 卸载脚本（Linux）
set -eu

PREFIX=${PREFIX:-"$HOME/.local"}
APP_DIR="$PREFIX/share/pcl-launcher"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        --prefix=*) PREFIX=${arg#--prefix=} ;;
    esac
done
APP_DIR="$PREFIX/share/pcl-launcher"
BIN_DIR="$PREFIX/bin"

rm -f "$BIN_DIR/pcl-launcher" "$DESKTOP_DIR/pcl-launcher.desktop"
rm -rf "$APP_DIR"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if [ "$PURGE" -eq 1 ]; then
    rm -rf "$HOME/.pcl-arm64"
    echo "已删除应用与数据目录 ~/.pcl-arm64"
else
    echo "已删除应用；配置、日志、Java 与游戏目录保留在 ~/.pcl-arm64 与 ~/.minecraft"
fi
