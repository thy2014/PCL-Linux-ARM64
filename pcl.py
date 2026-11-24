#!/usr/bin/env python3
"""PCL Linux ARM64 启动器入口。"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
import threading
import webbrowser
from pathlib import Path

from pcl_core.config import APP_NAME, APP_TAGLINE, APP_VERSION, Config, Paths, arch_label, detect_arch
from pcl_core.server import create_server

BANNER = r"""
   ____   ____ _     _     _                _
  |  _ \ / ___| |   | |   | |    __ _ _ __ | |__
  | |_) | |   | |   | |   | |   / _` | '_ \| '_ \
  |  __/| |___| |___| |___| |__| (_| | | | | |_) |
  |_|    \____|_____|_____|_____\__,_|_| |_|_.__/
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PCL Linux ARM64 — 为 ARM64 Linux 打造的 Minecraft 启动器",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=3919, help="监听端口（默认 3919，占用时自动顺延）")
    parser.add_argument("--data-dir", default="", help="应用数据目录（默认 ~/.pcl-arm64）")
    parser.add_argument("--game-dir", default="", help="游戏目录（默认 ~/.minecraft）")
    parser.add_argument("--arch", choices=["arm64", "x86_64"], help="覆盖架构检测（调试用）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser


def _open_browser_later(url: str) -> None:
    def worker() -> None:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - 打不开浏览器不影响服务
            pass

    threading.Timer(1.0, worker).start()


def main() -> int:
    args = build_parser().parse_args()
    if args.arch:
        os.environ["PCL_ARCH"] = args.arch
    paths = Paths(args.data_dir or None)
    config = Config(paths)
    if args.game_dir:
        config.update({"game_dir": str(Path(os.path.expanduser(args.game_dir)).resolve())})

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(paths.logs_dir / "server.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    logging.getLogger("pcl").setLevel(logging.INFO)

    try:
        server = create_server(config, paths, host=args.host, port=args.port)
    except Exception as error:  # noqa: BLE001
        print(f"启动失败：{error}", file=sys.stderr)
        return 1

    arch = detect_arch()
    url = f"http://{args.host}:{server.state.port}/"
    print(BANNER)
    print(f"  {APP_NAME}  v{APP_VERSION}  ·  {APP_TAGLINE}")
    print(f"  架构：{arch_label(arch)} / {platform.system()}   数据：{paths.data_dir}")
    print(f"  游戏目录：{config.game_dir}")
    print(f"  界面地址：{url}")
    if arch != "arm64":
        print("  提示：当前不是 ARM64，ARM64 原生库补丁不会生效（调试界面与下载功能不受影响）。")
    else:
        print("  ARM64 原生库替换已就绪（LWJGL 3.3+ 版本生效）。")
    print("  按 Ctrl+C 退出。\n")

    if not args.no_browser:
        has_display = sys.platform != "linux" or bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        if has_display:
            _open_browser_later(url)

    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
