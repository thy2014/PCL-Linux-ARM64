"""服务器列表与 Minecraft 状态协议延迟检测。"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Paths
from .http_client import FetchError
from .util import atomic_write_json, read_json


def _varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_varint(sock: socket.socket) -> int:
    value = 0
    shift = 0
    while True:
        data = sock.recv(1)
        if not data:
            raise FetchError("服务器关闭了连接")
        byte = data[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
        if shift > 35:
            raise FetchError("服务器响应异常")


def _mc_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _varint(len(encoded)) + encoded


def _motd(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = str(value.get("text") or "")
        for child in value.get("extra") or []:
            text += _motd(child)
        return text
    if isinstance(value, list):
        return "".join(_motd(item) for item in value)
    return ""


class ServerStore:
    def __init__(self, paths: Paths) -> None:
        self.path = paths.data_dir / "servers.json"
        self._lock = threading.RLock()

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                data = read_json(self.path)
                servers = data.get("servers") if isinstance(data, dict) else []
                return [s for s in servers if isinstance(s, dict)] if isinstance(servers, list) else []
            except (OSError, ValueError):
                return []

    def save(self, servers: list[dict[str, Any]]) -> None:
        with self._lock:
            atomic_write_json(self.path, {"servers": servers})

    def list(self) -> list[dict[str, Any]]:
        return self.load()

    def add(self, name: str, host: str, port: int = 25565) -> dict[str, Any]:
        host = host.strip()
        if not host or any(ch.isspace() for ch in host) or "://" in host:
            raise FetchError("服务器地址不合法")
        if not (1 <= int(port) <= 65535):
            raise FetchError("端口不合法")
        with self._lock:
            servers = self.load()
            if any(item.get("host") == host and int(item.get("port") or 25565) == int(port) for item in servers):
                raise FetchError("该服务器已在列表中")
            server = {
                "id": uuid.uuid4().hex[:12],
                "name": name.strip()[:40] or host,
                "host": host[:253],
                "port": int(port),
                "added_at": time.time(),
            }
            servers.append(server)
            self.save(servers)
            return server

    def update(self, server_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            servers = self.load()
            for item in servers:
                if item.get("id") == server_id:
                    if patch.get("name"):
                        item["name"] = str(patch["name"]).strip()[:40]
                    if patch.get("host"):
                        host = str(patch["host"]).strip()
                        if not host or any(ch.isspace() for ch in host) or "://" in host:
                            raise FetchError("服务器地址不合法")
                        item["host"] = host[:253]
                    if patch.get("port") is not None:
                        port = int(patch["port"])
                        if not (1 <= port <= 65535):
                            raise FetchError("端口不合法")
                        item["port"] = port
                    self.save(servers)
                    return item
        raise FetchError("服务器不存在")

    def delete(self, server_id: str) -> None:
        with self._lock:
            servers = self.load()
            filtered = [item for item in servers if item.get("id") != server_id]
            if len(filtered) == len(servers):
                raise FetchError("服务器不存在")
            self.save(filtered)


def ping(host: str, port: int = 25565, timeout: float = 5.0) -> dict[str, Any]:
    host = host.strip()
    if not host or any(ch.isspace() for ch in host):
        raise FetchError("服务器地址不合法")
    port = int(port or 25565)
    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            packet = _varint(0) + _varint(47) + _mc_string(host) + struct.pack(">H", port) + _varint(1)
            sock.sendall(_varint(len(packet)) + packet)
            sock.sendall(_varint(1) + _varint(0))
            length = _read_varint(sock)
            if length <= 0 or length > 4_000_000:
                raise FetchError("服务器响应长度异常")
            payload = b""
            while len(payload) < length:
                chunk = sock.recv(length - len(payload))
                if not chunk:
                    break
                payload += chunk
            if not payload:
                raise FetchError("服务器没有返回状态")
            packet_id = payload[0]
            if packet_id != 0:
                raise FetchError("服务器状态包异常")
            # 读取 JSON 字符串（varint 长度 + UTF-8）
            pos = 1
            strlen = 0
            shift = 0
            while pos < len(payload):
                byte = payload[pos]
                pos += 1
                strlen |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            text = payload[pos:pos + strlen].decode("utf-8", errors="replace")
            data = json.loads(text)
            latency = int((time.time() - started) * 1000)
            players = data.get("players") or {}
            version = data.get("version") or {}
            return {
                "ok": True,
                "latency": latency,
                "version": version.get("name") or "",
                "protocol": version.get("protocol"),
                "online": int(players.get("online") or 0),
                "max": int(players.get("max") or 0),
                "motd": _motd(data.get("description"))[:300],
                "favicon": data.get("favicon") or "",
            }
    except (OSError, ValueError, FetchError) as error:
        return {"ok": False, "error": str(error), "latency": int((time.time() - started) * 1000)}
