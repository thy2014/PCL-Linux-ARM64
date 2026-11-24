"""启动命令构建与游戏进程管理。"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from . import java_runtime
from .config import APP_NAME, APP_VERSION, Config, Paths, detect_arch, detect_os
from .http_client import FetchError
from .installer import mark_played
from .minecraft import MinecraftService, required_java_major, resolve_libraries
from .util import offline_uuid

PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str, context: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda match: str(context.get(match.group(1), "")), value)


def _expand_arguments(
    items: Any,
    context: dict[str, str],
    os_name: str,
    arch: str,
    features: dict[str, bool],
) -> list[str]:
    from .minecraft import rules_allow

    if isinstance(items, str):
        return [_expand(items, context)]
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(_expand(item, context))
        elif isinstance(item, dict):
            if not rules_allow(item.get("rules"), os_name, arch, features):
                continue
            value = item.get("value")
            if isinstance(value, list):
                result.extend(_expand(str(part), context) for part in value)
            elif value is not None:
                result.append(_expand(str(value), context))
    return result


def build_launch(
    config: Config,
    paths: Paths,
    service: MinecraftService,
    version_id: str,
    *,
    username: str | None = None,
    memory_mb: int | None = None,
    jvm_args: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fullscreen: bool | None = None,
    account: dict[str, Any] | None = None,
    server: dict[str, Any] | None = None,
) -> dict[str, Any]:
    version_json = service.local_version_json(version_id)
    if not version_json:
        raise FetchError(f"版本 {version_id} 尚未安装")
    root_dir = config.ensure_game_dir()
    meta = service.version_meta(version_id)
    content_dir = config.version_game_dir(version_id, meta)
    content_dir.mkdir(parents=True, exist_ok=True)
    version_dir = root_dir / "versions" / version_id
    client_jar = version_dir / f"{version_id}.jar"
    if not client_jar.exists():
        raise FetchError(f"客户端文件缺失，请重新安装 {version_id}")

    settings = config.snapshot()
    overrides = meta.get("overrides") if isinstance(meta.get("overrides"), dict) else {}
    if account and account.get("name"):
        player = str(account["name"]).strip()[:16]
    else:
        player = (username or settings.get("username") or "Steve").strip()[:16] or "Steve"
    memory = int(memory_mb or overrides.get("memory_mb") or settings.get("memory_mb") or 4096)
    memory = max(512, min(65536, memory))
    min_memory = min(int(settings.get("min_memory_mb") or 512), memory)
    custom_width = int(width if width is not None else overrides.get("width", settings.get("width") or 0) or 0)
    custom_height = int(height if height is not None else overrides.get("height", settings.get("height") or 0) or 0)
    is_fullscreen = bool(fullscreen if fullscreen is not None else overrides.get("fullscreen", settings.get("fullscreen")))
    extra_jvm = jvm_args if jvm_args is not None else str(overrides.get("jvm_args", settings.get("jvm_args") or "") or "")

    arch = detect_arch()
    os_name = detect_os()
    features = {
        "has_custom_resolution": custom_width > 0 and custom_height > 0,
        "has_quick_plays_support": False,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
        "is_demo_user": False,
        "is_fullscreen": is_fullscreen,
    }
    plan = resolve_libraries(
        version_json,
        os_name,
        arch,
        features,
        arm64_patch=bool(settings.get("arm64_patch", True)),
    )
    library_base = root_dir / "libraries"
    classpath: list[str] = []
    missing: list[str] = []
    for entry in plan["classpath"]:
        path = (library_base / entry["path"]).resolve()
        if path.exists():
            classpath.append(str(path))
        else:
            missing.append(entry["path"])
    if missing:
        raise FetchError(f"依赖库缺失 {len(missing)} 个，请重新安装该版本（例如 {missing[0]}）")
    classpath.append(str(client_jar.resolve()))

    natives_dir = version_dir / "natives"
    natives_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = root_dir / "assets"
    assets_index = str((version_json.get("assetIndex") or {}).get("id") or version_id)
    if not (assets_dir / "indexes" / f"{assets_index}.json").exists():
        raise FetchError("资源索引缺失，请重新安装该版本")
    required_java = required_java_major(version_json)
    java = java_runtime.pick_java(config, paths, required_java, str(overrides.get("java_path") or "") or None)

    context = {
        "auth_player_name": player,
        "auth_uuid": str((account or {}).get("uuid") or offline_uuid(player)),
        "auth_access_token": str((account or {}).get("access_token") or "0"),
        "auth_session": str((account or {}).get("access_token") or "0"),
        "clientid": str((account or {}).get("client_id") or ""),
        "auth_xuid": str((account or {}).get("xuid") or ""),
        "user_type": str((account or {}).get("user_type") or "legacy"),
        "user_properties": "{}",
        "version_name": version_id,
        "version_type": str(version_json.get("type") or "release"),
        "game_directory": str(content_dir),
        "assets_root": str(assets_dir),
        "assets_index_name": assets_index,
        "natives_directory": str(natives_dir),
        "library_directory": str(library_base),
        "versions_directory": str(root_dir / "versions"),
        "classpath": os.pathsep.join(classpath),
        "classpath_separator": os.pathsep,
        "launcher_name": APP_NAME,
        "launcher_version": APP_VERSION,
        "resolution_width": str(custom_width or 854),
        "resolution_height": str(custom_height or 480),
        "quickPlayPath": "",
        "quickPlaySingleplayer": "",
        "quickPlayMultiplayer": "",
        "quickPlayRealms": "",
    }

    arguments = version_json.get("arguments") or {}
    jvm_list = _expand_arguments(arguments.get("jvm") or [], context, os_name, arch, features)
    game_list = _expand_arguments(arguments.get("game") or [], context, os_name, arch, features)
    if not jvm_list:
        jvm_list = [
            f"-Djava.library.path={context['natives_directory']}",
            "-cp",
            context["classpath"],
        ]
    if not game_list and version_json.get("minecraftArguments"):
        game_list = [_expand(part, context) for part in shlex.split(version_json["minecraftArguments"])]

    has_classpath = any(arg in ("-cp", "-classpath") or arg.startswith("-cp=") for arg in jvm_list)
    if not has_classpath:
        jvm_list = ["-cp", context["classpath"]] + jvm_list
    if not any(arg.startswith("-Djava.library.path=") for arg in jvm_list):
        jvm_list.insert(0, f"-Djava.library.path={context['natives_directory']}")
    if not any(arg.startswith("-Dminecraft.launcher.brand=") for arg in jvm_list):
        jvm_list.append(f"-Dminecraft.launcher.brand={APP_NAME}")
        jvm_list.append(f"-Dminecraft.launcher.version={APP_VERSION}")
    if is_fullscreen and "--fullscreen" not in game_list:
        game_list.append("--fullscreen")
    if server and server.get("host"):
        address = str(server["host"])
        port = int(server.get("port") or 25565)
        if "--quickPlayMultiplayer" not in game_list:
            game_list.extend(["--quickPlayMultiplayer", f"{address}:{port}"])

    user_jvm: list[str] = []
    if extra_jvm.strip():
        try:
            user_jvm = shlex.split(extra_jvm)
        except ValueError as error:
            raise FetchError(f"JVM 参数格式错误：{error}") from error

    main_class = str(version_json.get("mainClass") or "")
    if not main_class:
        raise FetchError("版本 JSON 缺少 mainClass")
    java_executable = str(java["path"])
    if os.name == "nt":
        javaw = Path(java_executable).with_name("javaw.exe")
        if javaw.exists():
            java_executable = str(javaw)
    command = [
        java_executable,
        f"-Xmx{memory}M",
        f"-Xms{min_memory}M",
        *user_jvm,
        *jvm_list,
        main_class,
        *game_list,
    ]
    return {
        "command": command,
        "java": java,
        "version": version_id,
        "required_java": required_java,
        "memory_mb": memory,
        "username": player,
        "cwd": str(content_dir),
        "native_patched": plan["patched"],
    }


class LaunchManager:
    def __init__(self, config: Config, paths: Paths, service: MinecraftService) -> None:
        self.config = config
        self.paths = paths
        self.service = service
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._status: dict[str, Any] = {
            "running": False,
            "version": "",
            "java": "",
            "pid": None,
            "exit_code": None,
            "started_at": None,
            "logs": [],
            "log_file": "",
            "error": "",
            "command": [],
        }
        self._logs: deque[str] = deque(maxlen=500)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = dict(self._status)
            data["logs"] = list(self._logs)
            data["elapsed"] = int(time.time() - data["started_at"]) if data.get("started_at") else 0
            return data

    def _append_log(self, line: str) -> None:
        text = line.rstrip("\n")
        if not text:
            return
        stamp = time.strftime("%H:%M:%S")
        with self._lock:
            self._logs.append(f"[{stamp}] {text}")

    def launch(self, **overrides: Any) -> dict[str, Any]:
        with self._lock:
            if self._status.get("running"):
                raise FetchError("游戏已在运行中")
        prepared = build_launch(self.config, self.paths, self.service, **overrides)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        log_file = self.paths.logs_dir / f"launch-{stamp}.log"
        env = dict(os.environ)
        try:
            process = subprocess.Popen(
                prepared["command"],
                cwd=prepared["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError as error:
            raise FetchError(f"启动失败：{error}") from error

        with self._lock:
            self._logs.clear()
            self._process = process
            self._status = {
                "running": True,
                "version": prepared["version"],
                "java": f"{prepared['java']['vendor']} {prepared['java']['version']}",
                "pid": process.pid,
                "exit_code": None,
                "started_at": time.time(),
                "log_file": str(log_file),
                "error": "",
                "command": prepared["command"],
            }
        self._append_log(
            f"使用 {prepared['java']['vendor']} Java {prepared['java']['version']} 启动 {prepared['version']}"
        )
        if prepared["native_patched"]:
            self._append_log(f"ARM64：已加载 {prepared['native_patched']} 个 arm64 原生库")
        mark_played(self.config, prepared["version"], prepared["java"]["version"])
        self._reader_thread = threading.Thread(
            target=self._read_output,
            args=(process, log_file),
            name="pcl-launch-log",
            daemon=True,
        )
        self._reader_thread.start()
        return self.snapshot()

    def _read_output(self, process: subprocess.Popen, log_file: Path) -> None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = open(log_file, "w", encoding="utf-8", buffering=1)
        except OSError:
            handle = None
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self._append_log(line)
                    if handle:
                        handle.write(line)
            code = process.wait()
        except Exception as error:  # noqa: BLE001 - 读取线程需要保活
            self._append_log(f"读取游戏输出失败：{error}")
            code = process.poll()
        finally:
            if handle:
                handle.close()
        with self._lock:
            self._status["running"] = False
            self._status["exit_code"] = code
            self._process = None
        self._append_log(f"游戏进程已退出（代码 {code}）" if code is not None else "游戏进程已退出")

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
        if not process or process.poll() is not None:
            return self.snapshot()
        self._append_log("正在结束游戏进程…")
        try:
            process.terminate()
        except OSError:
            pass

        def kill_later() -> None:
            for _ in range(20):
                if process.poll() is not None:
                    return
                time.sleep(0.25)
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass

        threading.Thread(target=kill_later, name="pcl-launch-stop", daemon=True).start()
        return self.snapshot()
