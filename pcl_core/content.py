"""版本内容管理：模组、资源包、光影与存档。"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import struct
import time
import zipfile
from pathlib import Path
from typing import Any

from .config import Config
from .http_client import FetchError
from .minecraft import MinecraftService
from .util import directory_size, now_iso, safe_extract_zip

KIND_DIRS = {"mods": "mods", "resourcepacks": "resourcepacks", "shaderpacks": "shaderpacks", "saves": "saves"}


def _root(config: Config, service: MinecraftService, version_id: str) -> Path:
    meta = service.version_meta(version_id)
    if not service.local_version_json(version_id):
        raise FetchError("版本尚未安装")
    root = config.version_game_dir(version_id, meta)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _text(value: Any, limit: int = 220) -> str:
    if isinstance(value, dict):
        value = value.get("text") or value.get("translate") or value.get("contents") or ""
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _authors(value: Any) -> str:
    if isinstance(value, str):
        return value[:80]
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                names.append(str(item.get("name") or item.get("id") or ""))
        return ", ".join(n for n in names if n)[:80]
    if isinstance(value, dict):
        return ", ".join(f"{k}" for k in value.keys())[:80]
    return ""


def _read_zip_text(path: Path, member: str) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            if member in zf.namelist():
                return zf.read(member).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    return None


def _parse_mod_meta(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {"name": path.name, "id": "", "version": "", "description": "", "authors": "", "loader": ""}
    raw = _read_zip_text(path, "fabric.mod.json")
    if raw:
        try:
            data = json.loads(raw)
            meta.update(
                name=str(data.get("name") or data.get("id") or path.name),
                id=str(data.get("id") or ""),
                version=str(data.get("version") or ""),
                description=_text(data.get("description")),
                authors=_authors(data.get("authors")),
                loader="fabric",
            )
        except ValueError:
            pass
        return meta
    raw = _read_zip_text(path, "quilt.mod.json")
    if raw:
        try:
            data = json.loads(raw).get("quilt_loader") or {}
            info = data.get("metadata") or {}
            meta.update(
                name=str(info.get("name") or data.get("id") or path.name),
                id=str(data.get("id") or ""),
                version=str(data.get("version") or ""),
                description=_text(info.get("description")),
                authors=_authors(info.get("contributors")),
                loader="quilt",
            )
        except (ValueError, AttributeError):
            pass
        return meta
    raw = _read_zip_text(path, "META-INF/mods.toml")
    if raw:
        def field(key: str) -> str:
            match = re.search(rf'(?m)^\s*{key}\s*=\s*"([^"]*)"', raw)
            return match.group(1).strip() if match else ""
        meta.update(
            name=field("displayName") or field("modId") or path.name,
            id=field("modId"),
            version=field("version"),
            description=_text(field("description")),
            authors=_authors(field("authors")),
            loader="forge",
        )
        return meta
    raw = _read_zip_text(path, "mcmod.info")
    if raw:
        try:
            data = json.loads(raw)
            item = data[0] if isinstance(data, list) and data else data
            if isinstance(item, dict):
                meta.update(
                    name=str(item.get("name") or item.get("modid") or path.name),
                    id=str(item.get("modid") or ""),
                    version=str(item.get("version") or ""),
                    description=_text(item.get("description")),
                    authors=_authors(item.get("authorList")),
                    loader="forge",
                )
        except (ValueError, IndexError, TypeError):
            pass
        return meta
    raw = _read_zip_text(path, "META-INF/MANIFEST.MF")
    if raw:
        title = re.search(r"(?im)^Implementation-Title:\s*(.+)$", raw)
        version = re.search(r"(?im)^Implementation-Version:\s*(.+)$", raw)
        if title:
            meta["name"] = title.group(1).strip()
        if version:
            meta["version"] = version.group(1).strip()
    return meta


def list_mods(root: Path) -> list[dict[str, Any]]:
    folder = root / "mods"
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        enabled = path.name.lower().endswith(".jar")
        disabled = path.name.lower().endswith(".jar.disabled")
        if not (enabled or disabled):
            continue
        display_name = path.name[: -len(".disabled")] if disabled else path.name
        meta = _parse_mod_meta(path)
        result.append(
            {
                "kind": "mods",
                "name": meta.get("name") or display_name,
                "filename": path.name,
                "enabled": enabled,
                "size": path.stat().st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
                "description": meta.get("description") or "",
                "version": meta.get("version") or "",
                "modid": meta.get("id") or "",
                "authors": meta.get("authors") or "",
                "loader": meta.get("loader") or "",
            }
        )
    return result


def _pack_description(mcmeta: dict[str, Any]) -> str:
    pack = mcmeta.get("pack") if isinstance(mcmeta, dict) else None
    if not isinstance(pack, dict):
        return ""
    desc = pack.get("description")
    return _text(desc)


def _read_options(root: Path) -> tuple[list[str], list[str]]:
    path = root / "options.txt"
    lines: list[str] = []
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    packs: list[str] = []
    for line in lines:
        if line.startswith("resourcePacks:"):
            value = line.split(":", 1)[1]
            try:
                data = json.loads(value)
                if isinstance(data, list):
                    packs = [str(item) for item in data]
            except ValueError:
                packs = re.findall(r'"((?:[^"\\]|\\.)*)"', value)
            break
    return lines, packs


def _write_options(root: Path, lines: list[str], packs: list[str]) -> None:
    path = root / "options.txt"
    value = "resourcePacks:" + json.dumps(packs, ensure_ascii=False, separators=(",", ":"))
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            lines[index] = value
            replaced = True
            break
    if not replaced:
        lines.append(value)
    if not any(line.startswith("incompatibleResourcePacks:") for line in lines):
        lines.append("incompatibleResourcePacks:[]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def list_resourcepacks(root: Path) -> list[dict[str, Any]]:
    folder = root / "resourcepacks"
    folder.mkdir(parents=True, exist_ok=True)
    _, enabled_packs = _read_options(root)
    result = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix.lower() not in (".zip",):
            continue
        if not path.is_file() and not path.is_dir():
            continue
        mcmeta: dict[str, Any] = {}
        if path.is_file():
            raw = _read_zip_text(path, "pack.mcmeta")
        else:
            meta_file = path / "pack.mcmeta"
            raw = meta_file.read_text(encoding="utf-8", errors="replace") if meta_file.exists() else None
        if raw:
            try:
                mcmeta = json.loads(raw)
            except ValueError:
                mcmeta = {}
        pack_id = f"file/{path.name}"
        size = path.stat().st_size if path.is_file() else directory_size(path)
        result.append(
            {
                "kind": "resourcepacks",
                "name": _pack_description(mcmeta) or path.name,
                "filename": path.name,
                "enabled": pack_id in enabled_packs,
                "size": size,
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
                "description": _pack_description(mcmeta),
                "is_dir": path.is_dir(),
            }
        )
    return result


def list_shaderpacks(root: Path) -> list[dict[str, Any]]:
    folder = root / "shaderpacks"
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix.lower() != ".zip":
            continue
        if not path.is_file() and not path.is_dir():
            continue
        size = path.stat().st_size if path.is_file() else directory_size(path)
        result.append(
            {
                "kind": "shaderpacks",
                "name": path.name,
                "filename": path.name,
                "size": size,
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
                "is_dir": path.is_dir(),
            }
        )
    return result


class _NBTReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def read(self, count: int) -> bytes:
        chunk = self.data[self.pos:self.pos + count]
        self.pos += count
        return chunk

    def u1(self) -> int:
        return struct.unpack(">B", self.read(1))[0]

    def i2(self) -> int:
        return struct.unpack(">h", self.read(2))[0]

    def u2(self) -> int:
        return struct.unpack(">H", self.read(2))[0]

    def i4(self) -> int:
        return struct.unpack(">i", self.read(4))[0]

    def i8(self) -> int:
        return struct.unpack(">q", self.read(8))[0]

    def string(self) -> str:
        length = self.u2()
        return self.read(length).decode("utf-8", errors="replace")

    def payload(self, tag: int):
        if tag == 0:
            return None
        if tag == 1:
            return struct.unpack(">b", self.read(1))[0]
        if tag == 2:
            return self.i2()
        if tag == 3:
            return self.i4()
        if tag == 4:
            return self.i8()
        if tag == 5:
            return struct.unpack(">f", self.read(4))[0]
        if tag == 6:
            return struct.unpack(">d", self.read(8))[0]
        if tag == 7:
            length = self.i4()
            return self.read(length)
        if tag == 8:
            return self.string()
        if tag == 9:
            item_type = self.u1()
            length = self.i4()
            return [self.payload(item_type) for _ in range(max(0, length))]
        if tag == 10:
            result = {}
            while True:
                item_type = self.u1()
                if item_type == 0:
                    return result
                name = self.string()
                result[name] = self.payload(item_type)
        if tag == 11:
            length = self.i4()
            return [self.i4() for _ in range(max(0, length))]
        if tag == 12:
            length = self.i4()
            return [self.i8() for _ in range(max(0, length))]
        return None


def _read_level_dat(path: Path) -> dict[str, Any]:
    try:
        with gzip.open(path, "rb") as handle:
            data = handle.read()
        reader = _NBTReader(data)
        tag = reader.u1()
        if tag != 10:
            return {}
        reader.string()
        payload = reader.payload(10)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, struct.error, EOFError):
        return {}


def list_saves(root: Path) -> list[dict[str, Any]]:
    folder = root / "saves"
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        level = _read_level_dat(path / "level.dat")
        data = level.get("Data") if isinstance(level.get("Data"), dict) else {}
        last = data.get("LastPlayed") if isinstance(data, dict) else None
        last_str = ""
        if isinstance(last, (int, float)) and last > 0:
            last_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last / 1000))
        version = data.get("Version") if isinstance(data, dict) else {}
        game_type = data.get("GameType") if isinstance(data, dict) else None
        result.append(
            {
                "kind": "saves",
                "name": str(data.get("LevelName") or path.name),
                "filename": path.name,
                "size": directory_size(path),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
                "last_played": last_str,
                "game_type": {
                    0: "生存", 1: "创造", 2: "冒险", 3: "旁观",
                }.get(game_type if isinstance(game_type, int) else -1, ""),
                "hardcore": bool(data.get("hardcore")) if isinstance(data, dict) else False,
                "version": str((version or {}).get("Name") or "") if isinstance(version, dict) else "",
            }
        )
    return result


def scan(config: Config, service: MinecraftService, version_id: str) -> dict[str, Any]:
    root = _root(config, service, version_id)
    meta = service.version_meta(version_id)
    return {
        "version": version_id,
        "game_dir": str(root),
        "isolated": bool(meta["isolated"]) if isinstance(meta.get("isolated"), bool) else bool(config.get("version_isolation", True)),
        "mods": list_mods(root),
        "resourcepacks": list_resourcepacks(root),
        "shaderpacks": list_shaderpacks(root),
        "saves": list_saves(root),
    }


def _safe_child(base: Path, name: str) -> Path:
    clean = Path(str(name)).name
    if not clean or clean in (".", ".."):
        raise FetchError("文件名不合法")
    target = (base / clean).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise FetchError("文件路径不合法")
    return target


def toggle(config: Config, service: MinecraftService, version_id: str, kind: str, name: str) -> dict[str, Any]:
    root = _root(config, service, version_id)
    if kind == "mods":
        target = _safe_child(root / "mods", name)
        if not target.exists():
            raise FetchError("模组文件不存在")
        if target.name.lower().endswith(".jar"):
            new = target.with_name(target.name + ".disabled")
        elif target.name.lower().endswith(".jar.disabled"):
            new = target.with_name(target.name[: -len(".disabled")])
        else:
            raise FetchError("不是可切换的模组文件")
        if new.exists():
            raise FetchError("目标文件已存在")
        target.rename(new)
        return {"filename": new.name, "enabled": new.name.lower().endswith(".jar")}
    if kind == "resourcepacks":
        path = _safe_child(root / "resourcepacks", name)
        if not path.exists():
            raise FetchError("资源包不存在")
        pack_id = f"file/{path.name}"
        lines, packs = _read_options(root)
        if pack_id in packs:
            packs = [p for p in packs if p != pack_id]
            enabled = False
        else:
            packs.append(pack_id)
            enabled = True
        if "vanilla" not in packs:
            packs.insert(0, "vanilla")
        _write_options(root, lines, packs)
        return {"filename": path.name, "enabled": enabled}
    raise FetchError("该类型不支持启用/禁用")


def delete(config: Config, service: MinecraftService, version_id: str, kind: str, name: str) -> None:
    root = _root(config, service, version_id)
    base = root / KIND_DIRS.get(kind, "")
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
    target = _safe_child(base, name)
    if not target.exists():
        raise FetchError("文件不存在")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def import_content(config: Config, service: MinecraftService, version_id: str, kind: str, source: str) -> dict[str, Any]:
    root = _root(config, service, version_id)
    src = Path(os.path.expanduser(str(source))).resolve()
    if not src.exists():
        raise FetchError("导入源不存在")
    folder = root / KIND_DIRS.get(kind, "")
    if kind not in KIND_DIRS:
        raise FetchError("不支持的内容类型")
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "mods" and not src.is_file():
        raise FetchError("模组必须是 .jar 文件")
    if kind == "mods" and src.suffix.lower() != ".jar":
        raise FetchError("模组必须是 .jar 文件")
    if src.is_dir():
        target = _safe_child(folder, src.name)
        if target.exists():
            raise FetchError("同名内容已存在")
        shutil.copytree(src, target)
    else:
        target = _safe_child(folder, src.name)
        if target.exists():
            raise FetchError("同名内容已存在")
        shutil.copy2(src, target)
    return {"filename": target.name}


def backup_save(config: Config, service: MinecraftService, version_id: str, name: str) -> dict[str, Any]:
    root = _root(config, service, version_id)
    saves = root / "saves"
    source = _safe_child(saves, name)
    if not source.is_dir():
        raise FetchError("存档不存在")
    backups = root / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backups / f"{source.name}-{stamp}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in source.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(source))
                count += 1
    return {"filename": target.name, "files": count, "size": target.stat().st_size}
