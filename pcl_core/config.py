"""全局配置、目录与运行环境识别。"""
from __future__ import annotations

import json
import os
import platform
import threading
from pathlib import Path
from typing import Any

APP_NAME = "PCL Linux ARM64"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Plain Craft Launcher · Linux ARM64 社区版"
PROJECT_URL = "https://github.com/thy2014/PCL-Linux-ARM64"

DEFAULT_SETTINGS: dict[str, Any] = {
    "game_dir": str(Path.home() / ".minecraft"),
    "java_path": "",
    "memory_mb": 4096,
    "min_memory_mb": 512,
    "username": "Steve",
    "download_source": "official",
    "download_threads": 16,
    "arm64_patch": True,
    "jvm_args": "",
    "width": 0,
    "height": 0,
    "fullscreen": False,
    "keep_launcher": True,
    "version_isolation": True,
    "theme": "blue",
    "show_snapshots": True,
}


def detect_arch() -> str:
    """返回规范化架构：arm64 / x86_64 / arm32 / 其它。"""
    override = os.environ.get("PCL_ARCH", "").strip().lower()
    if override in ("arm64", "aarch64"):
        return "arm64"
    if override in ("x86_64", "amd64"):
        return "x86_64"
    if override in ("arm32", "armv7", "armv7l"):
        return "arm32"
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if machine.startswith("armv7") or machine == "arm":
        return "arm32"
    return machine or "unknown"


def detect_os() -> str:
    system = platform.system().lower()
    return {"linux": "linux", "darwin": "osx", "windows": "windows"}.get(system, "linux")


def arch_label(arch: str) -> str:
    return {"arm64": "ARM64", "x86_64": "x86_64", "arm32": "ARM32"}.get(arch, arch)


def is_arm64(arch: str) -> bool:
    return arch == "arm64"


class Paths:
    """应用数据目录。"""

    def __init__(self, data_dir: str | None = None) -> None:
        raw = data_dir or os.environ.get("PCL_DATA_DIR") or str(Path.home() / ".pcl-arm64")
        self.data_dir = Path(os.path.expanduser(raw)).resolve()
        self.java_dir = self.data_dir / "java"
        self.logs_dir = self.data_dir / "logs"
        self.cache_dir = self.data_dir / "cache"
        self.config_file = self.data_dir / "config.json"
        for directory in (self.data_dir, self.java_dir, self.logs_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)


class Config:
    """线程安全的配置读写，未知字段会被忽略。"""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self._lock = threading.RLock()
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.paths.config_file.exists():
                return
            try:
                raw = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            if not isinstance(raw, dict):
                return
            merged = dict(DEFAULT_SETTINGS)
            for key, value in raw.items():
                if key in DEFAULT_SETTINGS and value is not None:
                    merged[key] = value
            self.settings = merged
            self._normalize()

    def _normalize(self) -> None:
        self.settings["memory_mb"] = int(self.settings.get("memory_mb") or 4096)
        self.settings["min_memory_mb"] = int(self.settings.get("min_memory_mb") or 512)
        self.settings["download_threads"] = int(self.settings.get("download_threads") or 16)
        self.settings["username"] = str(self.settings.get("username") or "Steve")[:16]
        self.settings["game_dir"] = os.path.expanduser(str(self.settings.get("game_dir") or "~/.minecraft"))
        self.settings["version_isolation"] = bool(self.settings.get("version_isolation", True))

    def save(self) -> None:
        with self._lock:
            self._normalize()
            tmp = self.paths.config_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.paths.config_file)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in patch.items():
                if key in DEFAULT_SETTINGS and value is not None:
                    self.settings[key] = value
            self._normalize()
            self.save()
            return dict(self.settings)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.settings.get(key, default)

    @property
    def game_dir(self) -> Path:
        return Path(os.path.expanduser(str(self.settings["game_dir"]))).resolve()

    def ensure_game_dir(self) -> Path:
        self.game_dir.mkdir(parents=True, exist_ok=True)
        return self.game_dir

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.settings)

    def version_game_dir(self, version_id: str, meta: dict[str, Any] | None = None) -> Path:
        """返回某版本实际使用的游戏目录；默认按版本隔离。"""
        isolated = None
        if isinstance(meta, dict) and isinstance(meta.get("isolated"), bool):
            isolated = bool(meta["isolated"])
        if isolated is None:
            isolated = bool(self.get("version_isolation", True))
        root = self.ensure_game_dir()
        return (root / "versions" / version_id) if isolated else root
