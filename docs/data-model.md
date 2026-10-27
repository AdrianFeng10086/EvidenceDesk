# 数据模型详细设计

## 一、模型层级关系

```
Workspace (资料空间)
  ├── DocumentVersion (文档版本)
  │     └── EvidenceSpan (文本证据片段)
  │     └── VisualEvidence (视觉证据)
  ├── Fact (用户事实)
  ├── CheckItem (核对清单项)
  └── Run (执行记录)
        └── Claim (结论)
              ├── → EvidenceSpan (关联)
              └── → VisualEvidence (关联)
```

## 二、Pydantic 模型定义

### Workspace

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class Workspace(BaseModel):
    id: str = Field(..., description="资料空间唯一标识")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    owner_id: str = Field(..., description="所有者 ID，用于访问控制")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "ws_abc123",
                "name": "2024年科研项目申报",
                "description": "校级重点项目申报资料包",
                "owner_id": "user_001",
                "created_at": "2024-10-22T10:00:00Z",
                "updated_at": "2024-10-22T10:00:00Z"
            }
        }
```

### DocumentVersion

```python
from enum import Enum

class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    SUCCESS = "success"
    FAILED = "failed"

class DocumentVersion(BaseModel):
    id: str
    workspace_id: str
    file_name: str
    file_hash: str = Field(..., description="SHA256 哈希，用于版本去重")
    file_size: int = Field(..., gt=0, description="文件大小（字节）")
    file_path: str = Field(..., description="存储路径")
    version: int = Field(..., ge=1, description="同一文件的版本号")
    upload_source: Optional[str] = Field(None, description="上传来源标注")
    applicable_scope: Optional[str] = Field(None, description="适用范围，如"2024年度"")
    upload_at: datetime = Field(default_factory=datetime.now)
    parse_status: ParseStatus = ParseStatus.PENDING
    parse_error: Optional[str] = None
    page_count: Optional[int] = Field(None, ge=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc_xyz789",
                "workspace_id": "ws_abc123",
                "file_name": "科研项目申报指南2024.pdf",
                "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "file_size": 2456789,
                "file_path": "/data/uploads/ws_abc123/doc_xyz789/original.pdf",
                "version": 1,
                "upload_source": "官网下载",
                "applicable_scope": "2024年度",
                "upload_at": "2024-10-22T10:05:00Z",
                "parse_status": "success",
                "page_count": 15
            }
        }
```

### EvidenceSpan

```python
from typing import List

class BBox(BaseModel):
    x0: float = Field(..., description="左边界，PDF 点坐标")
    y0: float = Field(..., description="上边界，PDF 点坐标")
    x1: float = Field(..., description="右边界，PDF 点坐标")
    y1: float = Field(..., description="下边界，PDF 点坐标")
    page_width: float = Field(..., gt=0, description="页面宽度")
    page_height: float = Field(..., gt=0, description="页面高度")

class EvidenceSpan(BaseModel):
    id: str
    document_version_id: str
    page: int = Field(..., ge=1, description="页码，从 1 开始")
    text: str = Field(..., min_length=1, description="证据文本")
    char_start: int = Field(..., ge=0, description="字符起始位置")
    char_end: int = Field(..., gt=0, description="字符结束位置")
    bboxes: List[BBox] = Field(..., min_items=1, description="一个或多个矩形框")
    context_before: Optional[str] = Field(None, max_length=500)
    context_after: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "ev_span_001",
                "document_version_id": "doc_xyz789",
                "page": 3,
                "text": "申报截止时间为2024年11月15日",
                "char_start": 142,
                "char_end": 159,
                "bboxes": [{
                    "x0": 72.0,
                    "y0": 156.5,
                    "x1": 268.3,
                    "y1": 170.2,
                    "page_width": 595.0,
                    "page_height": 842.0
                }],
                "context_before": "请各单位认真组织申报工作。",
                "context_after": "逾期不予受理。"
            }
        }
```

### VisualEvidence

```python
class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    OUT_OF_BOUNDS = "out_of_bounds"
    PAGE_MISMATCH = "page_mismatch"
    IMAGE_NOT_FOUND = "image_not_found"

class VisualBox(BaseModel):
    id: str
    x: float = Field(..., ge=0, le=1, description="归一化左上角 x")
    y: float = Field(..., ge=0, le=1, description="归一化左上角 y")
    width: float = Field(..., gt=0, le=1, description="归一化宽度")
    height: float = Field(..., gt=0, le=1, description="归一化高度")
    description: str = Field(..., min_length=1, max_length=200)
    supports_claim_ids: List[str] = Field(default_factory=list)

class VisualEvidence(BaseModel):
    id: str
    image_id: str = Field(..., description="页面图像标识")
    document_version_id: str
    page: int = Field(..., ge=1)
    image_width: int = Field(..., gt=0, description="图像宽度（像素）")
    image_height: int = Field(..., gt=0, description="图像高度（像素）")
    image_hash: str = Field(..., description="图像内容哈希")
    boxes: List[VisualBox] = Field(..., min_items=1)
    model_name: str = Field(..., description="使用的视觉模型")
    validation_status: ValidationStatus = ValidationStatus.VALIDATED
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "vis_ev_001",
                "image_id": "page-03-render-1",
                "document_version_id": "doc_xyz789",
                "page": 3,
                "image_width": 1600,
                "image_height": 2200,
                "image_hash": "a3f5e...",
                "boxes": [{
                    "id": "visual-1",
                    "x": 0.18,
                    "y": 0.42,
                    "width": 0.31,
                    "height": 0.08,
                    "description": "表格中说明申报截止时间的行",
                    "supports_claim_ids": ["claim_002"]
                }],
                "model_name": "deepseek-flash",
                "validation_status": "validated"
            }
        }
```

### Claim

```python
class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    NEEDS_HUMAN = "needs_human"

class Claim(BaseModel):
    id: str
    run_id: str
    text: str = Field(..., min_length=1, max_length=1000)
    evidence_span_ids: List[str] = Field(default_factory=list)
    visual_evidence_ids: List[str] = Field(default_factory=list)
    support_status: SupportStatus = SupportStatus.NEEDS_HUMAN
    support_reason: Optional[str] = Field(None, max_length=500)
    human_override: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "claim_002",
                "run_id": "run_123",
                "text": "申报截止时间为2024年11月15日",
                "evidence_span_ids": ["ev_span_001"],
                "visual_evidence_ids": ["vis_ev_001"],
                "support_status": "supported",
                "support_reason": "原文明确陈述了截止日期",
                "human_override": None
            }
        }
```

### Fact

```python
class FactSource(str, Enum):
    USER_INPUT = "user_input"
    DOCUMENT_EXTRACTED = "document_extracted"
    CLARIFIED = "clarified"

class Fact(BaseModel):
    id: str
    workspace_id: str
    key: str = Field(..., min_length=1, max_length=100, description="事实键，如 'applicant_role'")
    value: str = Field(..., min_length=1, max_length=500)
    source: FactSource
    confirmed: bool = False
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "fact_001",
                "workspace_id": "ws_abc123",
                "key": "applicant_role",
                "value": "副教授",
                "source": "user_input",
                "confirmed": True,
                "updated_at": "2024-10-22T10:15:00Z"
            }
        }
```

### CheckItem

```python
class CheckStatus(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    INSUFFICIENT_INFO = "insufficient_info"
    NEEDS_HUMAN = "needs_human"

class CheckItem(BaseModel):
    id: str
    workspace_id: str
    requirement: str = Field(..., min_length=1, max_length=500)
    premise: Optional[str] = Field(None, max_length=500, description="前提条件或适用范围")
    required_facts: List[str] = Field(default_factory=list, description="依赖的事实键")
    evidence_span_ids: List[str] = Field(default_factory=list, description="规则来源")
    status: CheckStatus = CheckStatus.INSUFFICIENT_INFO
    human_confirmed: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "check_001",
                "workspace_id": "ws_abc123",
                "requirement": "申请人须为副教授及以上职称",
                "premise": "适用于重点项目",
                "required_facts": ["applicant_role", "project_type"],
                "evidence_span_ids": ["ev_span_005"],
                "status": "met",
                "human_confirmed": True
            }
        }
```

### Run & ToolEvent

```python
class ToolEvent(BaseModel):
    tool_name: str
    arguments: dict
    result: dict
    duration_ms: int = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.now)

class Run(BaseModel):
    id: str
    workspace_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    model_name: str
    retrieval_params: dict = Field(default_factory=dict)
    tool_events: List[ToolEvent] = Field(default_factory=list)
    claims: List[str] = Field(default_factory=list, description="Claim IDs")
    duration_ms: int = Field(..., ge=0)
    tokens_used: int = Field(..., ge=0)
    cost_estimate: float = Field(..., ge=0)
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "run_123",
                "workspace_id": "ws_abc123",
                "query": "我是否满足重点项目申报条件？",
                "model_name": "deepseek-flash",
                "retrieval_params": {"top_k": 5, "strategy": "hybrid"},
                "tool_events": [
                    {
                        "tool_name": "search_evidence",
                        "arguments": {"query": "重点项目申报条件"},
                        "result": {"evidence_ids": ["ev_span_005", "ev_span_006"]},
                        "duration_ms": 450,
                        "timestamp": "2024-10-22T10:20:01Z"
                    }
                ],
                "claims": ["claim_001", "claim_002"],
                "duration_ms": 8540,
                "tokens_used": 1523,
                "cost_estimate": 0.0456
            }
        }
```

## 三、结构化输出 Schema

### AnswerWithEvidence 工具

```python
class ClaimSchema(BaseModel):
    """模型返回的单条结论"""
    text: str = Field(..., description="结论陈述，尽量精确")
    evidence_span_ids: List[str] = Field(
        ..., 
        description="支持该结论的证据片段 ID，必须是检索返回的真实 ID"
    )
    confidence: Optional[str] = Field(
        None, 
        description="仅当原文有明确限定词时填写，如'仅适用于重点项目'"
    )

class AnswerWithEvidenceOutput(BaseModel):
    """answer_with_evidence 工具返回值"""
    claims: List[ClaimSchema] = Field(..., min_items=1)
    has_insufficient_evidence: bool = Field(
        False, 
        description="是否有问题因证据不足无法回答"
    )
    
answer_with_evidence_tool = {
    "name": "answer_with_evidence",
    "description": "返回逐条带证据的回答",
    "parameters": AnswerWithEvidenceOutput.model_json_schema()
}
```

### UpdateChecklist 工具

```python
class CheckItemInput(BaseModel):
    requirement: str
    premise: Optional[str] = None
    required_facts: List[str]
    evidence_span_ids: List[str]
    status: CheckStatus

class UpdateChecklistInput(BaseModel):
    workspace_id: str
    check_items: List[CheckItemInput]
    
update_checklist_tool = {
    "name": "update_checklist",
    "description": "更新条件核对清单",
    "parameters": UpdateChecklistInput.model_json_schema()
}
```

### RequestFact 工具

```python
class RequestFactInput(BaseModel):
    fact_key: str = Field(..., description="事实键，用于后续引用")
    question: str = Field(..., description="向用户提出的问题")
    reason: str = Field(..., description="为什么需要这个信息")
    
request_fact_tool = {
    "name": "request_fact",
    "description": "向用户请求缺失的关键事实",
    "parameters": RequestFactInput.model_json_schema()
}
```

### AnalyzeVisualEvidence 工具

```python
class VisualBoxInput(BaseModel):
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)
    description: str
    supports_claim_ids: List[str]

class AnalyzeVisualEvidenceOutput(BaseModel):
    image_id: str
    page: int
    image_width: int
    image_height: int
    boxes: List[VisualBoxInput]
    
analyze_visual_evidence_tool = {
    "name": "analyze_visual_evidence",
    "description": "分析页面图像并返回视觉证据框",
    "parameters": AnalyzeVisualEvidenceOutput.model_json_schema()
}
```

## 四、数据流转示例

### 场景：用户提问 "我是否满足重点项目申报条件？"

#### 1. 检索阶段
```python
# 输入
query = "重点项目申报条件"
workspace_id = "ws_abc123"

# 检索返回
retrieval_result = {
    "evidence_spans": [
        {
            "id": "ev_span_005",
            "text": "重点项目申请人须为副教授及以上职称",
            "page": 2,
            "document_version_id": "doc_xyz789"
        },
        {
            "id": "ev_span_006",
            "text": "申请人近三年需有省级及以上科研项目",
            "page": 3,
            "document_version_id": "doc_xyz789"
        }
    ]
}
```

#### 2. 工具调用阶段
```python
# AI 决定需要用户事实
tool_call_1 = {
    "name": "request_fact",
    "arguments": {
        "fact_key": "applicant_role",
        "question": "请问您的职称是什么？",
        "reason": "需要核对是否满足'副教授及以上职称'要求"
    }
}

tool_call_2 = {
    "name": "request_fact",
    "arguments": {
        "fact_key": "recent_projects",
        "question": "请问您近三年是否有省级及以上科研项目？",
        "reason": "需要核对项目经历要求"
    }
}

# 用户回复
fact_1 = {
    "key": "applicant_role",
    "value": "副教授",
    "source": "clarified",
    "confirmed": True
}

fact_2 = {
    "key": "recent_projects",
    "value": "有，2023年省社科基金项目",
    "source": "clarified",
    "confirmed": True
}
```

#### 3. 清单生成阶段
```python
tool_call_3 = {
    "name": "update_checklist",
    "arguments": {
        "workspace_id": "ws_abc123",
        "check_items": [
            {
                "requirement": "申请人须为副教授及以上职称",
                "premise": "适用于重点项目",
                "required_facts": ["applicant_role"],
                "evidence_span_ids": ["ev_span_005"],
                "status": "met"
            },
            {
                "requirement": "近三年需有省级及以上科研项目",
                "premise": None,
                "required_facts": ["recent_projects"],
                "evidence_span_ids": ["ev_span_006"],
                "status": "met"
            }
        ]
    }
}
```

#### 4. 结论生成阶段
```python
tool_call_4 = {
    "name": "answer_with_evidence",
    "arguments": {
        "claims": [
            {
                "text": "您的副教授职称满足重点项目申报要求",
                "evidence_span_ids": ["ev_span_005"],
                "confidence": "仅适用于重点项目"
            },
            {
                "text": "您的省级科研项目经历符合近三年项目要求",
                "evidence_span_ids": ["ev_span_006"],
                "confidence": None
            }
        ],
        "has_insufficient_evidence": False
    }
}
```

#### 5. 最终存储
```python
# Run 记录
run = Run(
    id="run_123",
    workspace_id="ws_abc123",
    query="我是否满足重点项目申报条件？",
    model_name="deepseek-flash",
    tool_events=[...],  # 上述 4 个 tool_call
    claims=["claim_001", "claim_002"],
    duration_ms=8540,
    tokens_used=1523,
    cost_estimate=0.0456
)

# Claim 记录
claim_1 = Claim(
    id="claim_001",
    run_id="run_123",
    text="您的副教授职称满足重点项目申报要求",
    evidence_span_ids=["ev_span_005"],
    support_status="supported",
    support_reason="原文明确陈述要求，用户事实匹配"
)

# CheckItem 记录
check_1 = CheckItem(
    id="check_001",
    workspace_id="ws_abc123",
    requirement="申请人须为副教授及以上职称",
    premise="适用于重点项目",
    required_facts=["applicant_role"],
    evidence_span_ids=["ev_span_005"],
    status="met",
    human_confirmed=None  # 待用户确认
)
```

## 五、数据校验规则

### 引用完整性校验

```python
def validate_citation(claim: Claim, evidence_spans: List[EvidenceSpan]) -> dict:
    """校验引用完整性"""
    errors = []
    
    for ev_id in claim.evidence_span_ids:
        # 1. 检查 ID 是否存在
        evidence = next((e for e in evidence_spans if e.id == ev_id), None)
        if not evidence:
            errors.append(f"证据 {ev_id} 不存在")
            continue
        
        # 2. 检查文档版本是否可用
        if not is_document_version_available(evidence.document_version_id):
            errors.append(f"证据 {ev_id} 的文档版本不可用")
        
        # 3. 检查摘录是否与原文一致（如果 claim 中引用了摘录）
        if has_quoted_text(claim.text) and not text_matches(claim.text, evidence.text):
            errors.append(f"证据 {ev_id} 摘录与原文不一致")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
```

### 坐标校验

```python
def validate_visual_box(box: VisualBox, image_width: int, image_height: int) -> dict:
    """校验视觉证据框坐标"""
    errors = []
    
    # 1. 归一化坐标范围检查
    if not (0 <= box.x <= 1 and 0 <= box.y <= 1):
        errors.append("坐标 x, y 必须在 [0, 1] 范围内")
    
    # 2. 宽高检查
    if not (0 < box.width <= 1 and 0 < box.height <= 1):
        errors.append("宽高必须大于 0 且不超过 1")
    
    # 3. 越界检查
    if box.x + box.width > 1.01:  # 允许 1% 容差
        errors.append("框右边界越界")
    if box.y + box.height > 1.01:
        errors.append("框下边界越界")
    
    # 4. 最小尺寸检查（避免无意义的微小框）
    min_pixel_size = 10
    if box.width * image_width < min_pixel_size or box.height * image_height < min_pixel_size:
        errors.append("框尺寸过小")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
```

### 资料空间隔离校验

```python
def validate_workspace_isolation(
    current_workspace_id: str,
    evidence_span_ids: List[str],
    db_session
) -> bool:
    """校验所有证据都属于当前资料空间"""
    for ev_id in evidence_span_ids:
        evidence = db_session.query(EvidenceSpan).filter_by(id=ev_id).first()
        if not evidence:
            return False
        
        doc_version = db_session.query(DocumentVersion).filter_by(
            id=evidence.document_version_id
        ).first()
        if not doc_version or doc_version.workspace_id != current_workspace_id:
            return False
    
    return True
```

## 六、索引设计

### SQLite 索引

```sql
-- 文档版本按空间查询
CREATE INDEX idx_document_versions_workspace ON document_versions(workspace_id);
CREATE INDEX idx_document_versions_hash ON document_versions(file_hash);

-- 证据片段按文档查询
CREATE INDEX idx_evidence_spans_document ON evidence_spans(document_version_id);
CREATE INDEX idx_evidence_spans_page ON evidence_spans(document_version_id, page);

-- 事实按空间和键查询
CREATE INDEX idx_facts_workspace ON facts(workspace_id);
CREATE INDEX idx_facts_key ON facts(workspace_id, key);

-- 清单按空间查询
CREATE INDEX idx_check_items_workspace ON check_items(workspace_id);

-- 运行记录按空间和时间查询
CREATE INDEX idx_runs_workspace ON runs(workspace_id);
CREATE INDEX idx_runs_created ON runs(created_at DESC);

-- Claim 按运行查询
CREATE INDEX idx_claims_run ON claims(run_id);
```

### Chroma 集合设计

```python
# 每个资料空间一个独立集合
collection_name = f"workspace_{workspace_id}"

# Metadata 过滤字段
metadata_schema = {
    "document_version_id": str,  # 按文档过滤
    "page": int,                 # 按页码过滤
    "upload_source": str,        # 按来源过滤
    "applicable_scope": str,     # 按适用范围过滤
    "chunk_type": str            # "paragraph", "sentence", "table"
}

# 插入示例
collection.add(
    documents=[span.text for span in evidence_spans],
    metadatas=[
        {
            "document_version_id": span.document_version_id,
            "page": span.page,
            "evidence_span_id": span.id
        }
        for span in evidence_spans
    ],
    ids=[span.id for span in evidence_spans]
)

# 查询示例
results = collection.query(
    query_texts=["项目申报条件"],
    n_results=5,
    where={"document_version_id": "doc_xyz789"}  # 仅在指定文档中检索
)
```

## 七、数据迁移与版本管理

### 数据库迁移策略

```python
# 使用 Alembic 进行迁移
# alembic/versions/001_initial_schema.py

def upgrade():
    # 创建表
    op.create_table('workspaces', ...)
    op.create_table('document_versions', ...)
    ...
    
    # 创建索引
    op.create_index('idx_document_versions_workspace', ...)

def downgrade():
    # 回滚变更
    op.drop_index('idx_document_versions_workspace')
    op.drop_table('document_versions')
    ...
```

### 向量索引版本管理

```python
# 向量索引需要重建时的策略
class VectorIndexVersion:
    version: str  # "v1", "v2"
    embedding_model: str  # "@cf/qwen/qwen3-embedding-0.6b"
    chunk_strategy: str  # "paragraph", "sentence"
    created_at: datetime

# 支持多版本共存，平滑迁移
def get_collection(workspace_id: str, version: str = "latest"):
    if version == "latest":
        version = get_latest_version(workspace_id)
    return chroma_client.get_collection(f"workspace_{workspace_id}__{version}")
```

## 八、数据保留与清理策略

### 保留策略

```python
# 软删除：保留数据但标记为不可用
class DocumentVersion(BaseModel):
    ...
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None

# 历史记录保留时间
RETENTION_POLICY = {
    "runs": 90,  # 运行记录保留 90 天
    "tool_events": 30,  # 工具事件保留 30 天
    "deleted_documents": 30,  # 删除的文档保留 30 天后物理删除
}
```

### 清理任务

```python
async def cleanup_old_records():
    """定期清理过期数据"""
    cutoff_date = datetime.now() - timedelta(days=RETENTION_POLICY["runs"])
    
    # 删除过期运行记录
    await db.execute(
        "DELETE FROM runs WHERE created_at < ?",
        (cutoff_date,)
    )
    
    # 物理删除标记删除的文档
    deleted_cutoff = datetime.now() - timedelta(days=RETENTION_POLICY["deleted_documents"])
    deleted_docs = await db.fetch_all(
        "SELECT * FROM document_versions WHERE deleted_at < ?",
        (deleted_cutoff,)
    )
    for doc in deleted_docs:
        # 删除文件
        os.remove(doc.file_path)
        # 删除数据库记录
        await db.execute("DELETE FROM document_versions WHERE id = ?", (doc.id,))
```

## 九、数据导出格式

### 报告导出 JSON

```json
{
  "workspace": {
    "id": "ws_abc123",
    "name": "2024年科研项目申报"
  },
  "query": "我是否满足重点项目申报条件？",
  "generated_at": "2024-10-22T10:30:00Z",
  "claims": [
    {
      "text": "您的副教授职称满足重点项目申报要求",
      "support_status": "supported",
      "evidences": [
        {
          "document": "科研项目申报指南2024.pdf",
          "version": 1,
          "page": 2,
          "text": "重点项目申请人须为副教授及以上职称",
          "applicable_scope": "2024年度"
        }
      ]
    }
  ],
  "facts": [
    {
      "key": "applicant_role",
      "value": "副教授",
      "confirmed": true
    }
  ],
  "checklist": [
    {
      "requirement": "申请人须为副教授及以上职称",
      "status": "met",
      "evidence_references": ["科研项目申报指南2024.pdf, 第2页"]
    }
  ],
  "pending_confirmations": [
    "请确认近三年科研项目的具体级别和时间"
  ]
}
```

这个数据模型设计确保了：
1. **类型安全**：使用 Pydantic 强制类型检查
2. **引用追溯**：所有结论都关联到具体证据
3. **版本管理**：文档版本与证据版本分离
4. **资料隔离**：通过 workspace_id 严格隔离
5. **坐标系统**：文本与视觉证据使用不同但明确的坐标系
6. **人工干预**：保留人工确认和纠正入口
7. **审计追踪**：记录所有工具调用和决策过程
