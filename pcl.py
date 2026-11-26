#!/usr/bin/env python3
"""PCL Launcher 入口：默认打开桌面窗口，也可回退到浏览器。"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

from pcl_core.config import APP_NAME, APP_TAGLINE, APP_VERSION, Config, Paths, arch_label, detect_arch, detect_os
from pcl_core.server import create_server

BANNER = r"""
   ____   ____ _     _     _                _
  |  _ \ / ___| |   | |   | |    __ _ _ __ | |__
  | |_) | |   | |   | |   | |   / _` | '_ \| '_ \
  |  __/| |___| |___| |___| |__| (_| | | | | |_) |
  |_|    \____|_____|_____|_____\__,_|_| |_|_.__/
"""

logger = logging.getLogger("pcl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} — 为 Windows 与 Linux ARM64 打造的 Minecraft 启动器",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=3919, help="监听端口（默认 3919，占用时自动顺延）")
    parser.add_argument("--data-dir", default="", help="应用数据目录（默认按系统惯例）")
    parser.add_argument("--game-dir", default="", help="游戏目录（默认 ~/.minecraft）")
    parser.add_argument("--arch", choices=["arm64", "x86_64", "arm32"], help="覆盖架构检测（调试用）")
    parser.add_argument("--no-window", action="store_true", help="不打开桌面窗口（服务端模式）")
    parser.add_argument("--browser", action="store_true", help="强制用默认浏览器打开（调试用）")
    parser.add_argument("--no-browser", action="store_true", help="回退浏览器时也不自动打开")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser


def _ensure_streams() -> None:
    """Windows 无控制台打包时 stdout/stderr 为 None，避免日志与 print 崩溃。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout


def _open_browser_later(url: str) -> None:
    def worker() -> None:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - 打不开浏览器不影响服务
            pass

    threading.Timer(1.0, worker).start()


def _display_available(os_name: str) -> bool:
    if os_name in ("windows", "osx"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _connect_host(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "::") else host


class DesktopBridge:
    """暴露给网页的少量桌面能力；目前只有原生的目录选择框。"""

    def __init__(self, initial_dir: str) -> None:
        self._window = None
        self._initial_dir = initial_dir

    def choose_directory(self, initial: str = "") -> str | None:
        """打开系统目录选择器，取消时返回 None。"""
        if self._window is None:
            raise RuntimeError("桌面窗口尚未初始化")
        import webview

        start = str(initial or self._initial_dir or Path.home())
        try:
            start_path = Path(os.path.expanduser(start))
            if not start_path.is_dir():
                start_path = Path.home()
        except OSError:
            start_path = Path.home()
        result = self._window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=str(start_path),
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)


def _run_window(server, url: str, config: Config) -> None:
    """启动 pywebview 桌面窗口；阻塞到窗口关闭。"""
    import webview

    bridge = DesktopBridge(str(config.game_dir))
    icon = Path(__file__).resolve().parent / "web" / "assets" / ("app.ico" if os.name == "nt" else "app.png")
    window = webview.create_window(
        APP_NAME,
        url=url,
        js_api=bridge,
        width=1180,
        height=720,
        min_size=(1000, 640),
        background_color="#f4f5f8",
        text_select=True,
        confirm_close=False,
    )
    if window is None:
        raise RuntimeError("无法创建桌面窗口")
    bridge._window = window

    def shutdown_server() -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    window.events.closed += shutdown_server
    webview.start(
        icon=str(icon) if icon.is_file() else None,
        private_mode=False,
    )


def _serve_in_background(server) -> threading.Thread:
    def worker() -> None:
        try:
            server.serve_forever(poll_interval=0.4)
        except Exception:  # noqa: BLE001
            logger.exception("本地服务异常退出")

    thread = threading.Thread(target=worker, name="pcl-http", daemon=True)
    thread.start()
    return thread


def main() -> int:
    _ensure_streams()
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
    logging.getLogger("pywebview").setLevel(logging.INFO)

    try:
        server = create_server(config, paths, host=args.host, port=args.port)
    except Exception as error:  # noqa: BLE001
        print(f"启动失败：{error}", file=sys.stderr)
        return 1

    arch = detect_arch()
    os_name = detect_os()
    host = _connect_host(args.host)
    url = f"http://{host}:{server.state.port}/"
    print(BANNER)
    print(f"  {APP_NAME}  v{APP_VERSION}  ·  {APP_TAGLINE}")
    print(f"  架构：{arch_label(arch)} / {os_name}   数据：{paths.data_dir}")
    print(f"  游戏目录：{config.game_dir}")
    print(f"  界面地址：{url}")
    if os_name == "linux" and arch == "arm64":
        print("  ARM64 原生库替换已就绪（LWJGL 3.3+ 版本生效）。")
    elif os_name == "linux":
        print("  提示：当前不是 ARM64，ARM64 原生库补丁不会生效（界面与下载功能不受影响）。")
    else:
        print("  原生库：按当前系统从官方版本清单自动匹配。")
    print()

    server_thread = _serve_in_background(server)
    use_window = not args.no_window and not args.browser
    window_error = ""
    if use_window:
        if not _display_available(os_name):
            use_window = False
            window_error = "没有检测到图形显示服务"
        else:
            try:
                print("  正在打开桌面窗口…")
                _run_window(server, url, config)
                server_thread.join(timeout=2)
                server.server_close()
                return 0
            except Exception as error:  # noqa: BLE001
                use_window = False
                window_error = str(error)
                logger.exception("桌面窗口启动失败，回退到浏览器")

    if window_error:
        print(f"  桌面窗口不可用：{window_error}")
        print("  已回退到浏览器模式；也可以加 --browser 显式使用浏览器。")
    if not args.no_browser:
        _open_browser_later(url)

    print("  按 Ctrl+C 退出。\n")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
