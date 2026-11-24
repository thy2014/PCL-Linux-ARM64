"""HTTP 获取与可续传下载。"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .util import sha1_file, sha256_file

USER_AGENT = "PCL-Launcher/1.0 (+https://github.com/thy2014/PCL-Linux-ARM64)"
JSON_HEADERS = {"Accept": "application/json, text/plain, */*"}


class FetchError(Exception):
    """网络或 HTTP 错误。"""

    def __init__(self, message: str, url: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status = status


class DownloadCancelled(Exception):
    """用户取消下载。"""


ProgressCallback = Callable[[int], None]


def _request(url: str, headers: dict[str, str] | None = None) -> urllib.request.Request:
    final_headers = {"User-Agent": USER_AGENT}
    if headers:
        final_headers.update(headers)
    return urllib.request.Request(url, headers=final_headers)


def open_stream(url: str, timeout: float = 60, headers: dict[str, str] | None = None):
    try:
        return urllib.request.urlopen(_request(url, headers), timeout=timeout)
    except urllib.error.HTTPError as error:
        raise FetchError(f"HTTP {error.code}", url, error.code) from error
    except urllib.error.URLError as error:
        raise FetchError(f"网络错误：{error.reason}", url) from error
    except TimeoutError as error:
        raise FetchError("连接超时", url) from error


def get_text(url: str, timeout: float = 30, retries: int = 2) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with open_stream(url, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except FetchError as error:
            last_error = error
            if error.status and error.status < 500:
                raise
        except OSError as error:
            last_error = error
        if attempt < retries:
            time.sleep(0.8 * (attempt + 1))
    raise FetchError(str(last_error or "请求失败"), url)


def get_json(url: str, timeout: float = 30, retries: int = 2):
    text = get_text(url, timeout=timeout, retries=retries)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise FetchError(f"JSON 解析失败：{error}", url) from error


def maven_sha1(url: str) -> str | None:
    """读取 Maven Central 的 .sha1 校验文件，失败返回 None。"""
    try:
        text = get_text(url + ".sha1", timeout=20, retries=1).strip().split()[0]
    except (FetchError, IndexError):
        return None
    return text.lower() if len(text) == 40 else None


def download_file(
    url: str,
    dest: Path,
    *,
    sha1: str | None = None,
    sha256: str | None = None,
    size: int | None = None,
    progress: ProgressCallback | None = None,
    cancel=None,
    retries: int = 3,
    timeout: float = 60,
    log: Callable[[str], None] | None = None,
) -> Path:
    """流式下载到 dest.part，校验通过后原子改名为 dest；支持 Range 断点续传。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled(str(dest))
        try:
            offset = part.stat().st_size if part.exists() else 0
            headers = {"Accept": "*/*"}
            if offset > 0:
                headers["Range"] = f"bytes={offset}-"
            with open_stream(url, timeout=timeout, headers=headers) as response:
                status = getattr(response, "status", 200)
                if offset > 0 and status != 206:
                    offset = 0  # 服务端不支持续传，重新开始
                mode = "ab" if offset > 0 else "wb"
                with open(part, mode) as output:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise DownloadCancelled(str(dest))
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        output.write(chunk)
                        if progress is not None:
                            progress(len(chunk))
            actual_size = part.stat().st_size
            if size is not None and actual_size != int(size):
                part.unlink(missing_ok=True)
                raise FetchError(f"文件大小不符（期望 {size}，实际 {actual_size}）", url)
            if sha1:
                if sha1_file(part, cancel=cancel).lower() != sha1.lower():
                    part.unlink(missing_ok=True)
                    raise FetchError("SHA1 校验失败", url)
            if sha256:
                if sha256_file(part, cancel=cancel).lower() != sha256.lower():
                    part.unlink(missing_ok=True)
                    raise FetchError("SHA256 校验失败", url)
            os.replace(part, dest)
            return dest
        except DownloadCancelled:
            raise
        except FetchError as error:
            last_error = error
            if error.status == 404:
                raise
            if error.status in (401, 403):
                raise
            if error.status == 416:
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass
            if attempt < retries:
                if log is not None:
                    log(f"下载重试 {attempt + 1}/{retries}：{error}")
                time.sleep(0.8 * (attempt + 1))
        except (OSError, ValueError) as error:
            last_error = error
            if attempt < retries:
                if log is not None:
                    log(f"下载中断，准备重试：{error}")
                time.sleep(0.8 * (attempt + 1))

    raise FetchError(f"下载失败：{last_error}", url)


def is_download_cancelled(cancel) -> bool:
    return bool(cancel is not None and cancel.is_set())
