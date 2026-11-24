#!/usr/bin/env bash
# PCL Linux ARM64 启动脚本
set -euo pipefail

cd "$(dirname "$0")"

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

exec "$PYTHON_BIN" pcl.py "$@"
