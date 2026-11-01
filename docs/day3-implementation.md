# Day 3 实现说明：文档导入、不可变版本与证据片段

## 目标与完成情况

| 交付项 | 状态 | 位置 |
| --- | --- | --- |
| PDF（带文字层）/ TXT / Markdown 上传 | ✅ | `backend/api/routes/documents.py` |
| 保存原始文件 + SHA-256 哈希 | ✅ | `backend/services/storage.py` |
| 不可变文档版本（同名新内容生成 v2，不覆盖旧证据） | ✅ | `backend/db/models.py`、`backend/tests/test_versions.py` |
| 按页、段落、文字框抽取原文 | ✅ | `backend/services/parser.py` |
| 字符偏移 ↔ 文字框坐标映射 | ✅ | `EvidenceSpan.char_start/char_end` + `BBox.char_start/char_end` |
| 上传 / 解析 / 索引准备 / 成功 / 失败状态 | ✅ | `DocumentVersion.parse_status`、`ParseJob` |
| 解析任务与错误提示 | ✅ | `ParseJob`、`GET /api/documents/{id}/status` |
| 资料空间绑定访问主体与所有权校验 | ✅ | `backend/services/access.py` |
| 损坏 / 扫描 / 空白 / 超限文件明确状态 | ✅ | `backend/tests/test_parse_failures.py` |
| 布局不可靠时标记“受限” | ✅ | `support_level=restricted` + `warnings` |
| 前端文档列表、上传、状态轮询、原文阅读 | ✅ | `frontend/src/components/workspace/FileList.tsx`、`DocumentViewer.tsx` |
| 前端 Markdown 渲染优化 | ✅ | `frontend/src/components/markdown/MarkdownContent.tsx` |
| 对话框长宽自适应 | ✅ | `ChatPanel.tsx`（`minRows/maxRows`、视口高度上限、响应式宽度） |

## 一、数据模型与不可变版本

```
Workspace (owner_id)
  └── Document (逻辑文档，按规范化文件名去重)
        └── DocumentVersion (不可变内容版本)
              ├── DocumentPage (页面原文，字符偏移基准)
              ├── EvidenceSpan (段落/行证据 + 文字框)
              └── ParseJob (解析任务与错误)
```

关键规则：

1. **内容标识不可变**：`file_hash`、`file_path`、`version` 在版本创建后不再修改。
2. **同名不同内容**：`Document.normalized_name` 相同 -> 版本号 +1，旧版本的 `DocumentPage` 与 `EvidenceSpan` 原样保留。
3. **同内容重复上传**：按 `workspace_id + file_hash` 命中已有版本，直接返回该版本（`duplicate: true`），不产生新记录。
4. **文件落盘不复用目录**：
   ```
   data/uploads/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/original.{ext}
   ```
   上传先写入 `.staging/{uuid}`，校验通过后才移动到版本目录；重复文件只删除暂存副本。
5. 失败重试只清理**当前版本**的半成品页面/证据，不触碰历史版本。

## 二、解析规则

### PDF

- 先用 `pypdf` 检查页数、加密与损坏；再用 `pdfplumber` 逐页抽取。
- 每页以 `extract_text_lines()` 的行文本拼接为 `DocumentPage.text`（行间 `\n`），作为该页字符偏移的基准。
- 每个 `EvidenceSpan`：
  - `char_start/char_end` 指向 `DocumentPage.text`；
  - `bboxes` 为每行一个矩形，记录 PDF 点坐标及该行对应的字符范围；
  - 正常布局按段落合并行，标题单独成片段；布局受限时退回逐行片段。
- 页面尺寸 `width/height` 写入页面元数据，文字框同时携带 `page_width/page_height`，前端无需额外查询。

### TXT / Markdown

- 编码顺序：UTF-16 BOM → UTF-8(-sig) → GB18030；GB18030 命中时写入 `ENCODING_FALLBACK` 警告。
- 按空行切分段落；Markdown 的标题、列表、代码块、表格行单独识别，代码块内的空行不拆分。
- 纯文本片段没有页面坐标，`bboxes=[]` 是明确结果，不伪造坐标。
- 超长段落（>1500 字符）按行拆分为多个片段，并写入 `LONG_BLOCK_SPLIT` 警告。

## 三、状态与错误

状态机：

```
uploaded -> parsing -> indexing -> success
                            \-> failed
```

`indexing` 表示解析产物已生成、等待向量/关键词索引（Day 5 接入真实索引入口）。
`ParseJob` 与 `DocumentVersion` 同步记录状态、开始/结束时间与错误。

| 错误码 | 触发条件 | 前端表现 |
| --- | --- | --- |
| `UNSUPPORTED_FORMAT` | 非 PDF/TXT/MD（上传即拒绝，415） | 上传错误提示 |
| `TOO_LARGE` | PDF > `MAX_PDF_SIZE_MB`，文本 > `MAX_TEXT_SIZE_MB`（413） | 上传错误提示 |
| `TOO_MANY_PAGES` | PDF 页数 > `MAX_PDF_PAGES` | 解析失败 |
| `ENCRYPTED` | PDF 加密且无法用空密码打开 | 解析失败 |
| `CORRUPTED` | PDF 结构损坏/无法读取 | 解析失败 |
| `NO_TEXT_LAYER` | 只有图像、没有文字层（扫描件） | 解析失败，明确提示不支持 OCR |
| `EMPTY_DOCUMENT` | 空白 PDF/TXT/MD | 解析失败 |
| `UNSUPPORTED_ENCODING` | 文本编码无法识别或疑似二进制 | 解析失败 |
| `INTERRUPTED` | 服务重启时任务仍在中间状态 | 解析失败，可重新解析 |

布局可靠性：

| `support_level` | 含义 |
| --- | --- |
| `full` | 单栏、字符坐标覆盖充分、未检测到表格/旋转文本 |
| `restricted` | 检测到多栏、表格、旋转文本、坐标覆盖不足或乱码；原文仍保留，但段落顺序/文字框需人工核对 |
| `unsupported` | 解析失败，没有可用原文 |

限制说明（不伪装为完整支持）：

- 扫描件不做 OCR；
- 表格按行抽取，未还原单元格结构；
- 多栏 PDF 会标记 `LAYOUT_MULTI_COLUMN`，不承诺可靠阅读顺序；
- 段落切分是启发式规则，受限布局下退回逐行。

## 四、接口

所有接口都经过资料空间所有权校验。演示模式默认访问主体为 `demo_user`，
可用请求头 `X-Demo-User` 切换，便于验证越权拒绝。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/workspaces` | 当前主体可访问的资料空间 |
| POST | `/api/workspaces` | 创建资料空间，`owner_id=当前主体` |
| GET | `/api/workspaces/{id}` | 资料空间元数据 |
| GET | `/api/workspaces/{id}/documents` | 文档列表（含全部版本与解析状态） |
| POST | `/api/workspaces/{id}/documents` | 上传文件（multipart，可带 `upload_source`/`applicable_scope`） |
| GET | `/api/documents/{version_id}` | 版本详情、页面摘要、解析任务 |
| GET | `/api/documents/{version_id}/status` | 轻量状态轮询 |
| GET | `/api/documents/{version_id}/content?page=1` | 页面原文 + 证据片段 + 文字框 |
| GET | `/api/documents/{version_id}/original` | 下载原始文件（带 `X-Content-SHA256`） |
| POST | `/api/documents/{version_id}/parse/retry` | 失败重试（新 `ParseJob`，attempt+1） |

上传响应示例：

```json
{
  "duplicate": false,
  "version": {
    "id": "ver_...",
    "version": 1,
    "parse_status": "uploaded",
    "file_hash": "d4905e3d...",
    "support_level": "pending"
  },
  "parse_job": { "status": "queued", "attempt": 1 }
}
```

页面内容示例：

```json
{
  "page_number": 1,
  "text": "科研项目申报指南\n重点项目申请人须为副教授及以上职称，……",
  "width": 595.28,
  "height": 841.89,
  "spans": [
    {
      "kind": "heading",
      "text": "科研项目申报指南",
      "char_start": 0,
      "char_end": 8,
      "bboxes": [
        {
          "x0": 72, "y0": 69.9, "x1": 184, "y1": 83.9,
          "page_width": 595.28, "page_height": 841.89,
          "char_start": 0, "char_end": 8
        }
      ]
    }
  ]
}
```

## 五、前端

- **FileList**：真实接口、拖拽/按钮上传、1.2 秒轮询中间状态、版本号与页数、
  失败错误码与“重新解析”、受限标签。
- **DocumentViewer**：解析进度步骤、失败详情、版本切换、页码切换、字号调整、
  下载原始文件、按片段展示原文；点击片段可查看文字框坐标与字符范围。
- **Markdown**：assistant 消息和 Markdown 文档共用 `MarkdownContent`，支持标题、
  列表、表格、引用、链接、行内代码与代码块；不启用原始 HTML。
- **对话框自适应**：输入框使用 `react-textarea-autosize` 的 `minRows/maxRows`，
  高度随内容增长、最高 40vh；宽度随中间栏自适应（`max-w-3xl`，2xl 屏幕放宽）；
  消息区、输入区和左右侧栏均使用响应式宽度。

## 六、验证

后端测试：

```bash
cd backend
python -m pytest tests -q
```

结果：`26 passed`。

覆盖：

- `tests/test_pdf_layouts.py`：三份不同布局 PDF
  - 单栏双页：`support_level=full`，核对两页原文、页码、标题/段落/列表片段、文字框与字符映射；
  - 双栏：`restricted` + `LAYOUT_MULTI_COLUMN`，退回逐行片段；
  - 表格：`restricted` + `LAYOUT_TABLES`，保留表格文字。
- `tests/test_parse_failures.py`：损坏、扫描、空白、加密、超限、非法格式、空文本、二进制文本、重试。
- `tests/test_versions.py`：同名新内容生成 v2 且旧版本原文/证据不变；同哈希上传幂等；原始文件与哈希一致；路径穿越文件名净化；ORM 层拦截版本内容字段修改。
- `tests/test_text_files.py`：TXT 段落偏移、Markdown 标题/列表/代码块、GB18030 编码回退。
- `tests/test_ownership.py`：跨主体读取/上传/聊天全部 403，资料空间列表按主体隔离。
- `tests/test_status.py`：`uploaded -> parsing -> indexing -> success` 状态推进与 `ParseJob` 时间戳。

前端验证：

```bash
cd frontend
npx tsc --noEmit
npm run build
```

均通过。另用真实后端 + Next 生产服务做了冒烟验证：四份 PDF 上传后分别得到
`full / restricted / restricted / failed(NO_TEXT_LAYER)`，单栏文档的
`page_text[char_start:char_end] == span.text` 全部成立，下载文件 SHA-256 与接口一致。

## 七、尚未完成（后续 Day）

- 真实向量索引与 BM25 建索引（Day 5，`indexing` 阶段目前只做状态占位）
- PDF 页面渲染、点击引用精确高亮（Day 4）
- 检索结果替换 Day 2 样例证据（Day 5）
- 表格单元格结构还原、扫描件 OCR（首版明确不支持）
