"""崩溃报告与 latest.log 的启发式诊断。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import Config, detect_arch
from .http_client import FetchError
from .minecraft import MinecraftService


PATTERNS: list[dict[str, Any]] = [
    {
        "re": r"OutOfMemoryError|Java heap space|GC overhead limit exceeded",
        "level": "error",
        "title": "内存不足",
        "suggestion": "调高最大内存（建议 4–8 GB），关闭其他占用内存的程序；32 位 Java 无法使用超过 1 GB 内存。",
    },
    {
        "re": r"UnsupportedClassVersionError|requires Java|java.lang.ClassFormatError",
        "level": "error",
        "title": "Java 版本不匹配",
        "suggestion": "在“设置 → Java”中选择该版本要求的 Java（1.17+ 通常需要 Java 17/21，1.16 及以下通常需要 Java 8）。",
    },
    {
        "re": r"GLFW error|Failed to create window|Pixel format not accelerated|No GL context|OpenGL",
        "level": "error",
        "title": "图形环境初始化失败",
        "suggestion": "确认系统有可用的 OpenGL 驱动；SSH/无桌面环境无法启动游戏。ARM64 设备请检查 LWJGL arm64 原生库是否完整。",
    },
    {
        "re": r"Mixin apply failed|Incompatible mod set|mod incompatibility|requires .* which is missing|Missing or unsupported mandatory dependencies",
        "level": "error",
        "title": "模组冲突或缺少前置",
        "suggestion": "检查模组版本与游戏/加载器是否匹配，安装缺失前置；可先禁用最近添加的模组再启动。",
    },
    {
        "re": r"Duplicate mods|duplicate mod|Found duplicate",
        "level": "error",
        "title": "重复模组",
        "suggestion": "mods 文件夹中存在同一模组的多个版本，保留一个后重试。",
    },
    {
        "re": r"NoSuchMethodError|NoClassDefFoundError|ClassNotFoundException",
        "level": "error",
        "title": "类或依赖缺失",
        "suggestion": "可能是模组与加载器版本不兼容，或依赖库下载不完整；重新安装该版本并核对模组版本。",
    },
    {
        "re": r"java.lang.IllegalAccessError|java.lang.VerifyError",
        "level": "error",
        "title": "模组字节码不兼容",
        "suggestion": "该模组很可能不支持当前 Minecraft/加载器版本，更换对应版本。",
    },
    {
        "re": r"java.io.IOException: .*denied|AccessDeniedException|Permission denied",
        "level": "error",
        "title": "文件权限不足",
        "suggestion": "检查游戏目录与 Java 目录的读写权限，避免使用 root 运行启动器。",
    },
    {
        "re": r"Failed to download|Unable to download|Connection timed out|UnknownHostException",
        "level": "warn",
        "title": "网络下载失败",
        "suggestion": "切换下载源、检查网络/代理后重试；安装时不要关闭启动器。",
    },
    {
        "re": r"LWJGL 2|legacy LWJGL|org.lwjgl.LWJGLException",
        "level": "warn",
        "title": "旧版 LWJGL 与 ARM64",
        "suggestion": "1.12 及更早版本使用 LWJGL 2，官方没有 ARM64 原生库，可能无法在此设备启动。",
    },
]


def _tail(path: Path, limit: int = 240) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def analyze(config: Config, service: MinecraftService, version_id: str) -> dict[str, Any]:
    meta = service.version_meta(version_id)
    if not service.local_version_json(version_id):
        raise FetchError("版本尚未安装")
    root = config.version_game_dir(version_id, meta)
    crash_dir = root / "crash-reports"
    reports = sorted(crash_dir.glob("crash-*.txt"), key=lambda p: p.stat().st_mtime, reverse=True) if crash_dir.exists() else []
    latest_log = root / "logs" / "latest.log"
    report_text = _tail(reports[0], 400) if reports else ""
    log_text = _tail(latest_log, 240)
    haystack = (report_text + "\n" + log_text).strip()
    issues = []
    for item in PATTERNS:
        match = re.search(item["re"], haystack, re.IGNORECASE)
        if match:
            evidence = ""
            for line in haystack.splitlines():
                if re.search(item["re"], line, re.IGNORECASE):
                    evidence = line.strip()[:260]
                    break
            issues.append(
                {
                    "title": item["title"],
                    "level": item["level"],
                    "evidence": evidence,
                    "suggestion": item["suggestion"],
                    "detail": item["suggestion"],
                }
            )
    if issues:
        summary = issues[0]["title"]
    elif reports:
        summary = "发现崩溃报告，但没有匹配到常见特征"
    elif latest_log:
        summary = "日志中没有发现明显错误"
    else:
        summary = "该版本还没有日志，先启动一次游戏再分析"
    excerpt = ""
    if report_text:
        lines = [line for line in report_text.splitlines() if line.strip()]
        excerpt = "\n".join(lines[:36])[:2400]
    elif log_text:
        lines = [line for line in log_text.splitlines() if line.strip()]
        excerpt = "\n".join(lines[-30:])[:2400]
    mods_dir = root / "mods"
    mod_count = len(list(mods_dir.glob("*.jar"))) if mods_dir.exists() else 0
    return {
        "version": version_id,
        "arch": detect_arch(),
        "game_dir": str(root),
        "latest_log": str(latest_log) if latest_log.exists() else "",
        "crash_report": str(reports[0]) if reports else "",
        "crash_reports": len(reports),
        "summary": summary,
        "issues": issues,
        "excerpt": excerpt,
        "log_excerpt": excerpt,
        "log_size": latest_log.stat().st_size if latest_log.exists() else 0,
        "mod_count": mod_count,
        "report": reports[0].name if reports else "",
        "has_log": latest_log.exists(),
    }
