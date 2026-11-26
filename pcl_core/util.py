"""通用小工具：路径安全、哈希、离线 UUID、解压。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Iterable

_VERSION_ID_FORBIDDEN = set('\\/:*?"<>|')


def valid_version_id(version_id: str) -> bool:
    """版本文件夹名：允许中文/空格，但绝不能成为跳出 versions 的路径。"""
    if not version_id or len(version_id) > 96 or version_id in (".", ".."):
        return False
    if not (version_id[0].isalnum() or version_id[0] == "_"):
        return False
    return not any(ch in _VERSION_ID_FORBIDDEN or ord(ch) < 32 for ch in version_id)


def human_bytes(size: float | int | None) -> str:
    if size is None:
        return "未知"
    size = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.2f} {units[index]}"


def sha1_file(path: Path, chunk_size: int = 1024 * 1024, cancel=None) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("cancelled")
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024, cancel=None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("cancelled")
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def offline_uuid(player_name: str) -> str:
    data = f"OfflinePlayer:{player_name}".encode("utf-8")
    return str(uuid.UUID(bytes=hashlib.md5(data).digest(), version=3))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, data) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_extract_zip(zip_path: Path, dest: Path, skip_prefixes: Iterable[str] = ("META-INF/",)) -> int:
    """安全解压 zip（拒绝绝对路径与 ..），返回解压文件数。"""
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name or name.startswith("/") or ".." in Path(name).parts:
                continue
            if any(name.startswith(prefix) for prefix in skip_prefixes):
                continue
            if info.is_dir():
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 256)
            count += 1
    return count


def safe_extract_tar(archive_path: Path, dest: Path) -> int:
    """安全解压 tar.gz（拒绝设备文件、绝对路径和 ..）。"""
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() and not member.isdir():
                continue
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts:
                continue
            target = dest / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(target, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 256)
            try:
                os.chmod(target, member.mode & 0o777)
            except OSError:
                pass
            count += 1
    return count


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def format_date(timestamp_ms: int | float | None) -> str:
    if not timestamp_ms:
        return "—"
    try:
        return time.strftime("%Y-%m-%d", time.localtime(float(timestamp_ms) / 1000.0))
    except (ValueError, OSError, OverflowError):
        return "—"


def format_local(seconds: float | None) -> str:
    if not seconds:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(seconds))
    except (ValueError, OSError, OverflowError):
        return ""
