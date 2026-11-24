#!/usr/bin/env python3
"""把 Python 后端与 web/ 前端打包成单文件 pcl-single.py。"""
from __future__ import annotations

import base64
import io
import os
import sys
import zipfile
import zlib
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pcl_core.config import APP_VERSION  # noqa: E402

OUTPUT = ROOT / "pcl-single.py"
PREFIX = "PCLSINGLE1:"


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(ROOT / "pcl.py", "pcl.py")
        for path in sorted((ROOT / "pcl_core").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
        for path in sorted((ROOT / "web").rglob("*")):
            if not path.is_file():
                continue
            if path.suffix in {".pyc"} or "__pycache__" in path.parts:
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
    return buffer.getvalue()


def payload(raw: bytes) -> str:
    encoded = base64.b85encode(zlib.compress(raw, 9)).decode("ascii")
    return "\n".join(repr(chunk) for chunk in wrap(encoded, 96))


TEMPLATE = '''#!/usr/bin/env python3
"""PCL Linux ARM64 单文件版。首次运行会释放内置运行时到缓存目录。"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import runpy
import shutil
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

APP_VERSION = {version!r}
PAYLOAD = (
{payload}
)


def _runtime_root() -> Path:
    raw = zlib.decompress(base64.b85decode(PAYLOAD))
    digest = hashlib.sha256(raw).hexdigest()[:16]
    base = Path(os.environ.get("PCL_SINGLE_HOME") or (Path.home() / ".cache" / "pcl-linux-arm64" / "single"))
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path(tempfile.gettempdir()) / "pcl-linux-arm64-single"
        base.mkdir(parents=True, exist_ok=True)
    target = base / digest
    marker = target / ".complete"
    if marker.is_file():
        return target
    tmp = Path(tempfile.mkdtemp(prefix="extract-", dir=str(base)))
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for member in zf.infolist():
                dest = (tmp / member.filename).resolve()
                if dest != tmp.resolve() and tmp.resolve() not in dest.parents:
                    continue
                zf.extract(member, tmp)
        (tmp / ".complete").write_text(APP_VERSION, encoding="utf-8")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        os.replace(tmp, target)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return target


def main() -> None:
    root = _runtime_root()
    sys.path.insert(0, str(root))
    sys.argv[0] = str(root / "pcl.py")
    runpy.run_path(str(root / "pcl.py"), run_name="__main__")


if __name__ == "__main__":
    main()
'''


def main() -> None:
    raw = build_zip()
    body = TEMPLATE.format(version=APP_VERSION, payload=payload(raw))
    OUTPUT.write_text(body, encoding="utf-8")
    OUTPUT.chmod(0o755)
    print(f"built {OUTPUT}  {OUTPUT.stat().st_size:,} bytes  zip={len(raw):,} bytes")


if __name__ == "__main__":
    main()
