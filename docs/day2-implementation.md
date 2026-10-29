# Day 2 实现说明

## 目标与完成情况

Day 2 的目标是三栏工作台 + assistant-ui 接入 + FastAPI SSE 真实文本流。

| 交付项 | 状态 | 位置 |
| --- | --- | --- |
| 工作台路由 | ✅ | `frontend/src/app/workspace/[id]/page.tsx` |
| 可复用面板 | ✅ | `frontend/src/components/workspace/` |
| 流式事件类型 | ✅ | `frontend/src/lib/types/stream-events.ts` |
| assistant-ui Runtime 接入 | ✅ | `frontend/src/components/workspace/ChatPanel.tsx` |
| SSE 适配器 | ✅ | `frontend/src/lib/chat-adapter.ts` |
| 同源 SSE 代理 | ✅ | `frontend/src/app/api/chat/stream/route.ts` |
| 运行状态 | ✅ | 顶部状态胶囊 + 消息内“正在生成…” |
| 停止生成 | ✅ | 输入区停止按钮（`ComposerPrimitive.Cancel`） |
| 失败重试 | ✅ | 失败/停止消息内的“重试”（`MessageRuntime.reload()`） |
| 空状态 | ✅ | 欢迎面板 + 示例问题 |
| 折叠证据卡 | ✅ | `frontend/src/components/workspace/EvidenceCard.tsx` |
| 移动端分区标签页 | ✅ | `frontend/src/components/workspace/WorkspaceLayout.tsx` |
| `globals.css` 样式生效 | ✅ | 新增 `frontend/postcss.config.mjs` |

## 技术实现

### 1. assistant-ui 运行时

`ChatPanel` 使用 `useLocalRuntime(createEvidenceDeskAdapter(workspaceId))` 创建
`LocalRuntime`，并通过 `AssistantRuntimeProvider` 向下提供上下文：

```tsx
const adapter = useMemo(() => createEvidenceDeskAdapter(workspaceId), [workspaceId]);
const runtime = useLocalRuntime(adapter);

<AssistantRuntimeProvider runtime={runtime}>
  <EvidenceCard />   {/* 注册 search_evidence 工具 UI */}
  <ThreadView ... />
</AssistantRuntimeProvider>
```

消息列表使用 `ThreadPrimitive.Messages` 的自定义 `UserMessage` / `AssistantMessage`，
文本部分用 `MessagePrimitive.Content` + `ContentPartPrimitive.Text` 渲染，
工具调用部分由注册的 `EvidenceCard` 自动接管。

### 2. SSE 文本流

```
浏览器 → POST /api/chat/stream（Next.js 同源代理）
       → FastAPI /api/chat/stream（SSE）
       → 适配器解析为 assistant-ui 的 ChatModelRunResult
```

`lib/sse.ts` 按空行切分 SSE 帧，解析 `data:` 中的 JSON 事件。
`lib/chat-adapter.ts` 将事件映射为消息内容：

- `text_delta`：累加文本并增量 yield
- `tool_started` / `tool_finished`：生成 `tool-call` 内容部分
- `claim_ready`：补充结论文本
- `run_finished`：结束本轮
- `error`：以 `incomplete/error` 状态结束，触发前端重试入口

### 3. 运行状态、停止与重试

- 运行状态来自 `useThread((s) => s.isRunning)`。
- 停止生成：输入区的 `ComposerPrimitive.Cancel` 调用 `cancelRun()`，
  中止 `AbortController` → 适配器中的 `fetch` 被取消 → Next.js 代理通过
  `req.signal` 断开到 FastAPI 的连接 → 后端 `request.is_disconnected()` 停止生成。
- 失败重试：消息状态为 `incomplete`（`error` 或 `cancelled`）时显示“重试”，
  调用 `messageRuntime.reload()` 从该消息的父节点重新运行。

### 4. 折叠证据卡（Day 2 为样例数据）

证据卡通过 `makeAssistantToolUI({ toolName: 'search_evidence', ... })` 注册，
使用 Radix Accordion 实现折叠，`Accordion.Trigger` 是原生按钮，可通过键盘聚焦并回车展开。

**样例数据标识**：后端在 `tool_finished` 中返回 `is_sample: true` 与
`note: "样例数据，非真实检索结果…"`，卡片因此始终显示琥珀色
“样例数据 · 非真实检索结果”徽标和说明条，避免被误认为真实检索结果。
Day 5 接入真实检索后，`is_sample` 变为 `false`，徽标自动消失。

### 5. 移动端布局

桌面端（`md` 及以上）保持三栏；移动端不压缩三栏，而是显示顶部分区标签页
（资料 / 对话 / 文档），一次只渲染一个面板。

### 6. `globals.css` 无法应用的原因与修复

**原因**：`frontend/` 下缺少 PostCSS 配置。Next.js 只有在存在
`postcss.config.*` 时才会用 Tailwind 处理 `@tailwind` 与 `@apply`；
缺失时 `globals.css` 被原样输出，Tailwind 工具类不会生成。

**修复**：

1. 新增 `frontend/postcss.config.mjs`，注册 `tailwindcss` 与 `autoprefixer`。
2. 将 `tailwind.config.ts` 的 `content` 收敛为 `./src/**/*.{js,ts,jsx,tsx,mdx}`，
   避免遗漏 `src/lib` 等目录。
3. `globals.css` 补充 `html/body` 高度、字体平滑、深色滚动条与
   Accordion 折叠动画关键帧。

> 注意：PostCSS 配置在 dev server 启动时读取。新增该文件后需要重启
> `npm run dev`（或让 dev server 重启）才会生效。

## 本地验证

```bash
# 后端（项目根目录的 .env 会被自动加载）
cd backend && python main.py

# 前端
cd frontend && npm run dev
```

已验证：

- `GET /health` 返回正常。
- `POST /api/chat/stream` 能逐步返回 `text_delta`（真实模型），并在末尾返回
  `tool_started` / `tool_finished` / `claim_ready` / `run_finished`。
- Next.js 代理 `/api/chat/stream` 能将 SSE 原样透传。
- 生产构建通过，构建产物 CSS 中已生成 `bg-navy` 等工具类。

## 尚未完成（后续 Day）

- 真实文档上传、解析与检索（Day 3–5）
- 真实证据高亮定位与视觉证据框（Day 4、Day 11）
- 条件核对清单与缺失信息补问（Day 8）
- 报告导出（Day 10）
