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
├── main.py                    # FastAPI 应用入口、错误处理、路由注册
├── requirements.txt
├── core/
│   ├── config.py              # 环境变量与路径解析
│   └── database.py            # SQLite 连接、建表、演示空间、中断恢复
├── api/
│   ├── serializers.py         # ORM -> API 模型
│   └── routes/
│       ├── workspaces.py      # 资料空间与所有权
│       ├── documents.py       # 上传、版本、状态、原文、下载、重试
│       └── chat.py            # 聊天/运行端点 (SSE)
├── services/
│   ├── access.py              # 访问主体与所有权校验
│   ├── storage.py             # 暂存、哈希、不可变版本目录
│   ├── parser.py              # PDF/TXT/Markdown 解析与状态机
│   ├── errors.py              # 业务错误与解析错误码
│   ├── llm.py                 # LLM 客户端封装
│   └── embedding.py           # 向量化客户端
├── db/
│   └── models.py              # Workspace/Document/Version/Page/Span/ParseJob
├── schemas/
│   └── document.py            # API 响应模型
└── tests/                     # 25 个 pytest 用例与 PDF 生成器
```

## 主要接口

- `GET /api/workspaces`、`POST /api/workspaces`
- `GET|POST /api/workspaces/{id}/documents`
- `GET /api/documents/{version_id}`（详情/页面摘要/解析任务）
- `GET /api/documents/{version_id}/status`（状态轮询）
- `GET /api/documents/{version_id}/content?page=1`（原文 + EvidenceSpan + 文字框）
- `GET /api/documents/{version_id}/original`（下载原文，附 SHA-256 头）
- `POST /api/documents/{version_id}/parse/retry`（失败重试）
- `POST /api/chat/stream`（SSE，同样校验资料空间所有权）

完整说明见 `../docs/day3-implementation.md`。

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
