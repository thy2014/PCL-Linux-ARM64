#!/usr/bin/env bash
# 在当前用户目录安装 PCL Linux ARM64（不需要 sudo）
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
APP_DIR="$PREFIX/share/applications"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装 Python 3.10+。" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "需要 Python 3.10+，当前为 $("$PYTHON_BIN" -V 2>&1)。" >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "提示：当前架构为 $ARCH，不是 ARM64。界面与下载可用，但 ARM64 原生库补丁不会生效。" >&2
fi

chmod +x start.sh install.sh
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/start.sh" "$BIN_DIR/pcl-arm64"
echo "已创建命令：$BIN_DIR/pcl-arm64"

if [[ "${1:-}" == "--desktop" ]]; then
  mkdir -p "$APP_DIR"
  cat > "$APP_DIR/pcl-arm64.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PCL Linux ARM64
Comment=Plain Craft Launcher · Linux ARM64 社区版
Exec=$ROOT/start.sh
Path=$ROOT
Icon=$ROOT/web/assets/logo.svg
Terminal=false
Categories=Game;Utility;
StartupNotify=true
EOF
  chmod +x "$APP_DIR/pcl-arm64.desktop"
  echo "已创建桌面入口：$APP_DIR/pcl-arm64.desktop"
fi

echo
echo "启动：pcl-arm64"
echo "指定参数：pcl-arm64 --game-dir ~/.minecraft --port 3919"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "提示：$BIN_DIR 不在 PATH 中，可把它加入 ~/.profile。" ;;
esac
