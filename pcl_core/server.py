"""本地 HTTP 服务：静态界面 + JSON API。"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import content, diagnostics, installer, java_runtime, loaders, modrinth, servers
from .config import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    PROJECT_URL,
    Config,
    Paths,
    arch_label,
    detect_arch,
    detect_os,
)
from .accounts import AccountStore
from .http_client import DownloadCancelled, FetchError
from .launcher import LaunchManager
from .minecraft import MinecraftService
from .tasks import Task, TaskCancelled, TaskManager
from .util import atomic_write_json, format_date, valid_version_id

logger = logging.getLogger("pcl.server")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 1024 * 1024

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


class SettingsError(Exception):
    pass


class AppState:
    def __init__(self, config: Config, paths: Paths) -> None:
        self.config = config
        self.paths = paths
        self.service = MinecraftService(config, paths)
        self.tasks = TaskManager()
        self.launch = LaunchManager(config, paths, self.service)
        self.accounts = AccountStore(paths, str(config.get("username") or "Steve"))
        self.servers = servers.ServerStore(paths)
        self.token = secrets.token_hex(24)
        self.host = "127.0.0.1"
        self.port = 0
        self.arch = detect_arch()
        self.os_name = detect_os()
        self._java_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
        self._installed_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
        self._cache_lock = threading.RLock()

    # ---- 缓存 ----
    def java_list(self, force: bool = False) -> list[dict[str, Any]]:
        with self._cache_lock:
            cached_at, cached = self._java_cache
            if not force and cached and time.time() - cached_at < 60:
                return cached
        detected = java_runtime.detect_java(self.config, self.paths)
        with self._cache_lock:
            self._java_cache = (time.time(), detected)
        return detected

    def invalidate_java(self) -> None:
        with self._cache_lock:
            self._java_cache = (0.0, [])

    def installed(self, force: bool = False) -> list[dict[str, Any]]:
        with self._cache_lock:
            cached_at, cached = self._installed_cache
            if not force and time.time() - cached_at < 10:
                return cached
        versions = self.service.installed_versions()
        with self._cache_lock:
            self._installed_cache = (time.time(), versions)
        return versions

    def invalidate_installed(self) -> None:
        with self._cache_lock:
            self._installed_cache = (0.0, [])

    def invalidate_all(self) -> None:
        self.invalidate_installed()
        self.invalidate_java()

    def active_tasks(self) -> list[dict[str, Any]]:
        result = []
        for snapshot in self.tasks.list():
            if snapshot["status"] in ("running", "cancelling"):
                result.append(
                    {
                        "id": snapshot["id"],
                        "kind": snapshot["kind"],
                        "title": snapshot["title"],
                        "phase": snapshot["phase"],
                        "status": snapshot["status"],
                        "percent": snapshot["percent"],
                    }
                )
        return result[:5]

    def bootstrap(self) -> dict[str, Any]:
        settings = self.config.snapshot()
        manifest = self.service.cached_manifest(str(settings.get("download_source") or "official"))
        latest = (manifest or {}).get("latest") or {}
        launch = self.launch.snapshot()
        return {
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "tagline": APP_TAGLINE,
                "project_url": PROJECT_URL,
                "os": self.os_name,
                "arch": self.arch,
                "arch_label": arch_label(self.arch),
            },
            "dirs": {
                "data": str(self.paths.data_dir),
                "game": str(self.config.game_dir),
                "java": str(self.paths.java_dir),
                "logs": str(self.paths.logs_dir),
            },
            "settings": settings,
            "java": self.java_list(),
            "installed": self.installed(),
            "account": self.accounts.selected(),
            "accounts": self.accounts.list(),
            "servers": self.servers.list(),
            "latest": latest,
            "version_count": len((manifest or {}).get("versions") or []),
            "tasks": self.active_tasks(),
            "launch": {
                "running": launch["running"],
                "version": launch["version"],
                "exit_code": launch["exit_code"],
            },
            "token": self.token,
        }


def _coerce_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise SettingsError(f"{field} 必须是整数") from error
    if number < minimum or number > maximum:
        raise SettingsError(f"{field} 必须在 {minimum} 到 {maximum} 之间")
    return number


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def validate_settings(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    current = state.config.snapshot()
    if "game_dir" in body:
        raw = str(body.get("game_dir") or "").strip()
        if not raw:
            raise SettingsError("游戏目录不能为空")
        path = Path(os.path.expanduser(raw)).resolve()
        if path.exists() and not path.is_dir():
            raise SettingsError("游戏目录是一个文件，请选择文件夹")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise SettingsError(f"无法创建游戏目录：{error}") from error
        patch["game_dir"] = str(path)
    if "java_path" in body:
        raw = str(body.get("java_path") or "").strip()
        if raw:
            path = Path(os.path.expanduser(raw)).resolve()
            if not path.is_file() or not os.access(path, os.X_OK):
                raise SettingsError("Java 路径不存在或不可执行")
            patch["java_path"] = str(path)
        else:
            patch["java_path"] = ""
    if "memory_mb" in body:
        patch["memory_mb"] = _coerce_int(body.get("memory_mb"), "内存", 512, 65536)
    if "min_memory_mb" in body:
        patch["min_memory_mb"] = _coerce_int(body.get("min_memory_mb"), "最小内存", 128, 65536)
    memory = int(patch.get("memory_mb", current.get("memory_mb") or 4096))
    min_memory = int(patch.get("min_memory_mb", current.get("min_memory_mb") or 512))
    if min_memory > memory:
        raise SettingsError("最小内存不能大于最大内存")
    if "username" in body:
        username = re.sub(r"[\x00-\x1f\x7f]", "", str(body.get("username") or "")).strip()
        if not username or len(username) > 16:
            raise SettingsError("玩家名需为 1-16 个字符")
        patch["username"] = username
    if "download_source" in body:
        source = str(body.get("download_source") or "")
        if source not in ("official", "bmclapi"):
            raise SettingsError("未知下载源")
        patch["download_source"] = source
    if "download_threads" in body:
        patch["download_threads"] = _coerce_int(body.get("download_threads"), "下载线程", 1, 32)
    for key in ("arm64_patch", "fullscreen", "keep_launcher", "version_isolation", "show_snapshots"):
        if key in body:
            patch[key] = _coerce_bool(body.get(key))
    if "theme" in body:
        theme = str(body.get("theme") or "blue")
        if theme not in ("blue", "green", "purple", "orange", "red", "cyan", "dark"):
            raise SettingsError("未知主题")
        patch["theme"] = theme
    if "width" in body:
        patch["width"] = _coerce_int(body.get("width"), "窗口宽度", 0, 7680)
    if "height" in body:
        patch["height"] = _coerce_int(body.get("height"), "窗口高度", 0, 4320)
    if "jvm_args" in body:
        text = str(body.get("jvm_args") or "")
        if len(text) > 512:
            raise SettingsError("JVM 参数过长（最多 512 字符）")
        patch["jvm_args"] = text
    return patch


def _run_install(
    state: AppState,
    task: Task,
    version: str,
    source: str,
    auto_java: bool,
    java_major: int | None,
    loader: str = "",
    loader_version: str = "",
) -> None:
    try:
        installer.install_version(
            state.config,
            state.paths,
            state.service,
            task,
            version,
            source=source,
            auto_java=auto_java,
            java_major=java_major,
            finalize=not bool(loader),
        )
        if loader:
            task.set_phase("安装加载器")
            task.log(f"原版安装完成，继续安装 {loader} {loader_version}")
            loaders.install_loader(
                state.config,
                state.paths,
                state.service,
                task,
                loader,
                version,
                loader_version,
                source=source,
                auto_java=auto_java,
            )
    except (TaskCancelled, DownloadCancelled):
        task.mark_cancelled()
    except Exception as error:  # noqa: BLE001 - 任务边界
        logger.exception("安装失败")
        task.fail(str(error))
    finally:
        state.invalidate_all()


def _run_java_download(state: AppState, task: Task, major: int) -> None:
    try:
        asset = java_runtime.resolve_jdk(major, state.arch)
        java_runtime.install_jdk(task, state.config, major, asset)
        task.finish(f"Java {major} 安装完成")
    except (TaskCancelled, DownloadCancelled):
        task.mark_cancelled()
    except Exception as error:  # noqa: BLE001
        logger.exception("Java 下载失败")
        task.fail(str(error))
    finally:
        state.invalidate_java()


def _run_loader(state: AppState, task: Task, loader: str, game: str, loader_version: str, source: str, auto_java: bool) -> None:
    try:
        loaders.install_loader(
            state.config, state.paths, state.service, task,
            loader, game, loader_version, source=source, auto_java=auto_java,
        )
    except (TaskCancelled, DownloadCancelled):
        task.mark_cancelled()
    except Exception as error:  # noqa: BLE001
        logger.exception("加载器安装失败")
        task.fail(str(error))
    finally:
        state.invalidate_all()


def _run_modrinth(state: AppState, task: Task, version: str, project_type: str, slug: str, project_version_id: str | None, game: str) -> None:
    try:
        modrinth.install_project(
            state.config, state.paths, state.service, task, version, project_type, slug,
            project_version_id=project_version_id, game=game,
        )
    except (TaskCancelled, DownloadCancelled):
        task.mark_cancelled()
    except Exception as error:  # noqa: BLE001
        logger.exception("资源安装失败")
        task.fail(str(error))
    finally:
        state.invalidate_installed()


def _run_modpack(state: AppState, task: Task, source_version: str, slug: str, project_version_id: str | None) -> None:
    try:
        modrinth.install_modpack(
            state.config, state.paths, state.service, task, source_version, slug,
            project_version_id=project_version_id,
        )
    except (TaskCancelled, DownloadCancelled):
        task.mark_cancelled()
    except Exception as error:  # noqa: BLE001
        logger.exception("整合包安装失败")
        task.fail(str(error))
    finally:
        state.invalidate_all()


class Handler(BaseHTTPRequestHandler):
    server_version = "PCL/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> AppState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    # ---- 响应 ----
    def _send(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", payload)

    def _ok(self, data: dict[str, Any] | None = None) -> None:
        body = {"ok": True}
        if data:
            body.update(data)
        self._json(200, body)

    def _error(self, message: str, status: int = 400) -> None:
        self._json(status, {"ok": False, "error": message})

    # ---- 鉴权 ----
    def _check_write_auth(self) -> bool:
        token = self.headers.get("X-PCL-Token") or ""
        if not hmac.compare_digest(token, self.state.token):
            self._error("本地令牌无效，请刷新页面", 403)
            return False
        origin = (self.headers.get("Origin") or "").strip()
        port = self.state.port
        allowed = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        }
        if origin and origin not in allowed:
            self._error("来源校验失败", 403)
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            raise SettingsError("请求体过大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SettingsError("JSON 格式错误") from error
        if not isinstance(data, dict):
            raise SettingsError("请求体必须是 JSON 对象")
        return data

    # ---- 路由 ----
    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path.startswith("/api/"):
                self._get_api(path, query)
            else:
                self._serve_static(path)
        except SettingsError as error:
            self._error(str(error), 400)
        except FetchError as error:
            self._error(str(error), 400)
        except Exception:  # noqa: BLE001 - HTTP 边界
            logger.exception("GET 处理失败")
            self._error("服务器内部错误", 500)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if not self._check_write_auth():
                return
            parsed = urlsplit(self.path)
            body = self._read_json()
            self._post_api(parsed.path, body)
        except SettingsError as error:
            self._error(str(error))
        except FetchError as error:
            self._error(str(error), 400)
        except Exception:  # noqa: BLE001
            logger.exception("POST 处理失败")
            self._error("服务器内部错误", 500)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_DIR / relative).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._error("路径非法", 404)
            return
        if not target.is_file():
            self._error("页面不存在", 404)
            return
        content_type = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, content_type, target.read_bytes())

    def _get_api(self, path: str, query: dict[str, list[str]]) -> None:
        state = self.state
        if path == "/api/bootstrap":
            self._ok(state.bootstrap())
            return
        if path == "/api/versions":
            source = (query.get("source") or [state.config.get("download_source") or "official"])[0]
            if source not in ("official", "bmclapi"):
                source = "official"
            refresh = (query.get("refresh") or ["0"])[0] in ("1", "true", "yes")
            try:
                data = state.service.list_versions(source, refresh=refresh)
            except FetchError as error:
                self._error(f"获取版本列表失败：{error}", 502)
                return
            installed = {item["id"] for item in state.installed()}
            for version in data["versions"]:
                version["installed"] = version["id"] in installed
                version["releaseDate"] = format_date(
                    _timestamp_from_iso(version.get("releaseTime"))
                )
            data["count"] = len(data["versions"])
            self._ok(data)
            return
        if path == "/api/installed":
            self._ok({"installed": state.installed(force=True)})
            return
        if path == "/api/accounts":
            self._ok(state.accounts.list())
            return
        if path == "/api/servers":
            self._ok({"servers": state.servers.list()})
            return
        if path == "/api/servers/ping":
            host = (query.get("host") or [""])[0].strip()
            try:
                port = int((query.get("port") or ["25565"])[0])
            except ValueError:
                raise SettingsError("端口不合法")
            self._ok({"ping": servers.ping(host, port)})
            return
        if path == "/api/content":
            version = (query.get("version") or [""])[0]
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            self._ok(content.scan(state.config, state.service, version))
            return
        if path == "/api/version/settings":
            version = (query.get("version") or [""])[0]
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            if not state.service.local_version_json(version):
                raise SettingsError("版本尚未安装")
            meta = state.service.version_meta(version)
            self._ok(
                {
                    "version": version,
                    "meta": meta,
                    "overrides": meta.get("overrides") or {},
                    "isolated": bool(meta["isolated"]) if isinstance(meta.get("isolated"), bool) else bool(state.config.get("version_isolation", True)),
                    "game_dir": str(state.config.version_game_dir(version, meta)),
                }
            )
            return
        if path == "/api/diagnose":
            version = (query.get("version") or [""])[0]
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            self._ok({"diagnosis": diagnostics.analyze(state.config, state.service, version)})
            return
        if path == "/api/loaders":
            self._ok({"loaders": loaders.LOADER_TYPES})
            return
        if path == "/api/loader/versions":
            loader = (query.get("type") or [""])[0].lower()
            game = (query.get("game") or [""])[0]
            source = (query.get("source") or ["official"])[0].lower()
            if loader not in ("fabric", "quilt", "forge", "neoforge"):
                raise SettingsError("不支持的加载器")
            if not valid_version_id(game):
                raise SettingsError("游戏版本不合法")
            try:
                data = loaders.loader_versions(loader, game, source)
            except FetchError as error:
                self._error(f"获取加载器版本失败：{error}", 502)
                return
            self._ok(data)
            return
        if path == "/api/modrinth/search":
            project_type = (query.get("type") or ["mod"])[0]
            if project_type not in ("mod", "modpack", "resourcepack", "shader"):
                raise SettingsError("未知资源类型")
            q = (query.get("q") or [""])[0]
            game = (query.get("game") or [""])[0]
            loader = (query.get("loader") or [""])[0]
            try:
                offset = int((query.get("offset") or ["0"])[0])
                limit = int((query.get("limit") or ["24"])[0])
            except ValueError:
                raise SettingsError("分页参数不合法")
            try:
                data = modrinth.search(project_type, q, game, loader, offset, limit)
            except FetchError as error:
                self._error(f"Modrinth 请求失败：{error}", 502)
                return
            self._ok(data)
            return
        if path == "/api/modrinth/versions":
            slug = (query.get("slug") or [""])[0].strip()
            if not slug:
                raise SettingsError("缺少项目标识")
            game = (query.get("game") or [""])[0]
            loader = (query.get("loader") or [""])[0]
            try:
                versions = modrinth.project_versions(slug, game, loader)
            except FetchError as error:
                self._error(f"Modrinth 请求失败：{error}", 502)
                return
            self._ok({"versions": versions})
            return
        if path == "/api/java":
            force = (query.get("refresh") or ["0"])[0] in ("1", "true")
            self._ok({"java": state.java_list(force=force), "arch": state.arch})
            return
        if path == "/api/settings":
            self._ok({"settings": state.config.snapshot()})
            return
        if path == "/api/tasks":
            tasks = [
                item
                for item in state.tasks.list()
                if item["status"] in ("running", "cancelling")
            ]
            self._ok({"tasks": tasks[:6]})
            return
        if path.startswith("/api/task/"):
            task_id = path.rsplit("/", 1)[-1]
            snapshot = state.tasks.snapshot(task_id)
            if not snapshot:
                self._error("任务不存在", 404)
                return
            self._ok({"task": snapshot})
            return
        if path == "/api/launch":
            launch = state.launch.snapshot()
            if (query.get("status") or ["0"])[0] in ("1", "true"):
                launch.pop("logs", None)
                launch.pop("command", None)
                launch.pop("log_file", None)
            self._ok({"launch": launch})
            return
        self._error("接口不存在", 404)

    def _post_api(self, path: str, body: dict[str, Any]) -> None:
        state = self.state
        if path == "/api/settings":
            patch = validate_settings(state, body)
            settings = state.config.update(patch)
            if "username" in patch:
                try:
                    state.accounts.rename_selected(str(patch["username"]))
                except FetchError:
                    pass
            state.invalidate_all()
            self._ok({"settings": settings, "java": state.java_list(force=True)})
            return
        if path == "/api/accounts/add":
            account = state.accounts.add(str(body.get("name") or ""))
            state.config.update({"username": account["name"]})
            self._ok(state.accounts.list())
            return
        if path == "/api/accounts/select":
            account = state.accounts.select(str(body.get("id") or ""))
            state.config.update({"username": account["name"]})
            self._ok(state.accounts.list())
            return
        if path == "/api/accounts/remove":
            state.accounts.remove(str(body.get("id") or ""))
            selected = state.accounts.selected()
            state.config.update({"username": selected.get("name") or "Steve"})
            self._ok(state.accounts.list())
            return
        if path == "/api/servers/add":
            server = state.servers.add(str(body.get("name") or ""), str(body.get("host") or ""), int(body.get("port") or 25565))
            self._ok({"servers": state.servers.list(), "server": server})
            return
        if path == "/api/servers/update":
            server = state.servers.update(str(body.get("id") or ""), body)
            self._ok({"servers": state.servers.list(), "server": server})
            return
        if path == "/api/servers/delete":
            state.servers.delete(str(body.get("id") or ""))
            self._ok({"servers": state.servers.list()})
            return
        if path == "/api/content/toggle":
            version = str(body.get("version") or "")
            kind = str(body.get("kind") or "")
            name = str(body.get("name") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            result = content.toggle(state.config, state.service, version, kind, name)
            self._ok({"item": result})
            return
        if path == "/api/content/delete":
            version = str(body.get("version") or "")
            kind = str(body.get("kind") or "")
            name = str(body.get("name") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            content.delete(state.config, state.service, version, kind, name)
            self._ok()
            return
        if path == "/api/content/import":
            version = str(body.get("version") or "")
            kind = str(body.get("kind") or "")
            source = str(body.get("source") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            result = content.import_content(state.config, state.service, version, kind, source)
            self._ok({"item": result})
            return
        if path == "/api/content/backup":
            version = str(body.get("version") or "")
            name = str(body.get("name") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            result = content.backup_save(state.config, state.service, version, name)
            self._ok({"backup": result})
            return
        if path == "/api/version/settings":
            version = str(body.get("version") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            if not state.service.local_version_json(version):
                raise SettingsError("版本尚未安装")
            meta = state.service.version_meta(version)
            overrides = dict(meta.get("overrides") or {}) if isinstance(meta.get("overrides"), dict) else {}
            if "isolated" in body:
                isolated = _coerce_bool(body.get("isolated"))
                if state.launch.snapshot().get("running") and state.launch.snapshot().get("version") == version:
                    raise SettingsError("版本正在运行，请先结束游戏再切换版本隔离")
                meta["isolated"] = isolated
            if "memory_mb" in body:
                value = _coerce_int(body.get("memory_mb"), "内存", 0, 65536)
                if value:
                    overrides["memory_mb"] = max(512, value)
                else:
                    overrides.pop("memory_mb", None)
            if "java_path" in body:
                raw = str(body.get("java_path") or "").strip()
                if raw:
                    path = Path(os.path.expanduser(raw)).resolve()
                    if not path.is_file() or not os.access(path, os.X_OK):
                        raise SettingsError("Java 路径不存在或不可执行")
                    overrides["java_path"] = str(path)
                else:
                    overrides.pop("java_path", None)
            if "jvm_args" in body:
                text = str(body.get("jvm_args") or "")
                if len(text) > 512:
                    raise SettingsError("JVM 参数过长")
                if text.strip():
                    overrides["jvm_args"] = text
                else:
                    overrides.pop("jvm_args", None)
            if "width" in body:
                value = _coerce_int(body.get("width"), "窗口宽度", 0, 7680)
                if value:
                    overrides["width"] = value
                else:
                    overrides.pop("width", None)
            if "height" in body:
                value = _coerce_int(body.get("height"), "窗口高度", 0, 4320)
                if value:
                    overrides["height"] = value
                else:
                    overrides.pop("height", None)
            if "fullscreen" in body:
                overrides["fullscreen"] = _coerce_bool(body.get("fullscreen"))
            meta["overrides"] = overrides
            atomic_write_json(state.config.game_dir / "versions" / version / "pcl_meta.json", meta)
            state.invalidate_installed()
            self._ok({"meta": meta, "overrides": overrides, "isolated": bool(meta.get("isolated")) if isinstance(meta.get("isolated"), bool) else bool(state.config.get("version_isolation", True)), "game_dir": str(state.config.version_game_dir(version, meta))})
            return
        if path == "/api/loader/install":
            loader = str(body.get("type") or "").lower()
            game = str(body.get("game") or "")
            loader_version = str(body.get("loader") or "").strip()
            if loader not in ("fabric", "quilt", "forge", "neoforge"):
                raise SettingsError("不支持的加载器")
            if not valid_version_id(game):
                raise SettingsError("游戏版本不合法")
            if not re.match(r"^[A-Za-z0-9._+-]{1,64}$", loader_version):
                raise SettingsError("加载器版本不合法")
            source = str(body.get("source") or state.config.get("download_source") or "official")
            if source not in ("official", "bmclapi"):
                raise SettingsError("未知下载源")
            auto_java = _coerce_bool(body.get("auto_java", True))
            task = state.tasks.create("loader", f"安装 {loader.title()} {loader_version}")
            threading.Thread(target=_run_loader, args=(state, task, loader, game, loader_version, source, auto_java), daemon=True, name=f"loader-{task.id}").start()
            self._ok({"task": task.snapshot(), "task_id": task.id})
            return
        if path == "/api/modrinth/install":
            version = str(body.get("version") or "")
            project_type = str(body.get("type") or "")
            slug = str(body.get("slug") or "")
            project_version_id = str(body.get("project_version_id") or "") or None
            game = str(body.get("game") or "")
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            if project_type not in ("mod", "resourcepack", "shader"):
                raise SettingsError("未知资源类型")
            if not re.match(r"^[A-Za-z0-9._-]{1,80}$", slug):
                raise SettingsError("项目标识不合法")
            task = state.tasks.create("resource", f"安装资源 {slug}")
            threading.Thread(target=_run_modrinth, args=(state, task, version, project_type, slug, project_version_id, game), daemon=True, name=f"resource-{task.id}").start()
            self._ok({"task": task.snapshot(), "task_id": task.id})
            return
        if path == "/api/modrinth/install_modpack":
            source_version = str(body.get("source_version") or "")
            slug = str(body.get("slug") or "")
            project_version_id = str(body.get("project_version_id") or "") or None
            if not valid_version_id(source_version):
                raise SettingsError("基础版本不合法")
            if not re.match(r"^[A-Za-z0-9._-]{1,80}$", slug):
                raise SettingsError("整合包标识不合法")
            task = state.tasks.create("modpack", f"安装整合包 {slug}")
            threading.Thread(target=_run_modpack, args=(state, task, source_version, slug, project_version_id), daemon=True, name=f"modpack-{task.id}").start()
            self._ok({"task": task.snapshot(), "task_id": task.id})
            return
        if path == "/api/install":
            version = str(body.get("version") or "").strip()
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            source = str(body.get("source") or state.config.get("download_source") or "official")
            if source not in ("official", "bmclapi"):
                raise SettingsError("未知下载源")
            auto_java = _coerce_bool(body.get("auto_java", True))
            loader = str(body.get("loader_type") or "").lower()
            loader_version = str(body.get("loader_version") or "").strip()
            if loader:
                if loader not in ("fabric", "quilt", "forge", "neoforge"):
                    raise SettingsError("不支持的加载器")
                if not re.match(r"^[A-Za-z0-9._+-]{1,64}$", loader_version):
                    raise SettingsError("加载器版本不合法")
            java_major = body.get("java_major")
            if java_major in (None, "", 0):
                java_major = None
            else:
                java_major = _coerce_int(java_major, "Java 版本", 8, 25)
                auto_java = False
            loader_title = {"fabric": "Fabric", "quilt": "Quilt", "forge": "Forge", "neoforge": "NeoForge"}.get(loader, loader)
            title = f"安装 {version}" + (f" + {loader_title} {loader_version}" if loader else "")
            task = state.tasks.create("install", title)
            thread = threading.Thread(
                target=_run_install,
                args=(state, task, version, source, auto_java, java_major, loader, loader_version),
                name=f"install-{task.id}",
                daemon=True,
            )
            thread.start()
            self._ok({"task": task.snapshot(), "task_id": task.id})
            return
        if path.startswith("/api/task/") and path.endswith("/cancel"):
            task_id = path.split("/")[-2]
            if state.tasks.cancel(task_id):
                snapshot = state.tasks.snapshot(task_id)
                self._ok({"task": snapshot})
            else:
                self._error("任务不存在", 404)
            return
        if path == "/api/java/download":
            major = _coerce_int(body.get("major", 21), "Java 版本", 8, 25)
            task = state.tasks.create("java", f"下载 Java {major}")
            thread = threading.Thread(
                target=_run_java_download,
                args=(state, task, major),
                name=f"java-{task.id}",
                daemon=True,
            )
            thread.start()
            self._ok({"task": task.snapshot(), "task_id": task.id})
            return
        if path == "/api/launch":
            version = str(body.get("version") or "").strip()
            if not valid_version_id(version):
                raise SettingsError("请选择要启动的版本")
            overrides: dict[str, Any] = {"version_id": version}
            if "username" in body:
                overrides["username"] = str(body.get("username") or "")[:16]
            if "memory_mb" in body:
                overrides["memory_mb"] = _coerce_int(body.get("memory_mb"), "内存", 512, 65536)
            if "jvm_args" in body:
                overrides["jvm_args"] = str(body.get("jvm_args") or "")
            if "width" in body:
                overrides["width"] = _coerce_int(body.get("width"), "窗口宽度", 0, 7680)
            if "height" in body:
                overrides["height"] = _coerce_int(body.get("height"), "窗口高度", 0, 4320)
            if "fullscreen" in body:
                overrides["fullscreen"] = _coerce_bool(body.get("fullscreen"))
            overrides["account"] = state.accounts.selected()
            server = body.get("server")
            if isinstance(server, dict) and server.get("host"):
                overrides["server"] = {"host": str(server["host"]), "port": int(server.get("port") or 25565)}
            snapshot = state.launch.launch(**overrides)
            self._ok({"launch": snapshot})
            return
        if path == "/api/launch/stop":
            self._ok({"launch": state.launch.stop()})
            return
        if path == "/api/version/delete":
            version = str(body.get("version") or "").strip()
            if not valid_version_id(version):
                raise SettingsError("版本名不合法")
            if state.launch.snapshot().get("running") and state.launch.snapshot().get("version") == version:
                raise SettingsError("该版本正在运行，请先结束游戏")
            freed = installer.delete_version(state.config, version)
            state.invalidate_installed()
            self._ok({"freed": freed})
            return
        if path == "/api/open":
            target = str(body.get("target") or "game")
            if target == "game":
                folder = state.config.ensure_game_dir()
            elif target == "logs":
                folder = state.paths.logs_dir
            elif target == "java":
                folder = state.paths.java_dir
            elif target == "data":
                folder = state.paths.data_dir
            elif target == "version":
                version = str(body.get("version") or "")
                if not valid_version_id(version):
                    raise SettingsError("版本名不合法")
                folder = state.config.game_dir / "versions" / version
            elif target == "content":
                version = str(body.get("version") or "")
                kind = str(body.get("kind") or "")
                if not valid_version_id(version) or kind not in content.KIND_DIRS:
                    raise SettingsError("内容目录不合法")
                meta = state.service.version_meta(version)
                folder = state.config.version_game_dir(version, meta) / content.KIND_DIRS[kind]
            elif target in {"version_logs", "crash"}:
                version = str(body.get("version") or "")
                if not valid_version_id(version):
                    raise SettingsError("版本名不合法")
                meta = state.service.version_meta(version)
                root_dir = state.config.version_game_dir(version, meta)
                folder = root_dir / ("logs" if target == "version_logs" else "crash-reports")
            else:
                raise SettingsError("未知目录")
            if not folder.exists():
                raise SettingsError("目录不存在")
            if os.name == "nt":
                try:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
                except OSError as error:
                    raise SettingsError(f"无法打开目录：{error}") from error
                self._ok({"path": str(folder)})
                return
            opener = shutil.which("xdg-open") or shutil.which("open")
            if not opener:
                raise SettingsError("当前系统没有可用的文件管理器启动命令，请手动打开：" + str(folder))
            subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._ok({"path": str(folder)})
            return
        self._error("接口不存在", 404)


def _timestamp_from_iso(value: str | None) -> int | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


class LauncherHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    state: AppState


def create_server(config: Config, paths: Paths, host: str = "127.0.0.1", port: int = 3919) -> LauncherHTTPServer:
    state = AppState(config, paths)
    server = None
    last_error: Exception | None = None
    ports = [port] if port == 0 else list(range(port, port + 20))
    for candidate in ports:
        try:
            server = LauncherHTTPServer((host, candidate), Handler)
            break
        except OSError as error:
            last_error = error
            continue
    if server is None:
        raise FetchError(f"无法监听端口：{last_error}")
    server.state = state
    state.host = host
    state.port = int(server.server_address[1])
    return server
