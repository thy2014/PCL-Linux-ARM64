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
BMCLAPI = "https://bmclapi2.bangbang93.com"
FABRIC_MIRROR = f"{BMCLAPI}/fabric-meta/v2"
FORGE_MAVEN_MIRROR = f"{BMCLAPI}/maven/net/minecraftforge/forge"
FORGE_PROMOTIONS_MIRROR = f"{BMCLAPI}/forge/promotions_slim.json"
NEOFORGE_MAVEN_MIRROR = f"{BMCLAPI}/maven/net/neoforged/neoforge"
LOADER_CACHE_TTL = 600
_loader_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

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


def _fabric_profile(game: str, loader: str, source: str = "official") -> dict[str, Any]:
    bases = [FABRIC_META, FABRIC_MIRROR] if source != "bmclapi" else [FABRIC_MIRROR, FABRIC_META]
    last_error: Exception | None = None
    for base in bases:
        try:
            data = get_json(f"{base}/versions/loader/{game}/{loader}/profile/json", timeout=6, retries=1)
            if not isinstance(data, dict) or not data.get("id"):
                raise FetchError("Fabric 配置格式不正确")
            return data
        except FetchError as error:
            last_error = error
    raise FetchError(f"Fabric 配置获取失败：{last_error}")


def _quilt_profile(game: str, loader: str) -> dict[str, Any]:
    url = f"{QUILT_META}/versions/loader/{game}/{loader}/profile/json"
    data = get_json(url, timeout=6, retries=1)
    if not isinstance(data, dict) or not data.get("id"):
        raise FetchError("Quilt 配置格式不正确")
    return data


def _xml_versions(url: str, timeout: float = 5, retries: int = 1) -> list[str]:
    text = get_text(url, timeout=timeout, retries=retries)
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
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    rest = ".".join(parts[1:]) if parts[0] == "1" else game
    if rest.count(".") == 0:
        rest += ".0"
    return rest + "."


def _ordered(urls: list[str], source: str) -> list[str]:
    return list(reversed(urls)) if source == "bmclapi" else list(urls)


def _first_json(urls: list[str], timeout: float = 5) -> Any:
    last_error: Exception | None = None
    for url in urls:
        try:
            return get_json(url, timeout=timeout, retries=1)
        except FetchError as error:
            last_error = error
    raise FetchError(f"加载器元数据获取失败：{last_error}")


def _first_xml(urls: list[str], timeout: float = 5) -> list[str]:
    last_error: Exception | None = None
    for url in urls:
        try:
            return _xml_versions(url, timeout=timeout, retries=1)
        except FetchError as error:
            last_error = error
    raise FetchError(f"加载器版本列表获取失败：{last_error}")


def loader_versions(loader: str, game: str, source: str = "official") -> dict[str, Any]:
    loader = loader.lower()
    cache_key = (loader, game, source)
    cached = _loader_cache.get(cache_key)
    if cached and time.time() - cached[0] < LOADER_CACHE_TTL:
        return dict(cached[1])
    result = _loader_versions_uncached(loader, game, source)
    if result.get("versions"):
        _loader_cache[cache_key] = (time.time(), dict(result))
    return result


def _loader_versions_uncached(loader: str, game: str, source: str) -> dict[str, Any]:
    if loader == "fabric":
        data = _first_json([f"{FABRIC_MIRROR}/versions/loader/{game}", f"{FABRIC_META}/versions/loader/{game}"])
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
        return {
            "loader": loader,
            "game": game,
            "versions": items[:40],
            "recommended": next((i["version"] for i in items if i["stable"]), items[0]["version"] if items else ""),
        }
    if loader == "quilt":
        data = _first_json([f"{QUILT_META}/versions/loader/{game}"])
        if not isinstance(data, list):
            raise FetchError("Quilt 加载器列表格式不正确")
        items = []
        for item in data:
            version = item.get("loader", {}).get("version") if isinstance(item, dict) else None
            if version:
                items.append({"version": str(version), "stable": "beta" not in str(version), "recommended": False})
        return {
            "loader": loader,
            "game": game,
            "versions": items[:40],
            "recommended": items[0]["version"] if items else "",
        }
    if loader == "forge":
        recommended = None
        latest = None
        versions: list[str] = []
        try:
            data = _first_json([f"{BMCLAPI}/forge/minecraft/{game}"], timeout=5)
            if isinstance(data, list):
                versions = [str(item["version"]) for item in data if isinstance(item, dict) and item.get("version")]
        except FetchError:
            versions = []
        if not versions:
            try:
                all_versions = _first_xml([f"{FORGE_MAVEN}/maven-metadata.xml"])
                prefix = f"{game}-"
                versions = [v[len(prefix):] for v in all_versions if v.startswith(prefix)]
            except FetchError:
                versions = []
        seen: set[str] = set()
        items = []
        for version in versions:
            if version in seen:
                continue
            seen.add(version)
            items.append({"version": version, "stable": True, "recommended": version == recommended})
        items.sort(key=lambda x: [int(p) if p.isdigit() else p for p in re.split(r"([0-9]+)", x["version"])], reverse=True)
        return {
            "loader": loader,
            "game": game,
            "versions": items[:60],
            "recommended": recommended or latest or (items[0]["version"] if items else ""),
        }
    if loader == "neoforge":
        prefix = _neo_prefix(game)
        if not prefix:
            return {"loader": loader, "game": game, "versions": [], "recommended": "", "note": "NeoForge 仅支持 1.20.2 及更高版本"}
        try:
            all_versions = _first_xml([f"{NEOFORGE_MAVEN_MIRROR}/maven-metadata.xml", f"{NEOFORGE_MAVEN}/maven-metadata.xml"])
        except FetchError as error:
            return {"loader": loader, "game": game, "versions": [], "recommended": "", "note": f"无法获取 NeoForge 版本列表：{error}"}
        versions = [v for v in all_versions if v.startswith(prefix)]
        versions.sort(key=lambda v: [int(p) if p.isdigit() else p for p in re.split(r"([0-9]+)", v)], reverse=True)
        items = [{"version": v, "stable": "beta" not in v, "recommended": False} for v in versions[:60]]
        return {
            "loader": loader,
            "game": game,
            "versions": items,
            "recommended": items[0]["version"] if items else "",
        }
    raise FetchError("暂不支持该加载器")


def _installer_info(loader: str, game: str, loader_version: str, source: str = "official") -> tuple[list[str], str]:
    if loader == "forge":
        name = f"forge-{game}-{loader_version}-installer.jar"
        official = f"{FORGE_MAVEN}/{game}-{loader_version}/{name}"
        mirror = f"{FORGE_MAVEN_MIRROR}/{game}-{loader_version}/{name}"
        return _ordered([official, mirror], source), f"{game}-forge-{loader_version}"
    if loader == "neoforge":
        name = f"neoforge-{loader_version}-installer.jar"
        official = f"{NEOFORGE_MAVEN}/{loader_version}/{name}"
        mirror = f"{NEOFORGE_MAVEN_MIRROR}/{loader_version}/{name}"
        return _ordered([official, mirror], source), f"neoforge-{loader_version}"
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
        profile = _fabric_profile(game, loader_version, source) if loader == "fabric" else _quilt_profile(game, loader_version)
        merged = merge_version_json(parent_json, profile, profile["id"])
        install_version(
            config, paths, service, task, profile["id"],
            source=source, auto_java=auto_java, game_version=game,
            version_json=merged, version_type="release",
            extra_meta={"loader": loader, "loader_version": loader_version},
        )
        return

    installer_urls, expected = _installer_info(loader, game, loader_version, source)
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
    installer = installer_dir / installer_urls[0].rsplit("/", 1)[-1]
    task.set_phase("下载安装器")
    if not installer.exists() or installer.stat().st_size == 0:
        last_error: Exception | None = None
        for installer_url in installer_urls:
            task.log(f"安装器：{installer_url}")
            try:
                download_file(installer_url, installer, timeout=90, cancel=task.cancel_event, log=task.log)
                last_error = None
                break
            except FetchError as error:
                last_error = error
                task.log(f"安装器下载源失败，尝试下一个：{error}")
        if last_error is not None:
            raise FetchError(f"安装器下载失败：{last_error}")
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
