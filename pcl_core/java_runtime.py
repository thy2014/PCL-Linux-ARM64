"""Java 运行时检测与 Adoptium ARM64 JDK 自动下载。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Config, Paths, arch_label, detect_arch
from .http_client import FetchError, download_file, get_json
from .tasks import Task
from .util import safe_extract_tar

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"


def _parse_java_version(text: str) -> tuple[int, str] | None:
    match = re.search(r'version "([^"]+)"', text)
    if not match:
        return None
    version = match.group(1)
    if version.startswith("1."):
        parts = version.split(".")
        if len(parts) < 2:
            return None
        major = int(parts[1])
    else:
        try:
            major = int(version.split(".")[0])
        except ValueError:
            return None
    return major, version


def _vendor_of(text: str) -> str:
    for vendor in ("Temurin", "Zulu", "Corretto", "Microsoft", "Liberica", "GraalVM", "OpenJDK"):
        if vendor in text:
            return vendor
    return "Java"


def _candidate_paths(config: Config, paths: Paths) -> list[Path]:
    candidates: list[Path] = []
    configured = str(config.get("java_path") or "").strip()
    if configured:
        candidates.append(Path(os.path.expanduser(configured)))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / "java")
    which = shutil.which("java")
    if which:
        candidates.append(Path(which))
    if paths.java_dir.exists():
        for directory in sorted(paths.java_dir.glob("**/bin/java")):
            candidates.append(directory)
    for root in ("/usr/lib/jvm", "/opt/java", "/usr/java"):
        root_path = Path(root)
        if root_path.exists():
            for java_home_dir in sorted(root_path.glob("*")):
                candidate = java_home_dir / "bin" / "java"
                if candidate.exists():
                    candidates.append(candidate)
                candidate = java_home_dir / "jre" / "bin" / "java"
                if candidate.exists():
                    candidates.append(candidate)
    return candidates


def _parse_release_version(text: str) -> tuple[int, str] | None:
    """从 JDK 的 release 文件读取版本，避免跨架构执行二进制。"""
    match = re.search(r'(?m)^JAVA_VERSION="([^"]+)"', text)
    if not match:
        return None
    version = match.group(1)
    if version.startswith("1."):
        parts = version.split(".")
        if len(parts) < 2:
            return None
        try:
            return int(parts[1]), version
        except ValueError:
            return None
    try:
        return int(version.split(".")[0]), version
    except ValueError:
        return None


def _bundled_java_record(resolved: str, paths: Paths) -> dict[str, Any] | None:
    """识别 PCL 下载的 JDK：优先读 release，不要求宿主能执行该架构的 java。"""
    binary = Path(resolved)
    home = binary.parent.parent
    try:
        if paths.java_dir.resolve() not in home.resolve().parents:
            return None
    except OSError:
        return None
    release_file = home / "release"
    if not release_file.is_file():
        return None
    try:
        text = release_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parsed = _parse_release_version(text)
    if not parsed:
        return None
    major, version = parsed
    vendor = "Temurin" if "Temurin" in text or "Eclipse" in text else _vendor_of(text)
    return {
        "path": resolved,
        "home": str(home),
        "version": version,
        "major": major,
        "vendor": vendor,
        "arch": arch_label(detect_arch()),
        "source": "PCL 下载",
        "bundled": True,
    }


def detect_java(config: Config, paths: Paths) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in _candidate_paths(config, paths):
        try:
            resolved = str(candidate.resolve())
        except OSError:
            continue
        if resolved in seen or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            continue
        seen.add(resolved)
        bundled = _bundled_java_record(resolved, paths)
        if bundled:
            result.append(bundled)
            continue
        try:
            completed = subprocess.run(
                [resolved, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=12,
                check=False,
            )
            output = completed.stdout or ""
        except (OSError, subprocess.TimeoutExpired):
            continue
        parsed = _parse_java_version(output)
        if not parsed:
            continue
        major, version = parsed
        try:
            data_dir = paths.java_dir.resolve()
            is_bundled = data_dir in Path(resolved).parents
        except OSError:
            is_bundled = False
        source = "PCL 下载" if is_bundled else ("手动指定" if str(config.get("java_path") or "") and resolved == str(Path(os.path.expanduser(str(config.get("java_path")))).resolve()) else "系统")
        result.append(
            {
                "path": resolved,
                "home": str(Path(resolved).parent.parent),
                "version": version,
                "major": major,
                "vendor": _vendor_of(output),
                "arch": arch_label(detect_arch()),
                "source": source,
            }
        )
    result.sort(key=lambda item: (item["major"], item["path"]), reverse=True)
    return result


def has_suitable(config: Config, paths: Paths, required_major: int) -> bool:
    return any(java["major"] >= required_major for java in detect_java(config, paths))


def pick_java(config: Config, paths: Paths, required_major: int, java_path: str | None = None) -> dict[str, Any]:
    java_list = detect_java(config, paths)
    configured = str(java_path or config.get("java_path") or "").strip()
    if configured:
        resolved = str(Path(os.path.expanduser(configured)).resolve())
        for java in java_list:
            if java["path"] == resolved:
                if java["major"] < required_major:
                    raise FetchError(
                        f"所选 Java {java['version']} 低于该版本要求的 Java {required_major}，请在设置中更换"
                    )
                return java
        raise FetchError("设置中的 Java 路径不可用，请重新检测")
    exact = [java for java in java_list if java["major"] == required_major]
    if exact:
        return exact[0]
    higher = [java for java in java_list if java["major"] >= required_major]
    if higher:
        return min(higher, key=lambda item: item["major"])
    found = "、".join(f"Java {item['major']}" for item in java_list) or "未检测到 Java"
    raise FetchError(f"未找到可用的 Java {required_major}（当前：{found}），请先在下载页安装")


def _api_arch(arch: str) -> str:
    return {"arm64": "aarch64", "x86_64": "x64", "arm32": "arm"}.get(arch, "aarch64")


def resolve_jdk(major: int, arch: str) -> dict[str, Any]:
    url = ADOPTIUM_API.format(major=int(major))
    params = f"?architecture={_api_arch(arch)}&image_type=jdk&os=linux&vendor=eclipse"
    try:
        payload = get_json(url + params, timeout=30, retries=2)
    except FetchError as error:
        raise FetchError(f"无法获取 Java {major} 下载信息：{error}") from error
    if not isinstance(payload, list) or not payload:
        raise FetchError(f"Adoptium 没有提供 Java {major} 的 Linux {arch} 安装包")
    binary = (payload[0] or {}).get("binary") or {}
    package = binary.get("package") or {}
    if not package.get("link"):
        raise FetchError(f"Java {major} 下载信息不完整")
    version = (payload[0].get("version") or {}).get("openjdk_version") or str(major)
    return {
        "link": package["link"],
        "name": package.get("name") or f"jdk-{major}.tar.gz",
        "size": int(package.get("size") or 0),
        "checksum": (package.get("checksum") or "").lower(),
        "version": version,
        "major": int(major),
    }


def _find_java_root(extract_dir: Path) -> Path | None:
    if (extract_dir / "bin" / "java").exists():
        return extract_dir
    for entry in sorted(extract_dir.iterdir()):
        if entry.is_dir():
            if (entry / "bin" / "java").exists():
                return entry
            for nested in sorted(entry.iterdir()):
                if nested.is_dir() and (nested / "bin" / "java").exists():
                    return nested
    return None


def install_jdk(
    task: Task,
    config: Config,
    major: int,
    asset: dict[str, Any],
    *,
    totals_registered: bool = False,
) -> str:
    if not totals_registered:
        task.add_totals(files=1, bytes_count=int(asset.get("size") or 0))
    task.set_phase(f"下载 Java {major}")
    task.set_current(asset["name"])
    archive = config.paths.java_dir / ".cache" / asset["name"]
    task.log(f"下载 Java {major}（{asset.get('version')}）：{asset['name']}")
    download_file(
        asset["link"],
        archive,
        sha256=asset.get("checksum") or None,
        size=asset.get("size") or None,
        progress=lambda count: task.add_bytes(count),
        cancel=task.cancel_event,
        timeout=90,
        log=task.log,
    )
    task.set_phase(f"解压 Java {major}")
    temp_dir = config.paths.java_dir / f".extract-{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        safe_extract_tar(archive, temp_dir)
        root = _find_java_root(temp_dir)
        if root is None:
            raise FetchError("Java 压缩包结构异常，未找到 bin/java")
        target = config.paths.java_dir / f"temurin-{major}-{_api_arch(detect_arch())}"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(root), str(target))
        java_path = target / "bin" / "java"
        try:
            os.chmod(java_path, 0o755)
        except OSError:
            pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            archive.unlink()
        except OSError:
            pass
    try:
        config.update({"java_path": str(java_path)})
    except OSError:
        pass
    task.file_done(name=asset["name"])
    task.set_current(f"Java {major} 已就绪")
    task.log(f"Java {major} 安装到 {java_path}")
    return str(java_path)
