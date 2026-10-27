"""
有据工作台后端 - FastAPI 应用入口

Day 1: 基础结构和健康检查
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 应用元数据
APP_NAME = "有据工作台后端"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "文档证据校验与检索增强生成工作台"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期事件"""
    # 启动
    print(f"🚀 启动 {APP_NAME} v{APP_VERSION}")
    print(f"📁 上传目录: {os.getenv('UPLOAD_DIR', './data/uploads')}")
    print(f"💾 数据库: {os.getenv('DATABASE_URL', 'sqlite:///./data/db/evidence.db')}")

    # TODO Day 2: 初始化数据库
    # TODO Day 2: 初始化 Chroma 客户端
    # TODO Day 2: 验证 LLM/向量模型连通性

    yield

    # 关闭
    print(f"👋 关闭 {APP_NAME}")
    # TODO: 清理连接


# 创建 FastAPI 应用
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)

# 配置 CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查端点
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


# TODO Day 2: 添加路由导入和注册
# from api.routes import workspace, document, chat, evidence, export
# app.include_router(workspace.router, prefix="/api/workspaces", tags=["资料空间"])
# app.include_router(document.router, prefix="/api/documents", tags=["文档"])
# app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
# app.include_router(evidence.router, prefix="/api/evidence", tags=["证据"])
# app.include_router(export.router, prefix="/api/export", tags=["导出"])


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
