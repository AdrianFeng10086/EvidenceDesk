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
    """建表并写入演示资料空间。"""
    from db import models  # noqa: F401 — 注册所有表

    models.Base.metadata.create_all(bind=engine)
    seed_demo_workspace()


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
