#!/usr/bin/env bash
# PCL Linux ARM64 启动脚本。只下载了本脚本时，会自动拉取完整项目到用户目录。
set -euo pipefail

SELF="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"
HERE="$(cd "$(dirname "$SELF")" && pwd)"
cd "$HERE"

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装 Python 3.10 或更高版本。" >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    print(f"需要 Python 3.10+，当前为 {sys.version.split()[0]}。", file=sys.stderr)
    raise SystemExit(1)
PY

if [[ ! -f "$HERE/pcl.py" ]]; then
  SOURCE_URL="${PCL_SOURCE_URL:-https://github.com/thy2014/PCL-Linux-ARM64/archive/refs/heads/main.tar.gz}"
  APP_HOME="${PCL_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/PCL-Linux-ARM64}"

  if ! command -v curl >/dev/null 2>&1; then
    echo "当前目录缺少 pcl.py，且系统没有 curl，无法自动获取完整项目。" >&2
    echo "请重新下载完整仓库：$SOURCE_URL" >&2
    exit 1
  fi
  if ! command -v tar >/dev/null 2>&1; then
    echo "当前目录缺少 pcl.py，且系统没有 tar，无法自动解压项目。" >&2
    exit 1
  fi

  mkdir -p "$APP_HOME"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  if [[ ! -f "$APP_HOME/pcl.py" ]]; then
    echo "当前目录缺少 pcl.py，正在获取完整项目…" >&2
    echo "安装位置：$APP_HOME" >&2
    if ! curl -fL --retry 3 --retry-delay 2 "$SOURCE_URL" -o "$TMP_DIR/pcl.tar.gz"; then
      echo "项目下载失败，请检查网络后重试，或手动克隆仓库：$SOURCE_URL" >&2
      exit 1
    fi
    tar -xzf "$TMP_DIR/pcl.tar.gz" -C "$APP_HOME" --strip-components=1
  fi
  if [[ ! -f "$APP_HOME/pcl.py" ]]; then
    echo "项目解压后仍缺少 pcl.py，请重新下载完整仓库。" >&2
    exit 1
  fi
  cd "$APP_HOME"
  echo "使用完整项目：$APP_HOME" >&2
fi

exec "$PYTHON_BIN" pcl.py "$@"
