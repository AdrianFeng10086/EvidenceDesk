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
│       ├── cases.py           # Case 范围、检索、索引状态与日志
│       └── chat.py            # 聊天/运行端点 (SSE)
├── services/
│   ├── access.py              # 访问主体、空间/Case/版本所有权校验
│   ├── storage.py             # 暂存、哈希、不可变版本目录
│   ├── parser.py              # PDF/TXT/Markdown 解析与状态机
│   ├── chunking.py            # EvidenceSpan -> 检索块（稳定 ID + 章节上下文）
│   ├── tokenizer.py           # 中文 BM25 分词
│   ├── index_config.py        # 索引配置指纹/版本
│   ├── indexing.py            # 分块、嵌入、Chroma 与 SQLite 映射
│   ├── vector_store.py        # Chroma 集合读写
│   ├── retrieval.py           # Case 范围过滤 + 向量/BM25/RRF
│   ├── cases.py               # 范围快照、来源状态、Run 过期
│   ├── errors.py              # 业务错误与解析错误码
│   ├── llm.py                 # LLM 客户端封装
│   └── embedding.py           # Cloudflare / 本地哈希向量化
├── db/
│   └── models.py              # Workspace/Document/Version/Span/Case/Run/检索表
├── schemas/
│   ├── document.py            # 文档 API 模型
│   └── retrieval.py           # Case/检索 API 模型
├── scripts/
│   └── evaluate_retrieval.py  # 开发集召回评测
└── tests/                     # 51 个 pytest 用例与 PDF 生成器
```

## 主要接口

- `GET /api/workspaces`、`POST /api/workspaces`
- `GET|POST /api/workspaces/{id}/documents`
- `GET /api/documents/{version_id}`（详情/页面摘要/解析任务）
- `GET /api/documents/{version_id}/status`（状态轮询）
- `GET /api/documents/{version_id}/content?page=1`（原文 + EvidenceSpan + 文字框）
- `GET /api/documents/{version_id}/original`（下载原文，附 SHA-256 头）
- `POST /api/documents/{version_id}/parse/retry`（失败重试）
- `POST /api/documents/{version_id}/index/rebuild`（重建索引）
- `GET|POST /api/cases`、`GET|PATCH /api/cases/{case_id}`
- `GET|POST /api/cases/{case_id}/scope`（固定引用跨空间版本）
- `POST /api/cases/{case_id}/retrieve`（Case 级向量 + 中文 BM25 混合检索）
- `GET /api/cases/{case_id}/retrieval/index-status`、`.../retrieval/logs`、`.../runs`
- `GET /api/retrieval/logs/{log_id}`（历史来源状态标注）
- `GET /api/index/status`
- `POST /api/chat/stream`（SSE，可带 `case_id` 使用 Case 级检索）

完整说明见 `../docs/day5-implementation.md` 与 `../docs/api-spec.md`。

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
