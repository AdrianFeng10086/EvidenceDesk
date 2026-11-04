"""
有据工作台后端 - FastAPI 应用入口

Day 1: 基础结构和健康检查
Day 2: 流式对话
Day 3: 文档导入、不可变版本、解析状态与 EvidenceSpan
Day 5: 分块、Chroma 索引、Case 级混合检索与检索日志
"""

import os
import sys
import threading
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# 加载环境变量
load_dotenv()

from core.config import get_settings  # noqa: E402
from core.database import init_db, recover_interrupted_parses  # noqa: E402
from services.errors import AppError  # noqa: E402

settings = get_settings()

APP_NAME = settings.app_name
APP_VERSION = settings.app_version
APP_DESCRIPTION = "文档证据校验与检索增强生成工作台"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期事件"""
    print(f"🚀 启动 {APP_NAME} v{APP_VERSION}")
    print(f"📁 上传目录: {settings.upload_dir}")
    print(f"💾 数据库: {settings.database_url}")

    init_db()
    interrupted = recover_interrupted_parses()
    if interrupted:
        print(f"⚠️  {len(interrupted)} 个解析任务因上次退出而中断，已标记为失败")

    if os.getenv("INDEX_BACKFILL_ON_STARTUP", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        def _backfill() -> None:
            from services.indexing import backfill_pending_indexes

            try:
                count = backfill_pending_indexes()
                if count:
                    print(f"🧩 已补齐 {count} 个文档版本的检索索引")
            except Exception as exc:  # noqa: BLE001 — 后台补齐失败不阻断启动
                print(f"⚠️  启动索引补齐失败：{exc}")

        threading.Thread(
            target=_backfill, name="index-backfill", daemon=True
        ).start()

    yield

    print(f"👋 关闭 {APP_NAME}")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不合法",
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.get("/health")
async def health_check():
    """基础健康检查"""
    return {
        "status": "healthy",
        "service": APP_NAME,
        "version": APP_VERSION,
    }


@app.get("/")
async def root():
    """根端点"""
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


from api.routes import cases, chat, documents, workspaces  # noqa: E402

app.include_router(workspaces.router, prefix="/api", tags=["资料空间"])
app.include_router(documents.router, prefix="/api", tags=["文档"])
app.include_router(cases.router, prefix="/api", tags=["事项与检索"])
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])


if __name__ == "__main__":
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    reload = os.getenv("AUTO_RELOAD", "true").lower() == "true"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
