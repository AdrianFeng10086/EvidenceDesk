# 有据工作台后端

基于 FastAPI 的后端服务，提供文档解析、检索和 AI 工作流编排。

## 安装步骤

1. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp ../.env.example .env
# 编辑 .env 填写你的 API 密钥
```

4. 运行开发服务器：
```bash
python main.py
```

服务器将在 http://localhost:8000 启动

## API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── main.py                 # FastAPI 应用入口
├── requirements.txt        # Python 依赖
├── core/
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库连接
│   └── models.py          # Pydantic 模型
├── api/
│   ├── routes/
│   │   ├── workspace.py   # 工作空间端点
│   │   ├── document.py    # 文档上传/解析
│   │   ├── chat.py        # 聊天/运行端点 (SSE)
│   │   ├── evidence.py    # 证据检索
│   │   └── export.py      # 报告导出
│   └── dependencies.py    # 共享依赖
├── services/
│   ├── parser.py          # 文档解析 (pdfplumber)
│   ├── retrieval.py       # 向量 + 关键词搜索
│   ├── llm.py             # LLM 客户端封装
│   ├── workflow.py        # AI 工作流编排器
│   └── citation.py        # 引用验证
├── db/
│   ├── models.py          # SQLAlchemy 模型
│   └── crud.py            # 数据库操作
└── tests/
    ├── test_parser.py
    ├── test_retrieval.py
    └── test_citation.py
```

## 开发

运行测试：
```bash
pytest
```

格式化代码：
```bash
black .
isort .
```

类型检查：
```bash
mypy .
```

## 环境变量

详见 `../.env.example` 中的必需配置。

关键变量：
- `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`: 主要 LLM（DeepSeek，OpenAI 兼容接口，见 `services/llm.py`）
- `VISION_MODEL`: 视觉证据使用的模型，需支持图片输入
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare 账户 ID（向量化模型由 Workers AI 提供）
- `EMBEDDING_API_KEY`: Cloudflare API Token（需 Workers AI 权限）
- `EMBEDDING_MODEL`: 默认 `@cf/qwen/qwen3-embedding-0.6b`，1024 维
- `DATABASE_URL`: SQLite 数据库路径
- `UPLOAD_DIR`: 文件上传目录
