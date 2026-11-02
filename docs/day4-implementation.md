# Day 4 实现说明：PDF.js 精确证据定位

## 1. 目标与产物

| 能力 | 产物 | 位置 |
| --- | --- | --- |
| 真实 EvidenceSpan 检索 | `search_evidence` 返回数据库中的真实片段 | `backend/services/evidence_search.py`、`backend/api/routes/chat.py` |
| 证据卡点击定位 | `EvidenceCard`（摘录、上下文、定位按钮） | `frontend/src/components/workspace/EvidenceCard.tsx` |
| PDF 页面渲染 | `PdfPageView`（PDF.js canvas） | `frontend/src/components/evidence/PdfPageView.tsx` |
| 红色实线高亮 | `HighlightOverlay`（区分 evidenceId） | `frontend/src/components/evidence/HighlightOverlay.tsx` |
| 页级跳转兜底 | assistant-ui `DocumentReference` | `frontend/src/components/evidence/DocumentReference.tsx` |
| 阅读器 / 文本定位 | `DocumentViewer` | `frontend/src/components/workspace/DocumentViewer.tsx` |
| 证据定位状态 | zustand store + 状态条 | `frontend/src/lib/stores/evidence-locator.ts`、`frontend/src/lib/evidence/location-status.ts` |
| 坐标换算 | 纯函数 + Node 测试 | `frontend/src/lib/pdf/coordinates.ts`、`coordinates.test.ts` |
| 段落 / 行范围 | 纯函数 + Node 测试 | `frontend/src/lib/evidence/text-range.ts`、`text-range.test.ts` |

## 2. 数据流

```
search_evidence（真实 EvidenceSpan）
  → EvidenceCard 点击“定位”
  → useEvidenceLocator.locate({ documentVersionId, spanId, page, bboxes, context… })
  → WorkspaceLayout 把目标版本推给右侧 DocumentViewer
  → DocumentViewer 拉取文档元数据与该页原文
  → PDF：PdfPageView 渲染页面，HighlightOverlay 用 bbox * scale 画红框
  → TXT/Markdown：TextViewer 按 span.char_start/char_end 高亮段落
```

后端返回的真实片段带：

- `document_version_id`：定位到不可变文档版本，连续点击不同引用不会串文件
- `page` / `page_count`：PDF 页码
- `bboxes[]`：pdfplumber 坐标系（页面左上角原点，单位 pt）
- `char_start` / `char_end`：纯文本段落范围
- `context_before` / `context_after`：前后段落

没有匹配证据时返回空列表和明确 `note`，不再用样例证据伪装真实检索。

## 3. 坐标转换与缩放

pdfplumber 的文字框使用**页面左上角原点、单位 pt**。PDF.js 在 `rotation = 0`
时 viewport 也是左上角原点，因此换算为：

```ts
left = bbox.x0 * scale;
top = bbox.y0 * scale;
width = (bbox.x1 - bbox.x0) * scale;
height = (bbox.y1 - bbox.y0) * scale;
```

`scale = fitScale(容器宽度, 页面宽度pt, zoom)`。容器宽度由 `ResizeObserver`
监听，因此：

- 75% / 100% / 150% 缩放时，矩形相对页面的位置不变
- 侧栏拖动或窗口缩放后，canvas 与红框一起按新 scale 重算
- 画布按 `devicePixelRatio` 放大，CSS 尺寸仍用逻辑像素，红框与文字对齐

## 4. 页级 / 不可精确定位

| 情况 | 行为 | 状态 |
| --- | --- | --- |
| PDF 有文字框、旋转 0、解析完整 | 红色实线矩形 | `exact` 已精确定位 |
| 多栏 / 表格（`support_level = restricted`） | 仍画红框，但提示人工核对 | `approximate` 受限定位 |
| 页面旋转 90/180/270 | 不画矩形，跳到正确页 | `page` 页级定位 |
| 证据没有文字框 | 不画矩形，跳到正确页 | `page` 页级定位 |
| TXT / Markdown | 段落序号 + 行范围，红色边框 | `text` 段落定位 |
| 原文 / 版本缺失、解析失败 | 明确错误与错误码 | `failed` 定位失败 |
| 文档已软删除 | 后端返回 404 `DOCUMENT_DELETED`，阅读器显示错误，不再渲染旧文档 | `failed` 定位失败 |

`DocumentReference` 按文档列出“第 N 页 + 摘录”，即使无法精确高亮也能跳到正确页面。
同一页有多处证据时，阅读器提供“本页 X 处引用 / 上一处 / 下一处”，
`HighlightOverlay` 只为当前 `evidenceId` 画红框，其他引用不会被误高亮。

## 5. 定位失败的修复前后案例

### 现象

第一版按照 `docs/architecture.md` 的旧示例调用
`viewport.convertToViewportPoint(bbox.x0, bbox.y0)`。对于页面高度 841.92pt、
`y0 = 110.25` 的文字框，矩形被画到页面底部附近，看起来像是证据在页面下方，
缩放时上下位置仍然错误。

### 原因

`convertToViewportPoint` 期待 PDF 原生坐标（左下角原点），而 pdfplumber 的
`bbox` 是左上角原点。两者 y 轴方向相反，必须镜像一次。

### 修复前

```ts
const [x0, y0] = viewport.convertToViewportPoint(bbox.x0, bbox.y0);
const [x1, y1] = viewport.convertToViewportPoint(bbox.x1, bbox.y1);
// y0/y1 被当成左下角坐标，结果上下镜像
```

### 修复后

```ts
// 页面旋转为 0 时，左上角原点与 pdfplumber 一致，直接乘以 scale
const left = bbox.x0 * scale;
const top = bbox.y0 * scale;
const width = (bbox.x1 - bbox.x0) * scale;
const height = (bbox.y1 - bbox.y0) * scale;
```

回归测试 `frontend/src/lib/pdf/coordinates.test.ts` 中的
“修复前案例：左下角原点会把文字框上下镜像”会断言：

```ts
const legacyTop = (PAGE_HEIGHT - bbox.y1) * scale;
assert.notEqual(fixed.top, legacyTop);
assert.equal(fixed.top, bbox.y0 * scale);
```

## 6. 验收记录

### 自动测试

```bash
# 坐标换算：75/100/150%、面板宽度变化、旋转、越界裁剪、镜像回归
cd frontend
npm run test:coordinates

# 真实证据检索：版本/页码/字符范围/上下文/空间隔离
cd backend
python -m pytest tests/test_evidence_search.py -q
```

结果：前端 10 项通过；后端 3 项通过。

### 浏览器实测（Playwright + 本机 Chrome）

- 同一证据在 75% / 100% / 150%：红框相对 canvas 的 `left/top/width/height`
  误差 < 0.002（浮点像素舍入）
- 面板宽度 1500 / 1150 / 1850 px：相对位置保持一致
- 同一页多处证据：点击“下一处”后，`data-evidence-id` 切换，红框数量随该片段
  的文字框数量变化，其他片段不高亮
- 页级兜底：点击 `DocumentReference` 第 2 页，页码输入变为 2，状态为页级定位，
  不画红框
- 连续点击不同文件：先点原文缺失的旧 PDF，出现“原始 PDF 不存在或已被删除
  （HTTP 404）”；再点回演示 PDF，canvas 和红框恢复，未停留在旧文件
- 旋转页面：显示“第 1 页旋转 90°，暂不支持精确高亮，已做页级定位”，无红框
- 双栏受限 PDF：显示“受限定位”，仍画红框并提示人工核对
- TXT：显示“段落定位 · 第 2 段 · 第 3 行”，不显示页码输入，不渲染
  `DocumentReference`，正文中红框段落带前后文

## 7. 限制与后续

- 前端不做 OCR；扫描件仍按 Day 3 的错误码失败
- 旋转页面目前只做页级跳转，后续可把 bbox 旋转到 viewport 坐标系
- 受限布局的红框来自逐行文字框，阅读顺序不保证
- 首版检索为确定性关键词召回；Day 5 替换为向量 + BM25 后，返回结构保持不变
- PDF.js worker 由 `scripts/copy-pdf-worker.mjs` 在 `postinstall/predev/prebuild`
  复制到 `public/pdf.worker.min.mjs`，不依赖 CDN
