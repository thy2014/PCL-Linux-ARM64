"""版本安装：客户端、依赖库、资源文件、平台原生库与 Java。"""
from __future__ import annotations

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import java_runtime
from .config import Config, Paths, detect_arch, detect_os
from .http_client import (
    DownloadCancelled,
    FetchError,
    download_file,
    get_json,
    maven_sha1,
)
from .minecraft import (
    MinecraftService,
    asset_base,
    asset_objects,
    get_asset_index,
    get_client,
    required_java_major,
    resolve_libraries,
)
from .tasks import Task, TaskCancelled
from .util import (
    atomic_write_json,
    directory_size,
    now_iso,
    read_json,
    safe_extract_zip,
    valid_version_id,
)


def _relative_under(base: Path, relative: str) -> Path:
    target = (base / relative).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise FetchError(f"非法文件路径：{relative}")
    return target


def _has_feature(config: Config) -> dict[str, bool]:
    width = int(config.get("width") or 0)
    height = int(config.get("height") or 0)
    return {"has_custom_resolution": width > 0 and height > 0, "is_demo_user": False}


def _existing_ok(path: Path, job: dict[str, Any]) -> bool:
    if not path.exists() or not path.is_file():
        return False
    size = job.get("size")
    if size is not None:
        return path.stat().st_size == int(size)
    digest = job.get("sha1")
    if digest:
        from .util import sha1_file

        return sha1_file(path).lower() == digest.lower()
    return path.stat().st_size > 0


def _job(
    url: str,
    dest: Path,
    label: str,
    *,
    sha1: str | None = None,
    size: int | None = None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "url": url,
        "dest": dest,
        "label": label,
        "sha1": sha1,
        "size": int(size) if size is not None else None,
        "fallback": fallback,
    }


def install_version(
    config: Config,
    paths: Paths,
    service: MinecraftService,
    task: Task,
    version_id: str,
    *,
    source: str = "official",
    auto_java: bool = True,
    java_major: int | None = None,
    version_json: dict[str, Any] | None = None,
    version_type: str | None = None,
    game_version: str | None = None,
    extra_meta: dict[str, Any] | None = None,
    finalize: bool = True,
) -> None:
    if not valid_version_id(version_id):
        raise FetchError("版本名不合法")
    arch = detect_arch()
    os_name = detect_os()
    settings = config.snapshot()
    game_dir = config.ensure_game_dir()

    task.set_phase("获取版本信息")
    task.log(f"开始安装 {version_id}（下载源：{'官方' if source == 'official' else 'BMCLAPI 镜像'}）")
    if version_json is None:
        manifest = service.fetch_manifest(source)
        entry = next(
            (item for item in manifest["data"].get("versions", []) if item.get("id") == version_id),
            None,
        )
        if entry is None:
            raise FetchError(f"版本列表中没有 {version_id}")
        version_type = entry.get("type") or "release"
        task.check_cancel()
        version_json = service.get_version_json(version_id, source)
    else:
        if not isinstance(version_json, dict):
            raise FetchError("版本信息格式不正确")
        version_type = version_type or version_json.get("type") or "release"
        version_json = dict(version_json)
        version_json["id"] = version_id
    game_version = game_version or version_id
    task.log(
        f"版本类型：{version_type} · 需要 Java {required_java_major(version_json)}"
    )
    version_dir = game_dir / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(version_dir / f"{version_id}.json", version_json)

    plan = resolve_libraries(
        version_json,
        os_name,
        arch,
        _has_feature(config),
        arm64_patch=bool(settings.get("arm64_patch", True)),
    )
    if arch == "arm64":
        if plan["patched"]:
            task.log(f"ARM64：已替换 {plan['patched']} 个 LWJGL Linux 原生库")
        if plan["lwjgl_unsupported"]:
            task.log("警告：该版本使用 LWJGL 2 或旧版 LWJGL，官方没有 ARM64 原生库，启动可能失败")
        elif not plan["patched"]:
            task.log("ARM64：该版本没有需要替换的 LWJGL 原生库")

    # 清理旧的 natives，避免不同版本残留
    natives_dir = version_dir / "natives"
    if natives_dir.exists():
        shutil.rmtree(natives_dir, ignore_errors=True)
    natives_dir.mkdir(parents=True, exist_ok=True)

    client = get_client(version_json)
    client_dest = version_dir / f"{version_id}.jar"
    library_base = game_dir / "libraries"
    assets_base = game_dir / "assets"
    asset_index_info = get_asset_index(version_json)
    asset_index_id = str(asset_index_info.get("id") or version_id)
    task.set_phase("获取资源索引")
    asset_index = get_json(asset_index_info["url"], timeout=30, retries=2)
    if not isinstance(asset_index, dict):
        raise FetchError("资源索引格式不正确")
    index_path = assets_base / "indexes" / f"{asset_index_id}.json"
    atomic_write_json(index_path, asset_index)
    objects = asset_objects(asset_index)

    # 可选 Java 自动下载
    jdk_asset = None
    selected_java = java_major
    required = required_java_major(version_json)
    if selected_java is None and auto_java:
        if not java_runtime.has_suitable(config, paths, required):
            selected_java = required
            task.log(f"本机缺少 Java {required}，将在安装完成后自动下载匹配平台的 JDK")
    if selected_java:
        task.set_phase(f"检查 Java {selected_java}")
        jdk_asset = java_runtime.resolve_jdk(int(selected_java), arch)

    # ---- 统计与任务清单 ----
    jobs: list[dict[str, Any]] = []
    client_job = _job(
        client["url"],
        client_dest,
        f"客户端 {version_id}.jar",
        sha1=client.get("sha1"),
        size=client.get("size"),
    )
    jobs.append(client_job)

    library_jobs = []
    for item in plan["classpath"]:
        dest = _relative_under(library_base, item["path"])
        library_jobs.append(
            _job(item["url"], dest, item["name"], sha1=item.get("sha1"), size=item.get("size"))
        )
    jobs.extend(library_jobs)

    native_jobs = []
    fallback_natives = 0
    for item in plan["natives"]:
        dest = _relative_under(library_base, item["path"])
        sha1 = item.get("sha1")
        if item.get("patched") and not sha1:
            sha1 = maven_sha1(item["url"])
        job = _job(
            item["url"],
            dest,
            f"原生库 {item['name']}",
            sha1=sha1,
            size=item.get("size"),
            fallback=item.get("fallback"),
        )
        native_jobs.append(job)
        jobs.append(job)

    asset_jobs = []
    for obj in objects:
        digest = obj["hash"]
        dest = assets_base / "objects" / digest[:2] / digest
        asset_jobs.append(
            _job(
                asset_base(source) + f"{digest[:2]}/{digest}",
                dest,
                f"资源 {digest[:8]}",
                sha1=digest,
                size=obj["size"],
            )
        )
    jobs.extend(asset_jobs)

    total_files = len(jobs) + 1 + (1 if jdk_asset else 0)
    total_bytes = (
        int(client.get("size") or 0)
        + sum(int(item.get("size") or 0) for item in plan["classpath"])
        + sum(int(item.get("size") or 0) for item in plan["natives"])
        + int(asset_index_info.get("size") or 0)
        + sum(int(obj["size"]) for obj in objects)
        + int((jdk_asset or {}).get("size") or 0)
    )
    task.add_totals(files=total_files, bytes_count=total_bytes)
    task.file_done(name=f"资源索引 {asset_index_id}.json", bytes_count=int(asset_index_info.get("size") or 0))
    task.log(
        f"共 {len(jobs)} 个文件，约 {total_bytes / 1024 / 1024:.1f} MB"
        + (f"，含 Java {selected_java}" if jdk_asset else "")
    )

    # ---- 并发下载 ----
    abort = threading.Event()
    errors: list[Exception] = []
    fallback_lock = threading.Lock()

    def run_job(job: dict[str, Any]) -> None:
        if task.cancelled or abort.is_set():
            raise TaskCancelled()
        dest: Path = job["dest"]
        task.file_started(job["label"])
        if _existing_ok(dest, job):
            task.file_done(
                skipped=True,
                name=job["label"],
                bytes_count=int(job.get("size") or 0),
            )
            return
        try:
            download_file(
                job["url"],
                dest,
                sha1=job.get("sha1"),
                size=job.get("size"),
                progress=lambda count: task.add_bytes(count),
                cancel=task.cancel_event,
                log=task.log,
            )
        except FetchError as error:
            fallback = job.get("fallback")
            if error.status == 404 and fallback:
                nonlocal fallback_natives
                with fallback_lock:
                    fallback_natives += 1
                task.log(f"ARM64 原生库缺失，回退官方 x86 版本：{job['label']}")
                download_file(
                    fallback["url"],
                    dest,
                    sha1=fallback.get("sha1"),
                    size=fallback.get("size"),
                    progress=lambda count: task.add_bytes(count),
                    cancel=task.cancel_event,
                    log=task.log,
                )
            else:
                task.log(f"下载失败：{job['label']} · {error} · {getattr(error, 'url', '')}")
                raise FetchError(f"{job['label']}：{error}", getattr(error, "url", ""), getattr(error, "status", None))
        task.file_done(name=job["label"])

    task.set_phase("下载文件")
    workers = max(1, min(32, int(settings.get("download_threads") or 16)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pcl-download") as pool:
        futures = {pool.submit(run_job, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except (TaskCancelled, DownloadCancelled):
                abort.set()
            except Exception as error:  # noqa: BLE001 - 聚合到任务失败
                errors.append(error)
                abort.set()
    if task.cancelled:
        raise TaskCancelled()
    if errors:
        raise FetchError(str(errors[0]))

    # ---- 解压 native ----
    task.set_phase("解压原生库")
    extracted = 0
    for job in native_jobs:
        jar_path: Path = job["dest"]
        if jar_path.exists():
            try:
                extracted += safe_extract_zip(jar_path, natives_dir)
            except (OSError, ValueError) as error:
                task.log(f"解压失败：{jar_path.name}：{error}")
    task.log(f"已解压 {extracted} 个原生库文件")

    # ---- 旧版资源目录 ----
    virtual_count = 0
    objects_map = asset_index.get("objects") or {}
    if asset_index.get("virtual") or asset_index.get("map_to_resources"):
        virtual_root = assets_base / "virtual" / asset_index_id
        resource_root = game_dir / "resources"
        for name, info in objects_map.items():
            if not isinstance(info, dict) or not info.get("hash"):
                continue
            digest = info["hash"]
            size = int(info.get("size") or 0)
            source_path = assets_base / "objects" / digest[:2] / digest
            if not source_path.exists():
                continue
            targets = []
            if asset_index.get("virtual"):
                targets.append(_relative_under(virtual_root, name))
            if asset_index.get("map_to_resources"):
                targets.append(_relative_under(resource_root, name))
            for target in targets:
                if not target.exists() or target.stat().st_size != size:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_path, target)
                    virtual_count += 1
        task.log(f"已整理 {virtual_count} 个旧版资源文件")

    # ---- Java ----
    downloaded_java = ""
    if jdk_asset:
        task.set_phase(f"安装 Java {selected_java}")
        downloaded_java = java_runtime.install_jdk(
            task, config, int(selected_java), jdk_asset, totals_registered=True
        )
        task.log(f"Java {selected_java} 已就绪：{downloaded_java}")

    # ---- 元数据 ----
    previous_meta = {}
    meta_file = version_dir / "pcl_meta.json"
    if meta_file.exists():
        try:
            previous_meta = read_json(meta_file)
        except (OSError, ValueError):
            previous_meta = {}
    isolated = previous_meta.get("isolated")
    if not isinstance(isolated, bool):
        isolated = bool(settings.get("version_isolation", True))
    meta = {
        "id": version_id,
        "type": version_type,
        "source": source,
        "installed_at": now_iso(),
        "java_major": required,
        "game_version": game_version,
        "isolated": isolated,
        "arm64": {
            "patched": plan["patched"],
            "fallback": fallback_natives,
            "unsupported": plan["lwjgl_unsupported"],
        },
        "files": len(jobs),
        "bytes": total_bytes,
        "size": directory_size(version_dir),
    }
    for key in ("last_played", "last_java", "overrides", "loader", "pack", "icon"):
        if previous_meta.get(key) is not None:
            meta[key] = previous_meta[key]
    if extra_meta:
        for key, value in extra_meta.items():
            if value is not None:
                meta[key] = value
    atomic_write_json(meta_file, meta)

    if finalize:
        task.set_phase("安装完成")
        task.set_current(f"{version_id} 已就绪")
        task.finish(f"{version_id} 安装完成")


def delete_version(config: Config, version_id: str) -> int:
    if not valid_version_id(version_id):
        raise FetchError("版本名不合法")
    version_dir = config.game_dir / "versions" / version_id
    if not version_dir.exists():
        raise FetchError("版本不存在")
    size = directory_size(version_dir)
    shutil.rmtree(version_dir)
    return size


def mark_played(config: Config, version_id: str, java_version: str = "") -> None:
    meta_file = config.game_dir / "versions" / version_id / "pcl_meta.json"
    if not meta_file.exists():
        return
    try:
        meta = read_json(meta_file)
    except (OSError, ValueError):
        return
    meta["last_played"] = now_iso()
    if java_version:
        meta["last_java"] = java_version
    atomic_write_json(meta_file, meta)
