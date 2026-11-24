"""Modrinth 资源搜索、模组/资源包/光影下载与整合包安装。"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .config import APP_NAME, APP_VERSION, Config, Paths
from .http_client import FetchError, download_file, get_json
from .minecraft import MinecraftService, detect_loader, required_java_major
from .tasks import Task
from .util import atomic_write_json, now_iso, read_json, sha1_file, directory_size, valid_version_id

API = "https://api.modrinth.com/v2"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (cross-platform launcher)"
PROJECT_TYPES = {"mod": "mod", "modpack": "modpack", "resourcepack": "resourcepack", "shader": "shader"}
CONTENT_DIRS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}


def _api(path: str, params: dict[str, Any] | None = None) -> Any:
    url = API + path
    if params:
        url += "?" + urlencode(params)
    return get_json(url, timeout=30, retries=2)


def search(project_type: str, query: str = "", game: str = "", loader: str = "", offset: int = 0, limit: int = 24) -> dict[str, Any]:
    project_type = PROJECT_TYPES.get(project_type, project_type)
    facets: list[list[str]] = [[f"project_type:{project_type}"]]
    if game:
        facets.append([f"versions:{game}"])
    if project_type == "mod" and loader in ("fabric", "forge", "neoforge", "quilt"):
        facets.append([f"categories:{loader}"])
    params = {
        "query": query or "",
        "limit": max(1, min(48, int(limit))),
        "offset": max(0, int(offset)),
        "facets": json.dumps(facets),
        "index": "relevance",
    }
    data = _api("/search", params)
    if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
        raise FetchError("Modrinth 搜索返回格式不正确")
    hits = []
    for hit in data.get("hits", []):
        if not isinstance(hit, dict):
            continue
        hits.append(
            {
                "id": hit.get("project_id") or hit.get("id"),
                "slug": hit.get("slug") or "",
                "title": hit.get("title") or "未命名",
                "description": hit.get("description") or "",
                "icon": hit.get("icon_url") or "",
                "downloads": int(hit.get("downloads") or 0),
                "follows": int(hit.get("follows") or 0),
                "author": hit.get("author") or "",
                "categories": hit.get("categories") or [],
                "versions": hit.get("versions") or [],
                "project_type": hit.get("project_type") or project_type,
            }
        )
    return {"hits": hits, "total": int(data.get("total_hits") or len(hits)), "offset": int(data.get("offset") or 0)}


def project_versions(slug: str, game: str = "", loader: str = "") -> list[dict[str, Any]]:
    data = _api(f"/project/{slug}/version")
    if not isinstance(data, list):
        raise FetchError("Modrinth 版本列表格式不正确")
    result = []
    for version in data:
        if not isinstance(version, dict):
            continue
        game_versions = version.get("game_versions") or []
        loaders = version.get("loaders") or []
        if game and game not in game_versions:
            continue
        if loader and loader not in ("", "vanilla") and loader not in loaders:
            continue
        files = version.get("files") or []
        result.append(
            {
                "id": version.get("id") or "",
                "name": version.get("name") or version.get("version_number") or "",
                "version_number": version.get("version_number") or "",
                "version_type": version.get("version_type") or "release",
                "game_versions": game_versions,
                "loaders": loaders,
                "date": version.get("date_published") or "",
                "downloads": int(version.get("downloads") or 0),
                "files": files,
                "dependencies": version.get("dependencies") or [],
            }
        )
    result.sort(key=lambda item: item.get("date") or "", reverse=True)
    return result


def _primary_file(version: dict[str, Any]) -> dict[str, Any]:
    files = version.get("files") or []
    for file in files:
        if isinstance(file, dict) and file.get("primary") and file.get("url"):
            return file
    for file in files:
        if isinstance(file, dict) and file.get("url"):
            return file
    raise FetchError("该版本没有可下载文件")


def _safe_name(name: str) -> str:
    name = Path(str(name)).name
    name = re.sub(r"[^\w.\-+()\[\] ]+", "_", name, flags=re.UNICODE)
    return name.strip(" .") or "download.bin"


def content_root(config: Config, service: MinecraftService, version_id: str) -> Path:
    meta = service.version_meta(version_id)
    root = config.version_game_dir(version_id, meta)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _collect_mod_jobs(project: str, game: str, loader: str, version_id: str | None, visited: set[str], jobs: list[dict[str, Any]]) -> None:
    if project in visited:
        return
    visited.add(project)
    versions = project_versions(project, game, loader)
    match: dict[str, Any] | None = None
    if version_id:
        match = next((v for v in versions if v.get("id") == version_id), None)
        if match is None:
            # 指定版本可能不兼容当前过滤条件，直接查版本详情
            data = _api(f"/version/{version_id}")
            if not isinstance(data, dict):
                raise FetchError("依赖版本不存在")
            match = {
                "id": data.get("id"),
                "name": data.get("name"),
                "files": data.get("files") or [],
                "dependencies": data.get("dependencies") or [],
                "loaders": data.get("loaders") or [],
                "game_versions": data.get("game_versions") or [],
            }
    if not versions and match is None:
        raise FetchError(f"没有找到兼容 {game} / {loader} 的版本")
    selected = match or versions[0]
    file = _primary_file(selected)
    jobs.append(
        {
            "url": file["url"],
            "filename": _safe_name(file.get("filename") or f"{project}.jar"),
            "sha1": (file.get("hashes") or {}).get("sha1"),
            "size": int(file.get("size") or 0),
            "project": project,
            "version": selected.get("name") or "",
        }
    )
    for dependency in selected.get("dependencies") or []:
        if not isinstance(dependency, dict) or dependency.get("dependency_type") != "required":
            continue
        dep_project = dependency.get("project_id")
        if not dep_project:
            continue
        _collect_mod_jobs(str(dep_project), game, loader, dependency.get("version_id"), visited, jobs)


def install_project(
    config: Config,
    paths: Paths,
    service: MinecraftService,
    task: Task,
    version_id: str,
    project_type: str,
    slug: str,
    *,
    project_version_id: str | None = None,
    game: str = "",
    loader: str = "",
) -> list[str]:
    if project_type not in CONTENT_DIRS:
        raise FetchError("当前只支持模组、资源包与光影下载；整合包请使用整合包安装")
    if not service.local_version_json(version_id):
        raise FetchError("目标版本尚未安装")
    meta = service.version_meta(version_id)
    root = content_root(config, service, version_id)
    target_dir = root / CONTENT_DIRS[project_type]
    target_dir.mkdir(parents=True, exist_ok=True)
    version_json = service.local_version_json(version_id) or {}
    actual_loader = detect_loader(version_json)
    if project_type == "mod":
        if actual_loader in ("vanilla", "optifine", "liteloader"):
            raise FetchError("这是原版版本，请先安装 Fabric / Forge / NeoForge / Quilt 加载器后再安装模组")
        loader = actual_loader
    else:
        loader = ""
    task.set_phase("获取项目版本")
    jobs: list[dict[str, Any]] = []
    visited: set[str] = set()
    _collect_mod_jobs(slug, game or str(meta.get("game_version") or version_id), loader, project_version_id, visited, jobs)
    task.add_totals(files=len(jobs), bytes_count=sum(j["size"] for j in jobs))
    task.log(f"准备安装 {len(jobs)} 个文件（含必需前置）")
    installed: list[str] = []
    for job in jobs:
        dest = target_dir / job["filename"]
        task.set_current(job["filename"])
        if dest.exists() and job.get("sha1") and sha1_file(dest).lower() == str(job["sha1"]).lower():
            task.log(f"已存在，跳过：{job['filename']}")
            task.file_done(skipped=True, name=job["filename"], bytes_count=job["size"])
        else:
            task.set_phase("下载资源")
            download_file(
                job["url"], dest, sha1=job.get("sha1") or None, size=job.get("size") or None,
                progress=lambda count: task.add_bytes(count), cancel=task.cancel_event, log=task.log,
            )
            task.file_done(name=job["filename"])
            installed.append(job["filename"])
            task.log(f"已安装：{job['filename']}")
    task.set_phase("安装完成")
    task.finish(f"已安装 {len(jobs)} 个文件")
    return installed


def _extract_overrides(archive: Path, target: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            prefix = None
            for candidate in ("overrides/", "client-overrides/"):
                if name.startswith(candidate):
                    prefix = candidate
                    break
            if prefix is None:
                continue
            relative = name[len(prefix):]
            dest = (target / relative).resolve()
            if target.resolve() not in dest.parents and dest != target.resolve():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


def install_modpack(
    config: Config,
    paths: Paths,
    service: MinecraftService,
    task: Task,
    source_version: str,
    slug: str,
    *,
    project_version_id: str | None = None,
) -> str:
    if not valid_version_id(source_version):
        raise FetchError("基础版本名不合法")
    source_json = service.local_version_json(source_version)
    if not source_json:
        raise FetchError("请选择一个已安装的版本作为整合包基础")
    project = _api(f"/project/{slug}")
    if not isinstance(project, dict):
        raise FetchError("整合包项目不存在")
    source_meta = service.version_meta(source_version)
    source_game = str(source_meta.get("game_version") or source_json.get("inheritsFrom") or source_version)
    versions = project_versions(slug, game=source_game)
    if project_version_id:
        versions = [v for v in versions if v.get("id") == project_version_id]
    if not versions:
        raise FetchError("该整合包没有可用版本")
    selected = versions[0]
    file = _primary_file(selected)
    if not str(file.get("filename") or "").endswith(".mrpack"):
        raise FetchError("该文件不是 Modrinth 整合包（.mrpack）")
    task.set_phase("下载整合包")
    cache = paths.cache_dir / "modpacks"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / _safe_name(file.get("filename") or f"{slug}.mrpack")
    task.add_totals(files=1, bytes_count=int(file.get("size") or 0))
    download_file(
        file["url"], archive, sha1=(file.get("hashes") or {}).get("sha1"),
        size=file.get("size") or None, progress=lambda count: task.add_bytes(count),
        cancel=task.cancel_event, log=task.log,
    )
    task.file_done(name=archive.name)

    with zipfile.ZipFile(archive) as zf:
        try:
            index = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
        except (KeyError, ValueError) as error:
            raise FetchError("整合包缺少 modrinth.index.json") from error
    if not isinstance(index, dict):
        raise FetchError("整合包索引格式不正确")
    dependencies = index.get("dependencies") or {}
    pack_game = str(dependencies.get("minecraft") or "")
    if pack_game and source_game != pack_game:
        raise FetchError(f"整合包需要 Minecraft {pack_game}，当前基础版本是 {source_game}")
    source_loader = detect_loader(source_json)
    required_loader = None
    if dependencies.get("fabric-loader"):
        required_loader = "fabric"
    elif dependencies.get("quilt-loader"):
        required_loader = "quilt"
    elif dependencies.get("neoforge"):
        required_loader = "neoforge"
    elif dependencies.get("forge"):
        required_loader = "forge"
    if required_loader and source_loader not in (required_loader, "quilt" if required_loader == "fabric" else required_loader):
        raise FetchError(f"整合包需要 {required_loader} 加载器，当前基础版本是 {source_loader}")

    pack_name = str(index.get("name") or project.get("title") or slug)
    clean_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")[:32] or "modpack"
    new_id = f"{clean_slug}-{str(selected.get('id') or '')[:6]}"
    if not valid_version_id(new_id):
        new_id = "modpack-" + re.sub(r"[^A-Za-z0-9._-]+", "-", str(selected.get("id") or "pack"))[:12]
    root = config.ensure_game_dir()
    versions_dir = root / "versions"
    target_dir = versions_dir / new_id
    if target_dir.exists():
        existing_meta = service.version_meta(new_id)
        if (existing_meta.get("pack") or {}).get("slug") != slug:
            suffix = 2
            while (versions_dir / f"{new_id}-{suffix}").exists():
                suffix += 1
            new_id = f"{new_id}-{suffix}"
            target_dir = versions_dir / new_id
        else:
            shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    new_json = dict(source_json)
    new_json["id"] = new_id
    atomic_write_json(target_dir / f"{new_id}.json", new_json)
    source_dir = versions_dir / source_version
    source_jar = source_dir / f"{source_version}.jar"
    if source_jar.exists():
        shutil.copy2(source_jar, target_dir / f"{new_id}.jar")
    source_natives = source_dir / "natives"
    if source_natives.exists():
        shutil.copytree(source_natives, target_dir / "natives", dirs_exist_ok=True)
    game_dir = target_dir
    game_dir.mkdir(parents=True, exist_ok=True)

    files = [item for item in (index.get("files") or []) if isinstance(item, dict)]
    downloads = []
    for item in files:
        env = item.get("env") or {}
        if isinstance(env, dict) and env.get("client") == "unsupported":
            continue
        path = str(item.get("path") or "")
        target = (game_dir / path).resolve()
        if game_dir.resolve() not in target.parents and target != game_dir.resolve():
            continue
        urls = item.get("downloads") or []
        if not urls:
            continue
        hashes = item.get("hashes") or {}
        downloads.append(
            {
                "url": urls[0],
                "dest": target,
                "sha1": hashes.get("sha1"),
                "size": int(item.get("fileSize") or 0),
                "path": path,
            }
        )
    task.add_totals(files=len(downloads) + 1, bytes_count=sum(j["size"] for j in downloads))
    task.set_phase("下载整合包内容")
    for job in downloads:
        dest: Path = job["dest"]
        if dest.exists() and job.get("sha1") and sha1_file(dest).lower() == str(job["sha1"]).lower():
            task.file_done(skipped=True, name=job["path"], bytes_count=job["size"])
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        task.set_current(job["path"])
        download_file(
            job["url"], dest, sha1=job.get("sha1") or None, size=job.get("size") or None,
            progress=lambda count: task.add_bytes(count), cancel=task.cancel_event, log=task.log,
        )
        task.file_done(name=job["path"])
    task.set_phase("写入覆盖文件")
    count = _extract_overrides(archive, game_dir)
    task.file_done(name="整合包覆盖文件")
    task.log(f"已覆盖 {count} 个整合包配置文件")
    meta = {
        "id": new_id,
        "type": "release",
        "source": "modrinth",
        "installed_at": now_iso(),
        "java_major": required_java_major(new_json),
        "game_version": pack_game or source_game,
        "isolated": True,
        "loader": source_meta.get("loader") or source_loader,
        "loader_version": source_meta.get("loader_version") or "",
        "pack": {
            "name": pack_name,
            "slug": slug,
            "version": selected.get("name") or "",
            "project_id": project.get("id") or "",
            "file": archive.name,
        },
        "files": len(downloads),
        "bytes": sum(j["size"] for j in downloads),
        "size": directory_size(target_dir),
    }
    atomic_write_json(target_dir / "pcl_meta.json", meta)
    task.set_phase("安装完成")
    task.finish(f"整合包 {pack_name} 安装完成")
    return new_id
