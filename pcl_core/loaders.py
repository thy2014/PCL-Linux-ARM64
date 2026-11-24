"""模组加载器：Fabric / Quilt / Forge / NeoForge 的查询与安装。"""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from . import java_runtime
from .config import Config, Paths, detect_arch
from .http_client import FetchError, download_file, get_json, get_text
from .installer import install_version
from .minecraft import MinecraftService, merge_version_json, required_java_major
from .tasks import Task
from .util import atomic_write_json

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
FORGE_PROMOTIONS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

LOADER_TYPES = [
    {"id": "fabric", "name": "Fabric", "description": "轻量、更新快，适合大多数优化与辅助模组", "available": True},
    {"id": "forge", "name": "Forge", "description": "历史最悠久的模组平台，模组生态庞大", "available": True},
    {"id": "neoforge", "name": "NeoForge", "description": "Forge 的现代分支，面向 1.20.2+", "available": True},
    {"id": "quilt", "name": "Quilt", "description": "Fabric 的衍生平台，兼容大部分 Fabric 模组", "available": True},
    {"id": "optifine", "name": "OptiFine", "description": "光影与性能优化（受官网验证限制，暂以模组方式导入）", "available": False},
    {"id": "liteloader", "name": "LiteLoader", "description": "旧版轻量加载器（已停止维护）", "available": False},
]


def _meta_library(name: str, url: str, version: str) -> dict[str, Any]:
    return {"name": f"{name}:{version}", "url": url}


def _fabric_profile(game: str, loader: str) -> dict[str, Any]:
    url = f"{FABRIC_META}/versions/loader/{game}/{loader}/profile/json"
    data = get_json(url, timeout=25, retries=2)
    if not isinstance(data, dict) or not data.get("id"):
        raise FetchError("Fabric 配置格式不正确")
    return data


def _quilt_profile(game: str, loader: str) -> dict[str, Any]:
    url = f"{QUILT_META}/versions/loader/{game}/{loader}/profile/json"
    data = get_json(url, timeout=25, retries=2)
    if not isinstance(data, dict) or not data.get("id"):
        raise FetchError("Quilt 配置格式不正确")
    return data


def _xml_versions(url: str) -> list[str]:
    text = get_text(url, timeout=30, retries=2)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise FetchError(f"版本元数据解析失败：{error}") from error
    versions = []
    for node in root.iter():
        if node.tag.endswith("version") and node.text:
            versions.append(node.text.strip())
    return versions


def _neo_prefix(game: str) -> str | None:
    parts = game.split(".")
    if len(parts) < 2 or parts[0] != "1":
        return None
    rest = ".".join(parts[1:])
    if rest.count(".") == 0:
        rest += ".0"
    return rest + "."


def loader_versions(loader: str, game: str) -> dict[str, Any]:
    loader = loader.lower()
    if loader == "fabric":
        data = get_json(f"{FABRIC_META}/versions/loader/{game}", timeout=25, retries=2)
        if not isinstance(data, list):
            raise FetchError("Fabric 加载器列表格式不正确")
        items = [
            {
                "version": str(item["loader"]["version"]),
                "stable": bool(item["loader"].get("stable")),
                "recommended": bool(item["loader"].get("stable")),
            }
            for item in data
            if isinstance(item, dict) and item.get("loader", {}).get("version")
        ]
        return {"loader": loader, "game": game, "versions": items[:40], "recommended": next((i["version"] for i in items if i["stable"]), items[0]["version"] if items else "")}
    if loader == "quilt":
        data = get_json(f"{QUILT_META}/versions/loader/{game}", timeout=25, retries=2)
        if not isinstance(data, list):
            raise FetchError("Quilt 加载器列表格式不正确")
        items = []
        for item in data:
            version = item.get("loader", {}).get("version") if isinstance(item, dict) else None
            if version:
                items.append({"version": str(version), "stable": "beta" not in str(version), "recommended": False})
        return {"loader": loader, "game": game, "versions": items[:40], "recommended": items[0]["version"] if items else ""}
    if loader == "forge":
        versions = []
        promotions: dict[str, Any] = {}
        try:
            promo = get_json(FORGE_PROMOTIONS, timeout=25, retries=2)
            promotions = promo.get("promos") if isinstance(promo, dict) else {}
        except FetchError:
            promotions = {}
        try:
            all_versions = _xml_versions(f"{FORGE_MAVEN}/maven-metadata.xml")
            prefix = f"{game}-"
            versions = [v[len(prefix):] for v in all_versions if v.startswith(prefix)]
        except FetchError:
            recommended = promotions.get(f"{game}-recommended") if isinstance(promotions, dict) else None
            latest = promotions.get(f"{game}-latest") if isinstance(promotions, dict) else None
            versions = [v for v in (recommended, latest) if v]
        seen = set()
        items = []
        recommended = promotions.get(f"{game}-recommended") if isinstance(promotions, dict) else None
        latest = promotions.get(f"{game}-latest") if isinstance(promotions, dict) else None
        for version in versions:
            if version in seen:
                continue
            seen.add(version)
            items.append({"version": version, "stable": True, "recommended": version == recommended})
        items.sort(key=lambda x: [int(p) if p.isdigit() else p for p in re.split(r"([0-9]+)", x["version"])], reverse=True)
        return {"loader": loader, "game": game, "versions": items[:60], "recommended": recommended or latest or (items[0]["version"] if items else "")}
    if loader == "neoforge":
        prefix = _neo_prefix(game)
        if not prefix:
            return {"loader": loader, "game": game, "versions": [], "recommended": "", "note": "NeoForge 仅支持 1.20.2 及更高版本"}
        try:
            all_versions = _xml_versions(f"{NEOFORGE_MAVEN}/maven-metadata.xml")
        except FetchError as error:
            return {"loader": loader, "game": game, "versions": [], "recommended": "", "note": f"无法获取 NeoForge 版本列表：{error}"}
        versions = [v for v in all_versions if v.startswith(prefix)]
        versions.sort(key=lambda v: [int(p) if p.isdigit() else p for p in re.split(r"([0-9]+)", v)], reverse=True)
        items = [{"version": v, "stable": "beta" not in v, "recommended": False} for v in versions[:60]]
        return {"loader": loader, "game": game, "versions": items, "recommended": items[0]["version"] if items else ""}
    raise FetchError("暂不支持该加载器")


def _installer_info(loader: str, game: str, loader_version: str) -> tuple[str, str]:
    if loader == "forge":
        base = f"{FORGE_MAVEN}/{game}-{loader_version}"
        return f"{base}/forge-{game}-{loader_version}-installer.jar", f"{game}-forge-{loader_version}"
    if loader == "neoforge":
        base = f"{NEOFORGE_MAVEN}/{loader_version}"
        return f"{base}/neoforge-{loader_version}-installer.jar", f"neoforge-{loader_version}"
    raise FetchError("该加载器不需要安装器")


def _run_installer(task: Task, java: str, installer: Path, game_dir: Path, timeout: int = 1500) -> int:
    game_dir.mkdir(parents=True, exist_ok=True)
    profiles = game_dir / "launcher_profiles.json"
    if not profiles.exists():
        atomic_write_json(profiles, {"profiles": {}, "settings": {}, "version": 2})
    env = dict(os.environ)
    env.setdefault("JAVA_TOOL_OPTIONS", "-Dfile.encoding=UTF-8")
    proc = subprocess.Popen(
        [java, "-jar", str(installer), "--installClient"],
        cwd=str(game_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    lines: "queue.Queue[str]" = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line.rstrip())
        proc.stdout.close()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    started = time.time()
    while proc.poll() is None:
        try:
            line = lines.get(timeout=0.25)
            task.log(line)
        except queue.Empty:
            pass
        if task.cancelled:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise RuntimeError("安装已取消")
        if time.time() - started > timeout:
            proc.kill()
            raise FetchError("Forge 安装器运行超时")
        try:
            while True:
                task.log(lines.get_nowait())
        except queue.Empty:
            pass
    try:
        while True:
            task.log(lines.get_nowait())
    except queue.Empty:
        pass
    return int(proc.returncode or 0)


def _find_generated_version(game_dir: Path, expected: str, started: float) -> tuple[str, dict[str, Any]]:
    versions_dir = game_dir / "versions"
    candidates: list[Path] = []
    expected_dir = versions_dir / expected
    if expected_dir.exists():
        candidates.append(expected_dir)
    for directory in sorted(versions_dir.iterdir()) if versions_dir.exists() else []:
        if directory.is_dir() and directory not in candidates and directory.stat().st_mtime >= started - 2:
            candidates.append(directory)
    for directory in candidates:
        json_path = directory / f"{directory.name}.json"
        if json_path.exists():
            from .util import read_json
            try:
                data = read_json(json_path)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("id"):
                return str(data.get("id") or directory.name), data
    raise FetchError("安装器未生成版本，请查看安装日志")


def install_loader(
    config: Config,
    paths: Paths,
    service: MinecraftService,
    task: Task,
    loader: str,
    game: str,
    loader_version: str,
    *,
    source: str = "official",
    auto_java: bool = True,
) -> None:
    loader = loader.lower()
    task.log(f"安装 {loader} {loader_version} · Minecraft {game}")
    task.set_phase("读取游戏版本")
    parent_json = service.get_version_json(game, source)
    required = required_java_major(parent_json)
    if loader in ("fabric", "quilt"):
        task.set_phase("获取加载器配置")
        profile = _fabric_profile(game, loader_version) if loader == "fabric" else _quilt_profile(game, loader_version)
        merged = merge_version_json(parent_json, profile, profile["id"])
        install_version(
            config, paths, service, task, profile["id"],
            source=source, auto_java=auto_java, game_version=game,
            version_json=merged, version_type="release",
            extra_meta={"loader": loader, "loader_version": loader_version},
        )
        return

    installer_url, expected = _installer_info(loader, game, loader_version)
    task.set_phase("准备 Java")
    if not java_runtime.has_suitable(config, paths, required):
        if not auto_java:
            raise FetchError(f"安装 {loader} 需要 Java {required}，请先在设置中安装或选择 Java")
        asset = java_runtime.resolve_jdk(required, detect_arch())
        java_path = java_runtime.install_jdk(task, config, required, asset)
        task.log(f"已准备 Java {required}：{java_path}")
    java = java_runtime.pick_java(config, paths, required)

    installer_dir = paths.cache_dir / "installers"
    installer_dir.mkdir(parents=True, exist_ok=True)
    parent_dir = config.ensure_game_dir() / "versions" / game
    parent_existed = parent_dir.exists()
    installer = installer_dir / installer_url.rsplit("/", 1)[-1]
    task.set_phase("下载安装器")
    task.log(f"安装器：{installer_url}")
    if not installer.exists() or installer.stat().st_size == 0:
        download_file(installer_url, installer, timeout=90, cancel=task.cancel_event, log=task.log)
    task.file_done(name=installer.name, skipped=False)

    task.set_phase(f"运行 {loader} 安装器")
    started = time.time()
    code = _run_installer(task, java["path"], installer, config.ensure_game_dir())
    if code != 0:
        raise FetchError(f"{loader} 安装器退出码 {code}，请查看日志")
    actual_id, generated = _find_generated_version(config.game_dir, expected, started)
    merged = merge_version_json(parent_json, generated, actual_id)
    task.log(f"安装器已生成版本：{actual_id}")
    install_version(
        config, paths, service, task, actual_id,
        source=source, auto_java=auto_java, game_version=game,
        version_json=merged, version_type="release",
        extra_meta={"loader": loader, "loader_version": loader_version},
    )
    if not parent_existed and parent_dir.exists() and (parent_dir / f"{game}.json").exists():
        shutil.rmtree(parent_dir, ignore_errors=True)
        task.log(f"已清理安装器临时生成的 {game} 版本目录")
