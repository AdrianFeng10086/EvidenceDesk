# API 规范（当前实现）

基础路径：`http://localhost:8000/api`。前端通过 Next.js 同源代理访问，代理只转发请求，不包含业务逻辑。

演示模式默认访问主体为 `demo_user`；可用请求头 `X-Demo-User` 切换主体，用于验证所有权隔离。

## 资料空间

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workspaces` | 当前主体拥有的、未删除的资料空间 |
| POST | `/workspaces` | 创建资料空间，`owner_id=当前主体` |
| GET | `/workspaces/{workspace_id}` | 资料空间元数据 |

## 文档

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workspaces/{workspace_id}/documents` | 活跃文档列表；`include_deleted=true` 时包含回收站 |
| POST | `/workspaces/{workspace_id}/documents` | multipart 上传；可带 `upload_source`、`applicable_scope` |
| GET | `/workspaces/{workspace_id}/documents/{document_id}/delete-impact` | 删除影响：版本、页面、证据片段、引用 Case、最近 Run |
| DELETE | `/workspaces/{workspace_id}/documents/{document_id}` | 软删除文档并写入来源墓碑 |
| POST | `/workspaces/{workspace_id}/documents/{document_id}/restore` | 恢复保留期内的软删除文档 |
| GET | `/documents/{version_id}` | 版本详情、页面摘要、解析任务 |
| GET | `/documents/{version_id}/status` | 轻量状态轮询 |
| GET | `/documents/{version_id}/content?page=1` | 页面原文、证据片段与文字框 |
| GET | `/documents/{version_id}/original` | 下载原始文件，响应头含 `X-Content-SHA256` |
| POST | `/documents/{version_id}/parse/retry` | 解析失败重试，生成新的 `ParseJob` |

软删除文档的详情、状态、原文、下载与重试接口返回 `404 DOCUMENT_DELETED`；所属资料空间被删除时返回 `404 WORKSPACE_DELETED`。原始文件缺失时，下载接口返回 `404 ORIGINAL_FILE_MISSING`，恢复接口返回 `409 ORIGINAL_FILE_MISSING`。

## 事项（Case）与检索范围

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/cases` | 当前主体的事项列表 |
| POST | `/cases` | 创建事项，可同时提交 `scope_items` |
| GET | `/cases/{case_id}` | 事项详情、范围项与范围快照 |
| PATCH | `/cases/{case_id}` | 修改标题/描述 |
| GET | `/cases/{case_id}/scope` | 范围项、来源状态与范围指纹 |
| POST | `/cases/{case_id}/scope` | 固定引用一个文档版本 |
| POST | `/cases/{case_id}/scope/batch` | 批量固定引用（先全部校验） |
| DELETE | `/cases/{case_id}/scope/{scope_item_id}` | 移除范围项；旧 Run 标记过期 |

创建/增加范围项时校验：版本存在、版本属于给定空间、空间属于当前主体且未删除。
`scope_items` 可以来自多个资料空间，但必须是同一所有者。

## 证据检索（Case 级）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/cases/{case_id}/retrieve` | 向量 + BM25 混合检索，返回真实证据片段与日志 ID |
| GET | `/cases/{case_id}/retrieval/index-status` | Case 内各来源解析/索引状态 |
| GET | `/cases/{case_id}/retrieval/logs` | 检索日志列表 |
| GET | `/retrieval/logs/{log_id}` | 单次检索日志；历史结果标注来源是否已删除/不可用 |
| GET | `/cases/{case_id}/runs` | Run 列表与 `stale` 过期标记 |
| GET | `/index/status` | 当前主体的索引配置、版本状态统计 |
| POST | `/documents/{version_id}/index/rebuild` | 重建单个版本索引（202） |
| POST | `/index/rebuild` | 重建当前主体全部已解析版本（202） |

`POST /cases/{case_id}/retrieve` 请求体：

```json
{
  "query": "普通员工住宿费上限是多少",
  "top_k": 5,
  "filters": {
    "workspace_ids": [],
    "document_version_ids": [],
    "document_ids": [],
    "file_suffixes": [".txt"],
    "chunk_types": ["paragraph", "table"],
    "applicable_scopes": ["2024年度"],
    "deletion_status": "active"
  },
  "record_run": true
}
```

响应关键字段：`status`（`ok/insufficient/empty`）、`empty_reason`、`note`、
`scope_snapshot`、`scope_hash`、`counts`、`excluded_sources`、`diagnostics`、
`run_id`、`retrieval_log_id` 与 `results`。每个结果包含：

- `id` / `evidence_span_id`：真实 EvidenceSpan ID；
- `chunk_id` / `stable_id`：稳定检索块 ID；
- `workspace_id` / `workspace_name` / `source_label`：来源空间；
- `document_version_id` / `file_version`：固定版本；
- `text`：实际检索片段，`char_start/char_end` 为页面绝对范围；
- `span_text`、`context_before/after`、`bboxes`：定位与高亮信息；
- `scores.vector_similarity / keyword / fused / ranks`。

`empty_reason`：

| 值 | 含义 |
| --- | --- |
| `NO_SCOPE` | 事项没有范围项 |
| `ALL_SOURCES_DELETED` | 范围内来源全部删除 |
| `SOURCES_UNAVAILABLE` | 版本/文档/空间缺失 |
| `INDEX_NOT_READY` | 索引 pending/indexing/failed/stale |
| `FILTERED_OUT` | 过滤条件排除全部来源 |
| `NO_SEARCHABLE_CONTENT` | 没有可检索文本块 |
| `NO_MATCH` | 有候选但没有超过阈值的匹配 |

越权/越界错误：`CASE_FORBIDDEN`、`WORKSPACE_FORBIDDEN`、
`WORKSPACE_OUT_OF_SCOPE`、`VERSION_OUT_OF_SCOPE`、`DOCUMENT_OUT_OF_SCOPE`。

## 对话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workspaces/{workspace_id}/evidence/search?q=...` | 兼容旧前端的空间级关键词召回；已删除文档不参与 |
| POST | `/chat/stream` | SSE 流式对话；请求体可带 `case_id` 使用 Case 级混合检索 |

## 错误格式

```json
{
  "error": {
    "code": "DOCUMENT_DELETED",
    "message": "文档不存在或已删除",
    "details": { "version_id": "ver_..." }
  }
}
```

常用错误码：`NOT_FOUND`、`DOCUMENT_DELETED`、`WORKSPACE_DELETED`、`ORIGINAL_FILE_MISSING`、`DOCUMENT_ALREADY_DELETED`、`DOCUMENT_NOT_DELETED`、`WORKSPACE_DOCUMENT_LIMIT`、`PARSE_NOT_READY`、`UNSUPPORTED_FORMAT`、`TOO_LARGE`。
