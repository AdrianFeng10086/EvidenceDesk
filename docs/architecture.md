# 系统架构设计

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         浏览器 / 客户端                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │  文件列表      │  │  对话与核对清单  │  │  文档阅读器     │  │
│  │  - 资料空间    │  │  - 消息          │  │  - PDF.js       │  │
│  │  - 文档        │  │  - 来源          │  │  - 高亮         │  │
│  │  - 状态        │  │  - 核对项        │  │  - 视觉框       │  │
│  └────────────────┘  └──────────────────┘  └─────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │            assistant-ui 自定义运行时 / 适配器             │  │
│  │  - SSE 流式解析                                           │  │
│  │  - 工具 UI 渲染                                           │  │
│  │  - 状态管理                                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP / SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js API 路由（代理）                     │
│  - 同源代理                                                     │
│  - 不含业务逻辑                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP / SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI 后端（Python）                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                         API 端点                          │  │
│  │  - /upload          - /chat（SSE）      - /export         │  │
│  │  - /parse-status    - /retrieve         - /checklist      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      AI 工作流编排器                      │  │
│  │  - 工具执行（检索、读取、补问、比较、更新）               │  │
│  │  - 事件发送（run_started、text_delta、tool_*）            │  │
│  │  - 参数校验与资源隔离                                     │  │
│  │  - 最大步数 / 超时 / 用量限制                             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  文档解析器 │  │  检索引擎    │  │  引用校验器            │  │
│  │  - pdfplumb │  │  - Chroma    │  │  - 引用检查            │  │
│  │  - 坐标     │  │  - BM25      │  │  - 支持性评估          │  │
│  │             │  │              │  │  - 人工覆盖            │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                        LLM 客户端                         │  │
│  │  - 结构化输出（Claim、CheckItem、VisualEvidence）         │  │
│  │  - 工具调用                                               │  │
│  │  - 视觉输入                                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐
         │  SQLite  │  │  Chroma  │  │   文件   │
         │  元数据  │  │   向量   │  │ /uploads │
         └──────────┘  └──────────┘  └──────────┘
```

## 二、数据模型

### 核心实体关系

```python
# Workspace / Case：资料空间与决策事项
class Workspace:
    id: str
    name: str
    description: str
    owner_id: str  # 访问控制
    created_at: datetime
    updated_at: datetime

# DocumentVersion：文件版本
class DocumentVersion:
    id: str
    workspace_id: str
    file_name: str
    file_hash: str  # SHA256
    file_size: int
    file_path: str
    version: int
    upload_source: str
    applicable_scope: Optional[str]  # 适用范围
    upload_at: datetime
    parse_status: str  # pending, parsing, success, failed
    parse_error: Optional[str]

# EvidenceSpan：文本证据片段
class EvidenceSpan:
    id: str
    document_version_id: str
    page: int
    text: str
    char_start: int
    char_end: int
    bboxes: List[BBox]  # 一个或多个矩形 [x0, y0, x1, y1]
    context_before: Optional[str]
    context_after: Optional[str]
    created_at: datetime

class BBox:
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float

# VisualEvidence：视觉证据框
class VisualEvidence:
    id: str
    image_id: str
    document_version_id: str
    page: int
    image_width: int
    image_height: int
    image_hash: str
    boxes: List[VisualBox]
    model_name: str
    validation_status: str  # validated, out_of_bounds, page_mismatch
    created_at: datetime

class VisualBox:
    id: str
    x: float  # 归一化 0-1
    y: float
    width: float
    height: float
    description: str
    supports_claim_ids: List[str]

# Claim：结论
class Claim:
    id: str
    run_id: str
    text: str
    evidence_span_ids: List[str]
    visual_evidence_ids: List[str]
    support_status: str  # supported, partial, not_found, needs_human
    support_reason: Optional[str]
    human_override: Optional[bool]
    created_at: datetime

# Fact：用户事实
class Fact:
    id: str
    workspace_id: str
    key: str
    value: str
    source: str  # user_input, document_extracted, clarified
    confirmed: bool
    updated_at: datetime

# CheckItem：核对清单项
class CheckItem:
    id: str
    workspace_id: str
    requirement: str
    premise: Optional[str]
    required_facts: List[str]
    evidence_span_ids: List[str]
    status: str  # met, not_met, insufficient_info, needs_human
    human_confirmed: Optional[bool]
    created_at: datetime

# Run：执行记录
class Run:
    id: str
    workspace_id: str
    query: str
    model_name: str
    retrieval_params: dict
    tool_events: List[ToolEvent]
    claims: List[Claim]
    duration_ms: int
    tokens_used: int
    cost_estimate: float
    created_at: datetime

class ToolEvent:
    tool_name: str
    arguments: dict
    result: dict
    duration_ms: int
    timestamp: datetime
```

### 数据库表设计（SQLite）

```sql
-- workspaces
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- document_versions
CREATE TABLE document_versions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    version INTEGER NOT NULL,
    upload_source TEXT,
    applicable_scope TEXT,
    upload_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parse_status TEXT NOT NULL,
    parse_error TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- evidence_spans
CREATE TABLE evidence_spans (
    id TEXT PRIMARY KEY,
    document_version_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    bboxes JSON NOT NULL,
    context_before TEXT,
    context_after TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_version_id) REFERENCES document_versions(id)
);

-- visual_evidences
CREATE TABLE visual_evidences (
    id TEXT PRIMARY KEY,
    image_id TEXT NOT NULL,
    document_version_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    image_width INTEGER NOT NULL,
    image_height INTEGER NOT NULL,
    image_hash TEXT NOT NULL,
    boxes JSON NOT NULL,
    model_name TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_version_id) REFERENCES document_versions(id)
);

-- claims
CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    text TEXT NOT NULL,
    evidence_span_ids JSON NOT NULL,
    visual_evidence_ids JSON NOT NULL,
    support_status TEXT NOT NULL,
    support_reason TEXT,
    human_override BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- facts
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- check_items
CREATE TABLE check_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    requirement TEXT NOT NULL,
    premise TEXT,
    required_facts JSON NOT NULL,
    evidence_span_ids JSON NOT NULL,
    status TEXT NOT NULL,
    human_confirmed BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- runs
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    query TEXT NOT NULL,
    model_name TEXT NOT NULL,
    retrieval_params JSON NOT NULL,
    tool_events JSON NOT NULL,
    claims JSON NOT NULL,
    duration_ms INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL,
    cost_estimate REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

## 三、流式事件协议

### 事件类型

```typescript
// SSE 事件格式
type StreamEvent =
  | RunStartedEvent
  | TextDeltaEvent
  | ToolStartedEvent
  | ToolFinishedEvent
  | ClaimReadyEvent
  | VisualEvidenceReadyEvent
  | ClarificationRequiredEvent
  | RunFinishedEvent
  | ErrorEvent;

interface RunStartedEvent {
  type: 'run_started';
  run_id: string;
  model: string;
  timestamp: string;
}

interface TextDeltaEvent {
  type: 'text_delta';
  delta: string;
  timestamp: string;
}

interface ToolStartedEvent {
  type: 'tool_started';
  tool_name: string;
  arguments: Record<string, any>;
  timestamp: string;
}

interface ToolFinishedEvent {
  type: 'tool_finished';
  tool_name: string;
  result: Record<string, any>;
  duration_ms: number;
  timestamp: string;
}

interface ClaimReadyEvent {
  type: 'claim_ready';
  claim: {
    id: string;
    text: string;
    evidence_span_ids: string[];
    validation_status: 'pending' | 'validated' | 'invalid';
  };
  timestamp: string;
}

interface VisualEvidenceReadyEvent {
  type: 'visual_evidence_ready';
  visual_evidence: {
    id: string;
    image_id: string;
    page: number;
    boxes: Array<{
      id: string;
      x: number;
      y: number;
      width: number;
      height: number;
      description: string;
      supports_claim_ids: string[];
    }>;
    validation_status: string;
  };
  timestamp: string;
}

interface ClarificationRequiredEvent {
  type: 'clarification_required';
  question: string;
  fact_key: string;
  reason: string;
  timestamp: string;
}

interface RunFinishedEvent {
  type: 'run_finished';
  run_id: string;
  summary: {
    claims_count: number;
    evidence_spans_count: number;
    visual_evidences_count: number;
    clarifications_count: number;
  };
  timestamp: string;
}

interface ErrorEvent {
  type: 'error';
  error_code: string;
  message: string;
  recoverable: boolean;
  timestamp: string;
}
```

### SSE 格式示例

```
event: run_started
data: {"type":"run_started","run_id":"run_123","model":"deepseek-flash","timestamp":"2024-10-22T20:00:00Z"}

event: text_delta
data: {"type":"text_delta","delta":"根据提供的文档，","timestamp":"2024-10-22T20:00:01Z"}

event: tool_started
data: {"type":"tool_started","tool_name":"search_evidence","arguments":{"query":"项目申报截止时间","workspace_id":"ws_001"},"timestamp":"2024-10-22T20:00:02Z"}

event: tool_finished
data: {"type":"tool_finished","tool_name":"search_evidence","result":{"evidence_ids":["ev_001","ev_002"]},"duration_ms":450,"timestamp":"2024-10-22T20:00:02Z"}

event: claim_ready
data: {"type":"claim_ready","claim":{"id":"claim_001","text":"申报截止时间为2024年11月15日","evidence_span_ids":["ev_001"],"validation_status":"pending"},"timestamp":"2024-10-22T20:00:03Z"}

event: run_finished
data: {"type":"run_finished","run_id":"run_123","summary":{"claims_count":3,"evidence_spans_count":5,"visual_evidences_count":0,"clarifications_count":1},"timestamp":"2024-10-22T20:00:10Z"}
```

## 四、工具定义

### 核心工具集

```python
tools = [
    {
        "name": "search_evidence",
        "description": "在资料空间中检索相关证据片段",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "workspace_id": {"type": "string"},
                "document_ids": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "default": 5}
            },
            "required": ["query", "workspace_id"]
        }
    },
    {
        "name": "read_span",
        "description": "读取证据片段的完整上下文",
        "parameters": {
            "type": "object",
            "properties": {
                "evidence_span_id": {"type": "string"},
                "context_pages": {"type": "integer", "default": 0}
            },
            "required": ["evidence_span_id"]
        }
    },
    {
        "name": "request_fact",
        "description": "向用户请求缺失的关键事实",
        "parameters": {
            "type": "object",
            "properties": {
                "fact_key": {"type": "string"},
                "question": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["fact_key", "question", "reason"]
        }
    },
    {
        "name": "compare_requirements",
        "description": "比较两处条款或要求的差异",
        "parameters": {
            "type": "object",
            "properties": {
                "evidence_span_id_a": {"type": "string"},
                "evidence_span_id_b": {"type": "string"},
                "comparison_aspect": {"type": "string"}
            },
            "required": ["evidence_span_id_a", "evidence_span_id_b"]
        }
    },
    {
        "name": "update_checklist",
        "description": "更新条件核对清单",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "check_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "requirement": {"type": "string"},
                            "premise": {"type": "string"},
                            "required_facts": {"type": "array"},
                            "evidence_span_ids": {"type": "array"},
                            "status": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["workspace_id", "check_items"]
        }
    },
    {
        "name": "analyze_visual_evidence",
        "description": "分析页面图像并返回视觉证据框",
        "parameters": {
            "type": "object",
            "properties": {
                "image_id": {"type": "string"},
                "page": {"type": "integer"},
                "claim_ids": {"type": "array", "items": {"type": "string"}},
                "focus_description": {"type": "string"}
            },
            "required": ["image_id", "page", "claim_ids"]
        }
    }
]
```

## 五、视觉证据坐标系统

### 文本证据（红色实线）

```python
# 由 pdfplumber 解析生成，坐标系：页面左上角为原点
class TextEvidenceBBox:
    x0: float  # 左边界，单位 pt
    y0: float  # 上边界，单位 pt
    x1: float  # 右边界，单位 pt
    y1: float  # 下边界，单位 pt
    page_width: float   # 页面宽度，单位 pt
    page_height: float  # 页面高度，单位 pt
    page: int
  
# 前端渲染：PDF.js viewport 转换
const scale = viewport.scale;
const [x0_px, y0_px] = viewport.convertToViewportPoint(bbox.x0, bbox.y0);
const [x1_px, y1_px] = viewport.convertToViewportPoint(bbox.x1, bbox.y1);

// 显示红色实线矩形
<div style={{
  position: 'absolute',
  left: x0_px,
  top: y0_px,
  width: x1_px - x0_px,
  height: y1_px - y0_px,
  border: '2px solid #EF4444',  // 红色实线
  pointerEvents: 'none'
}} />
```

### 视觉证据（红色虚线）

```python
# 由视觉模型生成，坐标系：图像左上角为原点，归一化 0-1
class VisualEvidenceBox:
    x: float       # 左上角 x，范围 [0, 1]
    y: float       # 左上角 y，范围 [0, 1]
    width: float   # 宽度，范围 [0, 1]
    height: float  # 高度，范围 [0, 1]
    image_id: str
    image_width: int   # 图像实际宽度 px
    image_height: int  # 图像实际高度 px
    page: int
  
# 坐标校验（后端）
def validate_visual_box(box: VisualEvidenceBox) -> bool:
    if not (0 <= box.x <= 1 and 0 <= box.y <= 1):
        return False
    if not (0 < box.width <= 1 and 0 < box.height <= 1):
        return False
    if box.x + box.width > 1 or box.y + box.height > 1:
        return False
    return True

# 前端渲染：根据当前显示尺寸计算像素坐标
const currentWidth = canvasRef.current.width;
const currentHeight = canvasRef.current.height;

const x_px = box.x * currentWidth;
const y_px = box.y * currentHeight;
const width_px = box.width * currentWidth;
const height_px = box.height * currentHeight;

// 显示红色虚线矩形
<div style={{
  position: 'absolute',
  left: x_px,
  top: y_px,
  width: width_px,
  height: height_px,
  border: '2px dashed #EF4444',  // 红色虚线
  pointerEvents: 'none'
}} />
```

### 坐标系统对比

| 维度     | 文本证据（实线）                | 视觉证据（虚线） |
| -------- | ------------------------------- | ---------------- |
| 来源     | pdfplumber 解析                 | 视觉模型推断     |
| 坐标系   | PDF 点坐标 (pt)                 | 归一化 0-1       |
| 原点     | 页面左上角                      | 图像左上角       |
| 精度     | 精确到字符框                    | 近似区域         |
| 校验     | 文档位置映射                    | 范围与尺寸检查   |
| 前端转换 | viewport.convertToViewportPoint | 乘以当前显示尺寸 |
| 显示样式 | 红色实线                        | 红色虚线         |

## 六、部署架构

### 开发环境

```
前端：http://localhost:3000（Next.js 开发服务器）
后端：http://localhost:8000（FastAPI uvicorn）
```

### 生产环境

```
┌────────────────────────────────────────┐
│             Nginx / Caddy              │
│  - SSL 终止                            │
│  - 静态资源                            │
│  - 反向代理                            │
└────────────────────────────────────────┘
            │                │
            ▼                ▼
     ┌─────────────┐  ┌──────────────┐
     │   Next.js   │  │   FastAPI    │
     │  (SSR/SSG)  │  │  (Gunicorn)  │
     └─────────────┘  └──────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  SQLite  │     │  Chroma  │     │  /data   │
  │  元数据  │     │   向量   │     │ 上传目录 │
  └──────────┘     └──────────┘     └──────────┘
       │                 │                 │
       └─────────────────┴─────────────────┘
                      │
              持久化存储卷
```

### 持久化存储

```
/data/
├── db/
│   └── evidence.db          # SQLite 数据库
├── chroma/
│   └── workspace_*/         # 向量索引（按空间隔离）
└── uploads/
    └── workspace_*/         # 上传文件（按空间隔离）
        └── document_*/
            ├── original.pdf
            ├── metadata.json
            └── pages/
                ├── page_001.png
                └── page_002.png
```

## 七、安全与隔离

### 访问控制

1. **资料空间隔离**：每个 workspace 有独立 owner_id
2. **文档版本追溯**：所有证据关联 document_version_id
3. **检索范围限制**：查询前验证 workspace_id
4. **API 密钥**：密钥只存在服务端，前端不可见
5. **评审账号**：演示账号只能访问公开样例

### 资源限制

```python
# 单个资料空间限制
MAX_DOCUMENTS_PER_WORKSPACE = 10
MAX_PDF_PAGES = 30
MAX_PDF_SIZE_MB = 10
MAX_UPLOAD_SIZE_MB = 50

# 单次请求限制
MAX_RETRIEVAL_RESULTS = 20
MAX_TOOL_CALLS_PER_RUN = 15
MAX_RUN_DURATION_SECONDS = 120

# 并发限制
MAX_CONCURRENT_PARSES = 3
MAX_CONCURRENT_RUNS_PER_USER = 2
```

### 错误处理

```python
# 文档解析错误
- ENCRYPTED: 加密文件，无法解析
- CORRUPTED: 文件损坏
- NO_TEXT_LAYER: 无文字层，需 OCR（首版不支持）
- TOO_LARGE: 超过大小限制
- UNSUPPORTED_FORMAT: 不支持的格式

# 引用错误
- EVIDENCE_NOT_FOUND: 引用 ID 不存在
- VERSION_MISMATCH: 文档版本不匹配
- TEXT_MISMATCH: 摘录与原文不一致
- BBOX_OUT_OF_BOUNDS: 坐标越界

# 运行时错误
- TIMEOUT: 执行超时
- RATE_LIMIT: 模型速率限制
- INSUFFICIENT_QUOTA: 额度不足
- TOOL_EXECUTION_FAILED: 工具执行失败
```

## 八、监控与日志

### 关键指标

```python
# 性能指标
- 文档解析耗时与成功率
- 检索召回延迟 (p50, p95, p99)
- 端到端问答延迟
- SSE 流式首字延迟

# 质量指标
- 引用完整性通过率
- 支持性检查准确率
- 用户纠正次数
- 清单项人工确认比例

# 成本指标
- 模型 token 消耗
- API 调用次数与费用
- 存储空间占用
```

### 日志结构

```python
{
  "timestamp": "2024-10-22T20:00:00Z",
  "level": "INFO",
  "event": "document_parsed",
  "workspace_id": "ws_001",
  "document_id": "doc_001",
  "pages": 15,
  "evidence_spans": 342,
  "duration_ms": 2450
}

{
  "timestamp": "2024-10-22T20:05:00Z",
  "level": "WARN",
  "event": "citation_validation_failed",
  "run_id": "run_123",
  "claim_id": "claim_002",
  "error": "TEXT_MISMATCH",
  "expected": "申报截止时间为11月15日",
  "actual": "申报截止日期为11月30日"
}
```

## 九、技术选型理由

| 技术         | 选择理由                        | 替代方案          |
| ------------ | ------------------------------- | ----------------- |
| Next.js      | React 生态、SSR/SSG、API Routes | Vite + React      |
| FastAPI      | 异步、类型提示、自动文档        | Flask, Django     |
| pdfplumber   | 文本+坐标、Python 生态          | PyMuPDF, pdfminer |
| PDF.js       | 浏览器原生、Mozilla 维护        | react-pdf         |
| Chroma       | 轻量、持久化、Python 友好       | Qdrant, Weaviate  |
| SQLite       | 单文件、零配置、嵌入式          | PostgreSQL, MySQL |
| assistant-ui | 流式 UI、Tool UI、可定制        | 自建 SSE 组件     |

## 十、扩展性考虑

### 后续可扩展点

1. **文档类型**：Word、Excel、网页、邮件
2. **OCR 能力**：Tesseract、云 OCR API
3. **检索增强**：Reranker、查询改写、多路召回融合
4. **协作功能**：评论、批注、审批流
5. **权限体系**：角色、团队、企业级权限
6. **多租户**：workspace → organization → team 层级
7. **API 开放**：Webhook、第三方集成
8. **离线能力**：本地模型、边缘部署

### 不破坏现有设计的扩展原则

- 新增 document_type 字段，保持 EvidenceSpan 统一接口
- 新增 parse_strategy 字段，不同类型文档使用不同解析器
- 检索保持 retrieve(query, workspace_id, filters) 接口
- 前端通过 viewer_type 决定渲染器（PDF/Text/HTML）
- 所有坐标保留原始单位与转换参数
