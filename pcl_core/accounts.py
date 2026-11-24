"""离线账户管理（PCL 账户列表的精简实现）。"""
from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any

from .config import Paths
from .http_client import FetchError
from .util import atomic_write_json, offline_uuid, read_json

NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


class AccountStore:
    def __init__(self, paths: Paths, default_name: str = "Steve") -> None:
        self.path = paths.data_dir / "accounts.json"
        self._lock = threading.RLock()
        self._ensure_default(default_name)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"accounts": [], "selected": ""}
        try:
            data = read_json(self.path)
            if isinstance(data, dict) and isinstance(data.get("accounts"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"accounts": [], "selected": ""}

    def _write(self, data: dict[str, Any]) -> None:
        atomic_write_json(self.path, data)

    def _ensure_default(self, name: str) -> None:
        with self._lock:
            data = self._read()
            accounts = [a for a in data.get("accounts", []) if isinstance(a, dict) and a.get("name")]
            if not accounts:
                name = self._clean(name)
                accounts = [self._new(name)]
                data = {"accounts": accounts, "selected": accounts[0]["id"]}
                self._write(data)
            elif not data.get("selected") or not any(a.get("id") == data.get("selected") for a in accounts):
                data["selected"] = accounts[0]["id"]
                data["accounts"] = accounts
                self._write(data)

    def _clean(self, name: str) -> str:
        name = str(name or "").strip()
        if not NAME_RE.match(name):
            raise FetchError("玩家名只能包含字母、数字、下划线，长度 1–16")
        return name

    def _new(self, name: str) -> dict[str, Any]:
        return {
            "id": uuid.uuid4().hex[:12],
            "type": "offline",
            "name": self._clean(name),
            "uuid": offline_uuid(name),
            "created_at": time.time(),
        }

    def list(self) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            accounts = [a for a in data.get("accounts", []) if isinstance(a, dict)]
            selected = next((a for a in accounts if a.get("id") == data.get("selected")), accounts[0] if accounts else None)
            return {"accounts": accounts, "selected": selected}

    def add(self, name: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            clean = self._clean(name)
            if any(a.get("name", "").lower() == clean.lower() for a in data.get("accounts", [])):
                raise FetchError("该离线账户已存在")
            account = self._new(clean)
            data.setdefault("accounts", []).append(account)
            data["selected"] = account["id"]
            self._write(data)
            return account

    def select(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            account = next((a for a in data.get("accounts", []) if a.get("id") == account_id), None)
            if not account:
                raise FetchError("账户不存在")
            data["selected"] = account_id
            self._write(data)
            return account

    def remove(self, account_id: str) -> None:
        with self._lock:
            data = self._read()
            accounts = [a for a in data.get("accounts", []) if a.get("id") != account_id]
            if len(accounts) == len(data.get("accounts", [])):
                raise FetchError("账户不存在")
            if not accounts:
                raise FetchError("至少保留一个离线账户")
            data["accounts"] = accounts
            if data.get("selected") == account_id:
                data["selected"] = accounts[0]["id"]
            self._write(data)

    def rename_selected(self, name: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            accounts = [a for a in data.get("accounts", []) if isinstance(a, dict)]
            selected = next((a for a in accounts if a.get("id") == data.get("selected")), None)
            if not selected or selected.get("type") != "offline":
                raise FetchError("当前账户不支持修改玩家名")
            clean = self._clean(name)
            if any(a.get("id") != selected.get("id") and a.get("name", "").lower() == clean.lower() for a in accounts):
                raise FetchError("该玩家名已被其他账户使用")
            selected["name"] = clean
            selected["uuid"] = offline_uuid(clean)
            self._write(data)
            return selected

    def selected(self) -> dict[str, Any]:
        return self.list().get("selected") or {"type": "offline", "name": "Steve", "uuid": offline_uuid("Steve")}
