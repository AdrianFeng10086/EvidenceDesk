# Day 5 实现说明：分块、索引与 Case 级混合检索

## 1. 目标与产物

| 能力 | 产物 | 位置 |
| --- | --- | --- |
| 检索块分块 | 段落窗口 + 章节上下文，稳定 `chunk_id` | `backend/services/chunking.py` |
| 向量索引 | Chroma 持久化集合（按索引版本隔离），显式写入嵌入 | `backend/services/vector_store.py`、`backend/services/indexing.py` |
| 嵌入后端 | Cloudflare / 本地确定性哈希降级 | `backend/services/embedding.py` |
| 中文 BM25 | 单字 + 二元组 + 完整短词，含问句停用词 | `backend/services/tokenizer.py` |
| 混合检索 | 向量基线 + BM25 + RRF 融合 | `backend/services/retrieval.py` |
| Case 范围 | 固定引用版本、跨空间、快照与过期 Run | `backend/services/cases.py` |
| 接口 | Case、范围、检索、索引状态、日志、重建 | `backend/api/routes/cases.py` |
| 开发集评测 | 24 个开发问题，向量基线与融合对比 | `backend/scripts/evaluate_retrieval.py` |
| 召回记录 | 本地/真实嵌入模型两份结果 | `data/eval/day5-dev-recall*.json` |

## 2. 数据流

```
上传 / 重新解析
  → 解析得到 DocumentPage + EvidenceSpan（带页码、字符范围、文字框）
  → chunking：EvidenceSpan → RetrievalChunk（可多个）
  → embedding：正文 + 最近一级标题
  → Chroma：向量 + metadata（空间、版本、类型、适用范围、index_version）
  → SQLite：chunk 元数据与到 EvidenceSpan 的稳定映射
  → index_status = ready

retrieve_evidence(case_id, query, filters)
  → 校验 Case 所有者
  → 读取 case_scope_items，固定到 document_version_id
  → 过滤：空间 / 版本 / 文档 / 文件类型 / 片段类型 / 适用范围 / 删除状态
  → 只用 parse_status=success 且 index_status=ready 的来源
  → Chroma 向量召回（version 白名单） + BM25（同一候选集）
  → RRF 融合 → Top-K
  → 用 chunk.evidence_span_id 取真实 EvidenceSpan
  → 返回实际片段、版本/空间、稳定 chunk/span ID、字符范围与文字框
  → 写入 Run + RetrievalLog（范围快照、过滤条件、诊断、空结果原因）
```

## 3. 分块与稳定 ID

- 默认一个 `EvidenceSpan`（段落、列表项、标题、表格）为一个检索块。
- 超过 `CHUNK_MAX_CHARS`（默认 480）的 span 按换行优先切分，重叠
  `CHUNK_OVERLAP_CHARS`（默认 60）。
- 每个块保存两套范围：
  - `char_start / char_end`：页面文本中的绝对范围；
  - `span_char_start / span_char_end`：所属 EvidenceSpan 范围。
- 返回的 `text` 是块的实际原文；`span_text` 是完整证据片段；`bboxes`
  只保留与块范围有交集的文字框。
- `chunk_id = chk_ + sha256(document_version_id | evidence_span_id |
  chunk_index | content_hash)[:40]`，重复建索引保持稳定。
- `evidence_span_id` 保持为结果里的 `id`，现有证据卡与原文高亮无需改动。

### 章节上下文

TXT 样例常包含 Markdown 或“一、二、三”式标题，但扩展名是 `.txt`，解析器
会按普通段落处理。分块阶段额外识别标题首行，把最近一级标题写入
`RetrievalChunk.section_title`，并只用于嵌入与 BM25；用户看到的 `text`
仍是真实片段。这样“申报需要提交哪些材料”可以召回只列出材料、却没写
“申报材料”字样的列表项。

## 4. 索引配置版本

`services/index_config.py` 把以下配置计算为指纹：

- 嵌入提供方、模型、维度；
- 分块策略、最大块长、重叠长度；
- 中文分词器版本；
- 融合策略与索引 schema 版本。

指纹写入 `index_version`（如 `v1-63017527058e`），Chroma 集合名也带该版本后缀
（`evidence_chunks_v1_v1_63017527058e`），避免 256/1024 维向量混用；
同时记录在：

- `DocumentVersion.index_version`
- `RetrievalChunk.index_version`
- `RetrievalIndex` 清单表
- 每次 `RetrievalLog.config_snapshot`

当模型或策略变化时，旧版本索引的 `effective_index_status` 变为 `stale`，
检索返回 `INDEX_NOT_READY`，不会被悄悄混用。可通过
`POST /api/documents/{version_id}/index/rebuild` 或 `POST /api/index/rebuild`
重建；服务启动时也会在后台补齐 pending/failed/过期索引
（`INDEX_BACKFILL_ON_STARTUP=true`，测试环境关闭）。

## 5. 检索范围与授权

- 入口是 `retrieve_evidence(db, case_id, principal, query, filters, top_k)`；
  模型或调用方不能传入任意 `workspace_id` 扩大范围。
- Case 只允许所有者访问：其他主体返回 `403 CASE_FORBIDDEN`。
- 范围项固定引用 `document_version_id`，可以来自多个资料空间；加入范围时
  校验版本与空间一致，且空间属于当前所有者。
- `filters.workspace_ids / document_version_ids / document_ids` 必须落在
  Case 范围内，否则返回 `403 WORKSPACE_OUT_OF_SCOPE` /
  `VERSION_OUT_OF_SCOPE` / `DOCUMENT_OUT_OF_SCOPE`。
- 证据身份保留
  `(workspace_id, document_id, document_version_id, evidence_span_id, chunk_id)`；
  不同空间的同名文件是不同来源，结果带 `workspace_name` 与 `source_label`。

## 6. 过滤与删除状态

| 过滤 | 字段 |
| --- | --- |
| 资料空间 | `workspace_ids` |
| 文档版本 | `document_version_ids` |
| 文档 | `document_ids` |
| 文件类型 | `file_suffixes`（如 `.pdf`、`.txt`） |
| 片段类型 | `chunk_types`（`paragraph`、`heading`、`list_item`、`table`、`code`） |
| 适用范围 | `applicable_scopes`（匹配 `DocumentVersion.applicable_scope`） |
| 删除状态 | `deletion_status = active \| deleted \| all` |

默认只检索 `active` 来源。`deleted` 只用于审计过滤：已删除来源已经从
向量与候选块移除，因此检索会返回空并给出 `ALL_SOURCES_DELETED`，不会
把删除内容重新返回。文档软删除时：

1. 从 Chroma 删除该版本的全部向量；
2. `RetrievalChunk.status = deleted`；
3. `DocumentVersion.index_status = deleted`；
4. 新检索候选集不再包含它，返回 `ALL_SOURCES_DELETED`；
5. 历史 `RetrievalLog` 结果在读取时重新计算来源状态，标注
   `document_deleted / workspace_deleted / version_missing / chunk_deleted`
   与 `source_available = false`。

恢复文档会重置索引并在后台重建；重建完成后重新可检索。

## 7. 向量 + BM25 + RRF

### 向量基线

- Chroma 查询使用 `query_embeddings`，明确计算查询向量；
- `where` 同时限制 `document_version_id ∈ Case 范围` 与当前
  `index_version`，因此删除、未授权、旧模型的向量不会进入候选；
- 相似度 = `1 - cosine_distance`；
- 向量不可用时降级为纯关键词，并在 `warnings` 标记 `VECTOR_UNAVAILABLE`。

### 中文 BM25

`services/tokenizer.py` 使用可复现的字符 n-gram：

- 中文连续片段：单字 + 相邻二元组 + 2~8 字完整片段；
- 英文/数字：连续字母数字，转小写；
- 去掉“什么、多少、是否、请问”等问句词和单字虚词；
- `BM25Plus` 避免小语料下 IDF 为负导致匹配分数被抹掉。

验证用例：

```bash
cd backend
python -m pytest tests/test_tokenizer.py -q
# 3 passed
```

### 融合

使用 RRF：

```
score = w_vector / (k + rank_vector) + w_keyword / (k + rank_keyword)
```

默认 `k=60`、两个权重均为 1.0。结果同时返回
`vector_rank / vector_similarity / keyword_rank / keyword / fused`，便于
排查“向量命中但关键词没命中”等情况。

在没有多字词项命中且最高向量相似度低于阈值时，返回 `NO_MATCH`，而不是
把最近邻硬说成答案。

## 8. 空结果原因

| `empty_reason` | 含义 |
| --- | --- |
| `NO_SCOPE` | Case 没有固定引用任何版本 |
| `ALL_SOURCES_DELETED` | 范围内来源全部删除 |
| `SOURCES_UNAVAILABLE` | 版本/文档/空间缺失 |
| `INDEX_NOT_READY` | 来源存在但索引为 pending/indexing/failed/stale |
| `FILTERED_OUT` | 过滤条件排除了全部来源 |
| `NO_SEARCHABLE_CONTENT` | 索引就绪但没有可检索文本块 |
| `NO_MATCH` | 有候选但没有达到阈值的匹配 |

`status` 取值：

- `ok`：有可靠匹配；
- `insufficient`：有候选，但只有单字或低于相似度阈值的弱信号；
- `empty`：无结果，附 `empty_reason` 与中文 `note`。

响应同时包含 `counts`（范围项、删除、不可用、索引未就绪、候选块、向量/
关键词命中数）与 `excluded_sources`（被过滤原因）。

## 9. 范围快照、Run 与过期

- 每次检索写入 `Run` 与 `RetrievalLog`，保存：
  - `scope_snapshot`：范围项、空间名、文档名、版本、来源状态、索引状态；
  - `scope_hash`：由排序后的 `(workspace_id, version_id)` 对计算；
  - 过滤条件、结果、分数、`counts`、`diagnostics`、`config_snapshot`。
- 增加/删除范围项后，所有基于旧 `scope_hash` 的 Run 被标记：
  `status=stale`、`stale_reason=scope_changed`、`stale_at=...`。
- 历史日志读取时重新检查来源状态，因此删除文档后旧记录会显示
  “来源已删除或不可用”，但不会被修改成新结果。

## 10. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/cases` | 列出/创建 Case，可在创建时带范围项 |
| GET/PATCH | `/api/cases/{case_id}` | Case 详情与范围快照 |
| GET | `/api/cases/{case_id}/scope` | 范围项与来源状态 |
| POST | `/api/cases/{case_id}/scope` | 增加一个固定版本 |
| POST | `/api/cases/{case_id}/scope/batch` | 批量增加 |
| DELETE | `/api/cases/{case_id}/scope/{scope_item_id}` | 移除范围项并标记旧 Run |
| POST | `/api/cases/{case_id}/retrieve` | `retrieve_evidence`，返回结果与日志 ID |
| GET | `/api/cases/{case_id}/retrieval/index-status` | Case 内索引状态 |
| GET | `/api/cases/{case_id}/retrieval/logs` | 检索日志列表 |
| GET | `/api/retrieval/logs/{log_id}` | 单次日志，含历史来源状态 |
| GET | `/api/cases/{case_id}/runs` | Run 状态与过期标记 |
| GET | `/api/index/status` | 当前主体索引配置与版本状态统计 |
| POST | `/api/documents/{version_id}/index/rebuild` | 重建单个版本索引 |
| POST | `/api/index/rebuild` | 重建当前主体全部已解析版本 |

`/api/chat/stream` 新增可选 `case_id`：提供时使用 Case 固定范围检索，
否则保留原来的空间级关键词召回以兼容现有前端。

## 11. 开发集召回记录

评测集：三个样例各 8 个开发问题，共 24 题；命中定义为 Top-K 结果文本包含
任一人工期望词项。保留集 `eval-questions.md` 不参与调参。

| 检索方式 | Hit@1 | Hit@5 | MRR |
| --- | --- | --- | --- |
| 本地哈希向量基线（256 维） | 0.500 | 0.958 | 0.715 |
| 本地哈希 + BM25 + RRF | **0.667** | **1.000** | **0.823** |
| Cloudflare `@cf/baai/bge-m3` 向量基线（1024 维） | 0.417 | 0.875 | 0.615 |
| Cloudflare `@cf/baai/bge-m3` + BM25 + RRF | **0.542** | **1.000** | **0.735** |

记录文件：

- `data/eval/day5-dev-recall.json`：本地确定性向量，可离线复现；
- `data/eval/day5-dev-recall-cloudflare.json`：当前配置的真实嵌入模型。

复现命令：

```bash
cd backend
python scripts/evaluate_retrieval.py
python scripts/evaluate_retrieval.py --provider cloudflare \
  --model @cf/baai/bge-m3 --dimension 1024 \
  --output ../data/eval/day5-dev-recall-cloudflare.json
```

两份记录都保存了 `index_version`、嵌入模型/维度、分块与分词器版本，
便于后续模型变更时对比。

## 12. 验收测试

```bash
cd backend
python -m pytest tests -q
# 51 passed
```

新增覆盖：

- 已知证据问题进入 Top-K，且结果能映射回真实 `EvidenceSpan` 与字符范围；
- 两个资料空间同名文件不会串资料，结果带空间名与来源标签；
- 空间、版本、文件类型、片段类型、适用范围、删除状态过滤；
- `NO_SCOPE / INDEX_NOT_READY / ALL_SOURCES_DELETED / FILTERED_OUT /
  NO_MATCH` 可区分；
- 越权 Case、他人空间、范围外版本被拒绝；
- 删除后新检索排除来源，历史日志标记来源已删除；
- 范围变更后旧 Run 标记 `stale`；
- 重复检索与重建索引后 `chunk_id / evidence_span_id` 稳定；
- 中文 BM25 分词与混合数字/英文词项验证。

## 13. 限制与后续

- 向量基线始终返回最近邻，因此用相似度阈值与多字关键词共同判断“无匹配”；
  阈值仍需在保留集和真实资料上校准。
- 当前章节识别是首行启发式，复杂 PDF 版式仍依赖解析器的 `heading`。
- 表格块目前整表作为一个片段，单元格级引用留到 Day 10 版本对照/报告。
- 索引构建在上传后台任务中同步完成；大文档可改为独立索引队列。
- 每个索引配置版本使用独立 Chroma 集合，切换模型/维度不会冲突；旧集合暂时保留，
  可在 Day 13 增加归档/清理任务。
- 本地哈希向量只用于离线测试，不代表生产语义效果。
