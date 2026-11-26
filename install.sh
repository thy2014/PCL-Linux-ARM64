#!/usr/bin/env bash
# 在当前用户目录安装 PCL Linux ARM64（不需要 sudo）。只下载了本脚本时，会自动拉取完整项目。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
PYTHON_BIN="${PYTHON:-python3}"
SOURCE_URL="${PCL_SOURCE_URL:-https://github.com/thy2014/PCL-Linux-ARM64/archive/refs/heads/main.tar.gz}"

RUN=0
DESKTOP=0
for arg in "$@"; do
  case "$arg" in
    --run) RUN=1 ;;
    --desktop) DESKTOP=1 ;;
    --help|-h)
      echo "用法：./install.sh [--desktop] [--run]"
      echo "  --desktop  同时创建应用菜单快捷方式"
      echo "  --run      安装完成后立即启动"
      exit 0
      ;;
  *)
      echo "未知参数：$arg（可用：--desktop、--run）" >&2
      exit 2
      ;;
  esac
done

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

if [[ -f "$HERE/pcl.py" ]]; then
  APP_HOME="$HERE"
else
  APP_HOME="${PCL_HOME:-$PREFIX/share/PCL-Linux-ARM64}"
  if [[ ! -f "$APP_HOME/pcl.py" ]]; then
    if ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
      echo "当前目录缺少 pcl.py，且系统缺少 curl/tar，无法自动获取完整项目。" >&2
      echo "请下载完整仓库：https://github.com/thy2014/PCL-Linux-ARM64" >&2
      exit 1
    fi
    echo "当前目录缺少 pcl.py，正在获取完整项目…"
    echo "安装位置：$APP_HOME"
    mkdir -p "$APP_HOME"
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    curl -fL --retry 3 --retry-delay 2 "$SOURCE_URL" -o "$TMP_DIR/pcl.tar.gz"
    tar -xzf "$TMP_DIR/pcl.tar.gz" -C "$APP_HOME" --strip-components=1
  fi
fi

if [[ ! -f "$APP_HOME/pcl.py" || ! -d "$APP_HOME/web" ]]; then
  echo "安装目录不完整：$APP_HOME（缺少 pcl.py 或 web/）" >&2
  exit 1
fi

chmod +x "$APP_HOME/start.sh"
mkdir -p "$BIN_DIR"
ln -sfn "$APP_HOME/start.sh" "$BIN_DIR/pcl-arm64"
echo "已创建命令：$BIN_DIR/pcl-arm64"

if [[ "$DESKTOP" == "1" ]]; then
  mkdir -p "$DESKTOP_DIR"
  cat > "$DESKTOP_DIR/pcl-arm64.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PCL Linux ARM64
Comment=Plain Craft Launcher · Linux ARM64 社区版
Exec=$APP_HOME/start.sh
Path=$APP_HOME
Icon=$APP_HOME/web/assets/logo.svg
Terminal=false
Categories=Game;Utility;
StartupNotify=true
EOF
  chmod +x "$DESKTOP_DIR/pcl-arm64.desktop"
  echo "已创建桌面入口：$DESKTOP_DIR/pcl-arm64.desktop"
fi

echo
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "提示：$BIN_DIR 不在 PATH 中，可把它加入 ~/.profile，或直接运行 $BIN_DIR/pcl-arm64。" ;;
esac
echo "安装完成：$APP_HOME"

if [[ "$RUN" == "1" ]]; then
  echo "正在启动…"
  exec "$APP_HOME/start.sh"
fi

echo "启动命令：pcl-arm64"
echo "指定参数：pcl-arm64 --game-dir ~/.minecraft --port 3919"
