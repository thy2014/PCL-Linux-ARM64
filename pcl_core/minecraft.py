"""Mojang 版本元数据、规则判定与 ARM64 原生库解析。"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .config import Config, Paths
from .http_client import FetchError, get_json
from .util import atomic_write_json, read_json, valid_version_id

OFFICIAL_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
BMCLAPI_BASE = "https://bmclapi2.bangbang93.com"
BMCLAPI_MANIFEST = BMCLAPI_BASE + "/mc/game/version_manifest_v2.json"

MANIFEST_SOURCES = {
    "official": OFFICIAL_MANIFEST,
    "bmclapi": BMCLAPI_MANIFEST,
}
OFFICIAL_LIBRARY_BASE = "https://libraries.minecraft.net/"
OFFICIAL_RESOURCE_BASE = "https://resources.download.minecraft.net/"
MAVEN_CENTRAL = "https://repo1.maven.org/maven2/"

TYPE_LABELS = {
    "release": "正式版",
    "snapshot": "快照",
    "old_beta": "远古 Beta",
    "old_alpha": "远古 Alpha",
    "special": "特殊版本",
}


def manifest_url(source: str) -> str:
    if source == "bmclapi":
        return BMCLAPI_MANIFEST
    return OFFICIAL_MANIFEST


def asset_base(source: str) -> str:
    if source == "bmclapi":
        return "https://bmclapi2.bangbang93.com/assets/"
    return OFFICIAL_RESOURCE_BASE


def _rule_matches(rule: dict[str, Any], os_name: str, arch: str, features: dict[str, bool]) -> bool:
    rule_os = rule.get("os")
    if rule_os:
        if rule_os.get("name") and rule_os["name"] != os_name:
            return False
        if rule_os.get("arch"):
            expected = rule_os["arch"]
            actual = arch
            if expected == "x86" and actual == "x86_64":
                return False
            if expected != actual:
                return False
        if rule_os.get("version"):
            try:
                if not re.search(rule_os["version"], os.uname().release):
                    return False
            except (AttributeError, re.error):
                pass
    rule_features = rule.get("features")
    if rule_features:
        for key, expected in rule_features.items():
            if bool(features.get(key, False)) != bool(expected):
                return False
    return True


def rules_allow(
    rules: list[dict[str, Any]] | None,
    os_name: str,
    arch: str,
    features: dict[str, bool] | None = None,
) -> bool:
    """按照 Mojang 规则顺序求值，未出现规则时默认允许。"""
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        if _rule_matches(rule, os_name, arch, features):
            allowed = rule.get("action") == "allow"
    return allowed


def parse_library_name(name: str) -> tuple[str, str, str, str | None]:
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"无法解析库名：{name}")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    return group, artifact, version, classifier


def maven_path(group: str, artifact: str, version: str, classifier: str | None = None) -> str:
    path = f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}"
    if classifier:
        path += f"-{classifier}"
    return path + ".jar"


def maven_url(group: str, artifact: str, version: str, classifier: str | None = None) -> str:
    return MAVEN_CENTRAL + maven_path(group, artifact, version, classifier)


def _version_tuple(version: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", version)
    return tuple(int(num) for num in numbers[:3]) if numbers else (0,)


def _library_base(library: dict[str, Any]) -> str:
    """返回库所属 Maven 仓库基址；Fabric/Forge 的自定义仓库不可丢。"""
    base = str(library.get("url") or OFFICIAL_LIBRARY_BASE)
    return base if base.endswith("/") else base + "/"


def _entry(
    name: str,
    group: str,
    artifact: str,
    version: str,
    classifier: str | None,
    path: str,
    url: str,
    sha1: str | None,
    size: int | None,
    *,
    patched: bool = False,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "group": group,
        "artifact": artifact,
        "version": version,
        "classifier": classifier,
        "path": path,
        "url": url,
        "sha1": sha1,
        "size": size,
        "patched": patched,
        "fallback": fallback,
    }


def resolve_libraries(
    version_json: dict[str, Any],
    os_name: str,
    arch: str,
    features: dict[str, bool] | None = None,
    *,
    arm64_patch: bool = True,
) -> dict[str, Any]:
    """解析 classpath 与 natives，含 Linux ARM64 的 LWJGL 原生库替换。"""
    features = features or {}
    classpath: list[dict[str, Any]] = []
    natives: list[dict[str, Any]] = []
    seen_classpath: set[str] = set()
    patched_count = 0
    lwjgl2 = False
    lwjgl_unsupported = False

    for library in version_json.get("libraries", []):
        if not isinstance(library, dict):
            continue
        if not rules_allow(library.get("rules"), os_name, arch, features):
            continue
        name = library.get("name")
        if not name:
            continue
        try:
            group, artifact, version, name_classifier = parse_library_name(name)
        except ValueError:
            continue
        downloads = library.get("downloads") or {}

        is_native_artifact = bool(name_classifier and name_classifier.startswith("natives-"))
        artifact_info = downloads.get("artifact") or {}
        artifact_path = artifact_info.get("path")
        if artifact_path and not is_native_artifact:
            if artifact_path not in seen_classpath:
                seen_classpath.add(artifact_path)
                classpath.append(
                    _entry(
                        name,
                        group,
                        artifact,
                        version,
                        None,
                        artifact_path,
                        artifact_info.get("url") or (_library_base(library) + artifact_path),
                        artifact_info.get("sha1"),
                        artifact_info.get("size"),
                    )
                )
        elif not is_native_artifact and not downloads:
            # 少数库只给出 Maven 坐标，没有 downloads 字段
            rel_path = maven_path(group, artifact, version)
            if rel_path not in seen_classpath:
                seen_classpath.add(rel_path)
                classpath.append(
                    _entry(
                        name,
                        group,
                        artifact,
                        version,
                        None,
                        rel_path,
                        _library_base(library) + rel_path,
                        None,
                        None,
                    )
                )

        classifier = library.get("natives", {}).get(os_name) if isinstance(library.get("natives"), dict) else None
        if not classifier and is_native_artifact:
            classifier = name_classifier
        if not classifier:
            continue

        classifiers = downloads.get("classifiers") or {}
        official = classifiers.get(classifier) or {}
        official_path = official.get("path") or maven_path(group, artifact, version, classifier)
        official_url = official.get("url") or (_library_base(library) + official_path)
        official_sha1 = official.get("sha1")
        official_size = official.get("size")

        patched = False
        fallback = None
        if arm64_patch and os_name == "linux" and arch == "arm64" and group == "org.lwjgl":
            if _version_tuple(version) < (3, 3, 0):
                lwjgl2 = True
                lwjgl_unsupported = True
            elif "natives-linux" in classifier and "arm64" not in classifier:
                new_classifier = classifier.replace("natives-linux", "natives-linux-arm64")
                rel_path = maven_path(group, artifact, version, new_classifier)
                patched = True
                patched_count += 1
                fallback = {
                    "path": official_path,
                    "url": official_url,
                    "sha1": official_sha1,
                    "size": official_size,
                }
                natives.append(
                    _entry(
                        name,
                        group,
                        artifact,
                        version,
                        new_classifier,
                        rel_path,
                        MAVEN_CENTRAL + rel_path,
                        None,
                        None,
                        patched=True,
                        fallback=fallback,
                    )
                )
                continue

        natives.append(
            _entry(
                name,
                group,
                artifact,
                version,
                classifier,
                official_path,
                official_url,
                official_sha1,
                official_size,
                patched=patched,
                fallback=fallback,
            )
        )

    if os_name == "linux" and arch == "arm64":
        for library in version_json.get("libraries", []):
            if not isinstance(library, dict):
                continue
            name = str(library.get("name") or "")
            if name.startswith("org.lwjgl.lwjgl:") and rules_allow(library.get("rules"), os_name, arch, features):
                lwjgl2 = True
                lwjgl_unsupported = True

    return {
        "classpath": classpath,
        "natives": natives,
        "patched": patched_count,
        "lwjgl2": lwjgl2,
        "lwjgl_unsupported": lwjgl_unsupported,
    }


LOADER_LABELS = {"fabric": "Fabric", "quilt": "Quilt", "forge": "Forge", "neoforge": "NeoForge", "optifine": "OptiFine", "liteloader": "LiteLoader"}


def detect_loader(version_json: dict[str, Any]) -> str:
    names: list[str] = []
    for library in version_json.get("libraries") or []:
        if isinstance(library, dict) and library.get("name"):
            names.append(str(library["name"]).lower())
    main_class = str(version_json.get("mainClass") or "").lower()
    if any("neoforge" in name for name in names):
        return "neoforge"
    if any("fabric-loader" in name for name in names) or "fabricmc" in main_class:
        return "fabric"
    if any("quilt-loader" in name for name in names) or "quiltmc" in main_class:
        return "quilt"
    if any("minecraftforge" in name for name in names) or "forge" in main_class:
        return "forge"
    if any("optifine" in name for name in names):
        return "optifine"
    if any("liteloader" in name for name in names):
        return "liteloader"
    return "vanilla"


def _library_identity(name: str) -> str:
    parts = name.split(":")
    if len(parts) >= 4:
        return ":".join(parts[:2] + [parts[3]])
    return ":".join(parts[:2]) if len(parts) >= 2 else name


def merge_version_json(parent: dict[str, Any], child: dict[str, Any], new_id: str) -> dict[str, Any]:
    """把继承版本（Fabric/Forge 等）与父版本合并成一份可直接安装的完整 JSON。"""
    merged = dict(child)
    merged["id"] = new_id
    merged["type"] = child.get("type") or parent.get("type") or "release"
    merged["downloads"] = dict(parent.get("downloads") or {})
    merged["assetIndex"] = parent.get("assetIndex")
    merged["assets"] = parent.get("assets") or "legacy"
    merged["javaVersion"] = child.get("javaVersion") or parent.get("javaVersion")
    merged["mainClass"] = child.get("mainClass") or parent.get("mainClass")
    merged["logging"] = parent.get("logging")
    merged["complianceLevel"] = parent.get("complianceLevel")
    merged["minimumLauncherVersion"] = parent.get("minimumLauncherVersion")
    if child.get("minecraftArguments"):
        merged["minecraftArguments"] = child["minecraftArguments"]
    elif parent.get("minecraftArguments"):
        merged["minecraftArguments"] = parent["minecraftArguments"]

    ordered = list(child.get("libraries") or []) + list(parent.get("libraries") or [])
    seen: set[str] = set()
    libraries: list[dict[str, Any]] = []
    for library in ordered:
        if not isinstance(library, dict) or not library.get("name"):
            continue
        identity = _library_identity(str(library["name"]))
        if identity in seen:
            continue
        seen.add(identity)
        libraries.append(library)
    merged["libraries"] = libraries

    parent_args = parent.get("arguments") or {}
    child_args = child.get("arguments") or {}
    merged["arguments"] = {
        "game": list(parent_args.get("game") or []) + list(child_args.get("game") or []),
        "jvm": list(parent_args.get("jvm") or []) + list(child_args.get("jvm") or []),
    }
    merged.pop("inheritsFrom", None)
    return merged


def get_client(version_json: dict[str, Any]) -> dict[str, Any]:
    downloads = version_json.get("downloads") or {}
    client = downloads.get("client") or {}
    if not client.get("url"):
        raise FetchError("该版本没有客户端下载信息")
    return client


def get_asset_index(version_json: dict[str, Any]) -> dict[str, Any]:
    index = version_json.get("assetIndex") or {}
    if not index.get("url"):
        raise FetchError("该版本没有资源索引信息")
    return index


def asset_objects(asset_index: dict[str, Any]) -> list[dict[str, Any]]:
    """按 hash 去重后的资源对象列表。"""
    objects = asset_index.get("objects") or {}
    unique: dict[str, int] = {}
    for _name, info in objects.items():
        if not isinstance(info, dict):
            continue
        digest = info.get("hash")
        if not digest:
            continue
        unique[digest] = int(info.get("size") or 0)
    return [{"hash": digest, "size": size} for digest, size in unique.items()]


def required_java_major(version_json: dict[str, Any]) -> int:
    java_version = version_json.get("javaVersion") or {}
    try:
        return int(java_version.get("majorVersion") or 8)
    except (TypeError, ValueError):
        return 8


def type_label(version_type: str | None) -> str:
    return TYPE_LABELS.get(version_type or "", version_type or "未知")


class MinecraftService:
    def __init__(self, config: Config, paths: Paths) -> None:
        self.config = config
        self.paths = paths
        self.version_cache_dir = paths.cache_dir / "versions"
        self.version_cache_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ---- 版本列表 ----
    def fetch_manifest(self, source: str = "official", refresh: bool = False) -> dict[str, Any]:
        cache_file = self.paths.cache_dir / f"manifest-{source}.json"
        now = time.time()
        if not refresh and source in self._manifest_cache:
            cached_at, data = self._manifest_cache[source]
            if now - cached_at < 600:
                return {"data": data, "source": source, "cached": True}
        if not refresh and cache_file.exists():
            try:
                payload = read_json(cache_file)
                if now - float(payload.get("fetched_at", 0)) < 600 and payload.get("data"):
                    self._manifest_cache[source] = (float(payload["fetched_at"]), payload["data"])
                    return {"data": payload["data"], "source": source, "cached": True}
            except (OSError, ValueError, TypeError):
                pass

        errors: list[str] = []
        urls = [manifest_url(source)]
        if source != "official":
            urls.append(OFFICIAL_MANIFEST)
        for url in urls:
            try:
                data = get_json(url, timeout=25, retries=2)
                if not isinstance(data, dict) or "versions" not in data:
                    raise FetchError("版本清单格式不正确", url)
                self._manifest_cache[source] = (now, data)
                atomic_write_json(
                    cache_file,
                    {
                        "fetched_at": now,
                        "source": "bmclapi" if url.startswith("https://bmclapi") else "official",
                        "data": data,
                    },
                )
                return {
                    "data": data,
                    "source": "bmclapi" if url.startswith("https://bmclapi") else "official",
                    "cached": False,
                }
            except FetchError as error:
                errors.append(str(error))
        raise FetchError("；".join(errors) or "无法获取版本列表")

    def cached_manifest(self, source: str = "official") -> dict[str, Any] | None:
        """只读本地缓存（允许过期），用于启动页快速展示，不阻塞网络。"""
        if source in self._manifest_cache:
            return self._manifest_cache[source][1]
        cache_file = self.paths.cache_dir / f"manifest-{source}.json"
        if not cache_file.exists():
            return None
        try:
            payload = read_json(cache_file)
            data = payload.get("data")
            if isinstance(data, dict) and data.get("versions"):
                self._manifest_cache[source] = (float(payload.get("fetched_at", 0) or 0), data)
                return data
        except (OSError, ValueError, TypeError):
            return None
        return None

    def list_versions(self, source: str = "official", refresh: bool = False) -> dict[str, Any]:
        result = self.fetch_manifest(source, refresh=refresh)
        manifest = result["data"]
        versions = []
        for entry in manifest.get("versions", []):
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            versions.append(
                {
                    "id": entry["id"],
                    "type": entry.get("type", "release"),
                    "releaseTime": entry.get("releaseTime") or "",
                    "url": entry.get("url") or "",
                }
            )
        return {
            "latest": manifest.get("latest") or {},
            "versions": versions,
            "source": result["source"],
            "cached": result["cached"],
        }

    # ---- 版本 JSON ----
    def local_version_json(self, version_id: str) -> dict[str, Any] | None:
        path = self.config.game_dir / "versions" / version_id / f"{version_id}.json"
        if not path.exists():
            return None
        try:
            data = read_json(path)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def get_version_json(
        self,
        version_id: str,
        source: str = "official",
        *,
        prefer_local: bool = True,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if not valid_version_id(version_id):
            raise FetchError("版本名不合法")
        if prefer_local:
            local = self.local_version_json(version_id)
            if local and local.get("id"):
                return local
        cache_file = self.version_cache_dir / f"{version_id}.json"
        if cache_file.exists() and not refresh:
            try:
                cached = read_json(cache_file)
                if isinstance(cached, dict) and cached.get("id"):
                    return cached
            except (OSError, ValueError):
                pass

        manifest_result = self.fetch_manifest(source)
        entry = next(
            (item for item in manifest_result["data"].get("versions", []) if item.get("id") == version_id),
            None,
        )
        urls: list[str] = []
        if entry and entry.get("url"):
            urls.append(entry["url"])
        if source != "official":
            urls.append(f"{BMCLAPI_BASE}/version/{version_id}/json")
        if not urls or source != "official":
            try:
                official = self.fetch_manifest("official")
                official_entry = next(
                    (item for item in official["data"].get("versions", []) if item.get("id") == version_id),
                    None,
                )
                if official_entry and official_entry.get("url"):
                    urls.append(official_entry["url"])
            except FetchError:
                pass
        if not urls:
            raise FetchError(f"版本列表中找不到 {version_id}")

        errors: list[str] = []
        for url in urls:
            try:
                data = get_json(url, timeout=25, retries=2)
                if not isinstance(data, dict) or not data.get("id"):
                    raise FetchError("版本 JSON 格式不正确", url)
                atomic_write_json(cache_file, data)
                return data
            except FetchError as error:
                errors.append(f"{url}：{error}")
        raise FetchError(f"获取版本 JSON 失败：{'；'.join(errors)}")

    def version_meta(self, version_id: str) -> dict[str, Any]:
        path = self.config.game_dir / "versions" / version_id / "pcl_meta.json"
        if not path.exists():
            return {}
        try:
            data = read_json(path)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # ---- 已安装版本 ----
    def installed_versions(self) -> list[dict[str, Any]]:
        versions_dir = self.config.game_dir / "versions"
        if not versions_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for directory in sorted(versions_dir.iterdir()):
            if not directory.is_dir() or not valid_version_id(directory.name):
                continue
            json_path = directory / f"{directory.name}.json"
            if not json_path.exists():
                continue
            try:
                version_json = read_json(json_path)
            except (OSError, ValueError):
                continue
            meta = {}
            meta_path = directory / "pcl_meta.json"
            if meta_path.exists():
                try:
                    meta = read_json(meta_path)
                except (OSError, ValueError):
                    meta = {}
            try:
                size = sum(
                    os.path.getsize(os.path.join(root, name))
                    for root, _dirs, files in os.walk(directory)
                    for name in files
                )
            except OSError:
                size = 0
            result.append(
                {
                    "id": directory.name,
                    "type": version_json.get("type") or meta.get("type") or "release",
                    "java_major": required_java_major(version_json),
                    "size": size,
                    "installed_at": meta.get("installed_at") or "",
                    "last_played": meta.get("last_played") or "",
                    "arm64": meta.get("arm64") or {},
                    "client_jar": (directory / f"{directory.name}.jar").exists(),
                    "game_version": meta.get("game_version") or version_json.get("inheritsFrom") or directory.name,
                    "isolated": bool(meta["isolated"]) if isinstance(meta.get("isolated"), bool) else bool(self.config.get("version_isolation", True)),
                    "game_dir": str(self.config.version_game_dir(directory.name, meta)),
                    "loader": meta.get("loader") or detect_loader(version_json),
                    "pack": meta.get("pack") or None,
                }
            )
        result.sort(key=lambda item: item.get("last_played") or item.get("installed_at") or "", reverse=True)
        return result
