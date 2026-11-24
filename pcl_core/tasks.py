"""后台任务与进度聚合。"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any


class Task:
    def __init__(self, task_id: str, kind: str, title: str) -> None:
        self.id = task_id
        self.kind = kind
        self.title = title
        self.status = "running"  # running / done / failed / cancelled
        self.phase = "准备中"
        self.current = ""
        self.message = ""
        self.error = ""
        self.total_files = 0
        self.done_files = 0
        self.skipped_files = 0
        self.total_bytes = 0
        self.done_bytes = 0
        self.start_time = time.time()
        self.end_time: float | None = None
        self.logs: deque[str] = deque(maxlen=260)
        self.cancel_event = threading.Event()
        self._lock = threading.RLock()
        self._last_sample_time = self.start_time
        self._last_sample_bytes = 0
        self._speed = 0.0

    # ---- 更新 ----
    def log(self, line: str) -> None:
        if not line:
            return
        with self._lock:
            stamp = time.strftime("%H:%M:%S")
            self.logs.append(f"[{stamp}] {line}")

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.phase = phase

    def set_current(self, name: str) -> None:
        with self._lock:
            self.current = name

    def add_totals(self, files: int = 0, bytes_count: int = 0) -> None:
        with self._lock:
            self.total_files += max(0, int(files))
            self.total_bytes += max(0, int(bytes_count))

    def file_started(self, name: str = "") -> None:
        if name:
            self.set_current(name)

    def file_done(self, *, skipped: bool = False, name: str = "", bytes_count: int = 0) -> None:
        with self._lock:
            self.done_files += 1
            if skipped:
                self.skipped_files += 1
            if bytes_count:
                self.done_bytes += max(0, int(bytes_count))
            if name:
                self.current = name

    def add_bytes(self, count: int, *, count_speed: bool = True) -> None:
        with self._lock:
            self.done_bytes += max(0, int(count))
            if count_speed:
                now = time.time()
                elapsed = now - self._last_sample_time
                if elapsed >= 1.0:
                    delta = self.done_bytes - self._last_sample_bytes
                    instantaneous = delta / elapsed if elapsed > 0 else 0
                    self._speed = instantaneous if self._speed <= 0 else (self._speed * 0.7 + instantaneous * 0.3)
                    self._last_sample_time = now
                    self._last_sample_bytes = self.done_bytes

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = message
            self.message = message
            self.end_time = time.time()
            self.log(f"任务失败：{message}")

    def finish(self, message: str = "已完成") -> None:
        with self._lock:
            if self.status != "running":
                return
            self.status = "done"
            self.message = message
            self.done_files = max(self.done_files, self.total_files)
            if self.total_bytes:
                self.done_bytes = max(self.done_bytes, self.total_bytes)
            self.end_time = time.time()
            self.log(message)

    def cancel(self) -> None:
        with self._lock:
            self.cancel_event.set()
            if self.status == "running":
                self.status = "cancelling"
                self.message = "正在取消…"
                self.log("收到取消请求，正在停止下载…")

    def mark_cancelled(self) -> None:
        with self._lock:
            self.status = "cancelled"
            self.message = "已取消"
            self.end_time = time.time()
            self.log("任务已取消")

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise TaskCancelled()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self.total_files:
                percent = self.done_files / self.total_files * 100.0
            elif self.total_bytes:
                percent = self.done_bytes / self.total_bytes * 100.0
            else:
                percent = 0.0
            if self.status == "done":
                percent = 100.0
            percent = min(99.9, max(0.0, percent))
            elapsed = (self.end_time or time.time()) - self.start_time
            speed = self._speed
            remaining = max(0, self.total_bytes - self.done_bytes)
            eta = int(remaining / speed) if speed > 1024 else None
            if self.status == "done":
                percent = 100.0
                eta = 0
                speed = 0
            return {
                "id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
                "phase": self.phase,
                "current": self.current,
                "message": self.message,
                "error": self.error,
                "total_files": self.total_files,
                "done_files": self.done_files,
                "skipped_files": self.skipped_files,
                "total_bytes": self.total_bytes,
                "done_bytes": self.done_bytes,
                "percent": round(percent, 2),
                "speed": int(speed),
                "eta": eta,
                "elapsed": int(elapsed),
                "logs": list(self.logs),
            }


class TaskCancelled(Exception):
    pass


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()

    def create(self, kind: str, title: str) -> Task:
        task = Task(uuid.uuid4().hex[:12], kind, title)
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def snapshot(self, task_id: str) -> dict[str, Any] | None:
        task = self.get(task_id)
        return task.snapshot() if task else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [task.snapshot() for task in sorted(tasks, key=lambda item: item.start_time, reverse=True)]

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if not task:
            return False
        task.cancel()
        return True
