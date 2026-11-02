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

## 证据与对话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workspaces/{workspace_id}/evidence/search?q=...` | 关键词召回真实 EvidenceSpan；已删除文档不参与 |
| POST | `/chat/stream` | SSE 流式对话，事件见 `docs/architecture.md` |

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
