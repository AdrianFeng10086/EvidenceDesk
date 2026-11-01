"""
运行配置

所有路径均相对项目根目录（evidence-desk/）解析。这样无论从
项目根目录还是 backend/ 目录启动，数据库和上传目录都落在同一个位置。

环境变量来自项目根目录的 .env（若存在），可用真实环境变量覆盖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# backend/core/config.py -> backend/core -> backend -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw: str, default: str) -> Path:
    path = Path(raw or default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _sqlite_url(raw: str) -> str:
    """把 sqlite:/// 相对路径固定到项目根目录。"""
    prefix = "sqlite:///"
    if not raw.startswith(prefix):
        return raw
    raw_path = raw[len(prefix) :]
    if raw_path in {"", ":memory:"}:
        return raw
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{path.as_posix()}"


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    database_url: str
    upload_dir: Path
    data_dir: Path

    max_upload_size_mb: int
    max_pdf_size_mb: int
    max_text_size_mb: int
    max_pdf_pages: int
    max_documents_per_workspace: int

    demo_mode: bool
    demo_workspace_id: str
    demo_workspace_name: str
    demo_user_id: str

    cors_origins: list[str]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    @property
    def max_text_size_bytes(self) -> int:
        return self.max_text_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = _resolve_path(os.getenv("DATA_DIR", "./data"), "./data")
    upload_dir = _resolve_path(os.getenv("UPLOAD_DIR", "./data/uploads"), "./data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    raw_db = os.getenv("DATABASE_URL", "sqlite:///./data/db/evidence.db")
    database_url = _sqlite_url(raw_db)

    cors = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    ]

    return Settings(
        app_name="有据工作台后端",
        app_version="0.2.0",
        database_url=database_url,
        upload_dir=upload_dir,
        data_dir=data_dir,
        max_upload_size_mb=_env_int("MAX_UPLOAD_SIZE_MB", 50),
        max_pdf_size_mb=_env_int("MAX_PDF_SIZE_MB", 10),
        max_text_size_mb=_env_int("MAX_TEXT_SIZE_MB", 10),
        max_pdf_pages=_env_int("MAX_PDF_PAGES", 30),
        max_documents_per_workspace=_env_int("MAX_DOCUMENTS_PER_WORKSPACE", 10),
        demo_mode=_env_bool("DEMO_MODE", True),
        demo_workspace_id=os.getenv("DEMO_WORKSPACE_ID", "demo_workspace"),
        demo_workspace_name=os.getenv("DEMO_WORKSPACE_NAME", "演示资料空间"),
        demo_user_id=os.getenv("DEMO_USER_ID", "demo_user"),
        cors_origins=cors,
    )


def max_size_for_suffix(suffix: str) -> int:
    settings = get_settings()
    if suffix == ".pdf":
        return settings.max_pdf_size_bytes
    return settings.max_text_size_bytes


def optional_suffix(file_name: Optional[str]) -> str:
    return Path(file_name or "").suffix.lower()
