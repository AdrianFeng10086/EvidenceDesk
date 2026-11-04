"""数据库连接与会话管理（SQLite + SQLAlchemy）。"""

from __future__ import annotations

from typing import Generator, List

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # FastAPI 的同步路由和后台解析任务可能在不同线程执行
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表、补齐旧库字段并写入演示资料空间。"""
    from db import models  # noqa: F401 — 注册所有表

    models.Base.metadata.create_all(bind=engine)
    _migrate_schema()
    seed_demo_workspace()


def _migrate_schema() -> None:
    """SQLite 轻量迁移：create_all 只建新表，不会给旧表加列。"""
    if not settings.database_url.startswith("sqlite"):
        return

    columns = {
        "workspaces": (
            ("deleted_at", "DATETIME"),
            ("deleted_by", "VARCHAR(128)"),
        ),
        "documents": (
            ("deleted_at", "DATETIME"),
            ("deleted_by", "VARCHAR(128)"),
        ),
        "document_versions": (
            ("index_status", "VARCHAR(24) DEFAULT 'pending'"),
            ("index_error_code", "VARCHAR(48)"),
            ("index_error", "TEXT"),
            ("index_version", "VARCHAR(64)"),
            ("embedding_model", "VARCHAR(120)"),
            ("chunk_count", "INTEGER"),
            ("indexed_at", "DATETIME"),
        ),
        "retrieval_chunks": (
            ("section_title", "TEXT"),
        ),
        "runs": (
            ("scope_hash", "VARCHAR(64)"),
            ("index_version", "VARCHAR(64)"),
            ("retrieval_log_id", "VARCHAR(64)"),
            ("stale_at", "DATETIME"),
            ("stale_reason", "VARCHAR(64)"),
        ),
    }
    with engine.begin() as connection:
        for table, additions in columns.items():
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for name, ddl_type in additions:
                if name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"
                    )


def seed_demo_workspace() -> None:
    if not settings.demo_mode:
        return

    from db.models import Workspace

    with SessionLocal() as db:
        existing = db.get(Workspace, settings.demo_workspace_id)
        if existing:
            return
        db.add(
            Workspace(
                id=settings.demo_workspace_id,
                name=settings.demo_workspace_name,
                description="首版演示账户使用的资料空间，仅含示例与用户上传资料。",
                owner_id=settings.demo_user_id,
            )
        )
        db.commit()


def recover_interrupted_parses() -> List[str]:
    """服务重启时，把停留在中间状态的版本标记为失败，避免永久转圈。

    Day 3 的解析任务是进程内后台任务，进程退出后不会自动续跑。
    用户可以在前端点击“重新解析”。
    """
    from db.models import DocumentVersion, ParseJob

    touched: List[str] = []
    with SessionLocal() as db:
        versions = db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.parse_status.in_(["uploaded", "parsing", "indexing"])
            )
        ).all()
        for version in versions:
            version.parse_status = "failed"
            version.support_level = "unsupported"
            version.parse_error_code = "INTERRUPTED"
            version.parse_error = "服务重启导致解析中断，请重新解析"
            version.index_status = "failed"
            version.index_error_code = "INTERRUPTED"
            version.index_error = "服务重启导致索引中断，请重新解析或重建索引"
            touched.append(version.id)

            job = db.scalars(
                select(ParseJob)
                .where(ParseJob.document_version_id == version.id)
                .order_by(ParseJob.created_at.desc())
            ).first()
            if job and job.finished_at is None:
                job.status = "failed"
                job.error_code = "INTERRUPTED"
                job.error_message = version.parse_error
                from db.models import utcnow

                job.finished_at = utcnow()
        if touched:
            db.commit()
    return touched
