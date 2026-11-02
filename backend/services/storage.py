"""原始文件存储。

原则：
- 原始文件按 workspace/document/version 隔离保存，落盘路径只使用内部 ID。
- 上传时流式计算 SHA-256，不把整份文件读进内存。
- 同名文件的新内容写入新版本目录，绝不覆盖旧版本目录。
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from core.config import get_settings, max_size_for_suffix
from services.errors import ConflictError, TooLargeError, UnsupportedMediaError

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}
SUFFIX_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class SavedFile:
    path: Path
    size: int
    sha256: str
    suffix: str
    media_type: str


def sanitize_filename(file_name: Optional[str]) -> str:
    """只保留文件名本身，去掉路径与控制字符。"""
    name = Path((file_name or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip()
    if not name:
        name = "未命名文件"
    if len(name) > 200:
        suffix = Path(name).suffix[:16]
        name = name[: 200 - len(suffix)] + suffix
    return name


def normalize_name(file_name: str) -> str:
    """用于判断“同名文档”的规范化键（大小写与全半角归一）。"""
    return unicodedata.normalize("NFKC", file_name).strip().casefold()


def validate_suffix(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedMediaError(
            f"暂不支持 {suffix or '无扩展名'} 文件，仅支持 PDF（带文字层）、TXT、Markdown",
            details={"file_name": file_name, "supported": sorted(SUPPORTED_SUFFIXES)},
        )
    return suffix


def media_type_for(suffix: str) -> str:
    return SUFFIX_MEDIA_TYPES.get(suffix, "application/octet-stream")


def version_dir(workspace_id: str, document_id: str, version_id: str) -> Path:
    return (
        get_settings().upload_dir
        / "workspaces"
        / workspace_id
        / "documents"
        / document_id
        / "versions"
        / version_id
    )


async def stage_upload(
    upload: UploadFile,
    *,
    staging_root: Path,
    file_name: str,
    suffix: str,
) -> SavedFile:
    """先写入暂存目录并计算哈希。

    只有确认不是重复文件后，才移动到不可变的版本目录。
    """
    settings = get_settings()
    limit = min(max_size_for_suffix(suffix), settings.max_upload_size_bytes)
    staging_root.mkdir(parents=True, exist_ok=True)
    destination = staging_root / f"original{suffix}"
    part_path = staging_root / f"original{suffix}.part"
    digest = hashlib.sha256()
    size = 0

    try:
        with part_path.open("wb") as target:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise TooLargeError(
                        f"文件超过大小限制（{limit // (1024 * 1024)} MB）",
                        code="TOO_LARGE",
                        details={
                            "max_size_mb": limit // (1024 * 1024),
                            "file_name": file_name,
                        },
                    )
                digest.update(chunk)
                target.write(chunk)

        os.replace(part_path, destination)
    except Exception:
        part_path.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return SavedFile(
        path=destination,
        size=size,
        sha256=digest.hexdigest(),
        suffix=suffix,
        media_type=media_type_for(suffix),
    )


def finalize_upload(
    saved: SavedFile,
    *,
    workspace_id: str,
    document_id: str,
    version_id: str,
) -> SavedFile:
    """把暂存文件移动到不可变的版本目录。"""
    dest_dir = version_dir(workspace_id, document_id, version_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / f"original{saved.suffix}"
    if destination.exists():
        raise ConflictError("该版本的文件已存在，版本不可覆盖", code="VERSION_EXISTS")
    try:
        os.replace(saved.path, destination)
    except OSError:
        # 跨磁盘移动时 os.replace 可能失败，退化为复制后删除
        import shutil

        shutil.copy2(saved.path, destination)
        saved.path.unlink(missing_ok=True)
    return SavedFile(
        path=destination,
        size=saved.size,
        sha256=saved.sha256,
        suffix=saved.suffix,
        media_type=saved.media_type,
    )


def remove_staged(saved: SavedFile) -> None:
    saved.path.unlink(missing_ok=True)
    try:
        saved.path.parent.rmdir()
    except OSError:
        pass


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def original_file_exists(file_path: Optional[str | Path]) -> bool:
    """原始文件是否仍在受管存储中；缺失即视为文档已被删除。"""
    if not file_path:
        return False
    try:
        return Path(file_path).is_file()
    except (OSError, ValueError):
        return False


def assert_managed_path(path: Path) -> Path:
    """下载前确认路径位于上传目录内。"""
    upload_root = get_settings().upload_dir.resolve()
    resolved = path.resolve()
    if upload_root not in resolved.parents and resolved != upload_root:
        raise ConflictError("文件路径不在受管目录内", code="UNSAFE_PATH")
    return resolved


def cleanup_version_files(workspace_id: str, document_id: str, version_id: str) -> None:
    """仅用于上传失败回滚；已入库版本从不调用。"""
    import shutil

    shutil.rmtree(version_dir(workspace_id, document_id, version_id), ignore_errors=True)


def stable_name_for_missing(file_name: str) -> str:
    """兜底展示名：去掉扩展名之外的路径信息。"""
    return re.sub(r"\s+", " ", file_name).strip()
