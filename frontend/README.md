# 有据工作台前端

基于 Next.js 的有据工作台前端应用。

## 安装步骤

1. 安装依赖：
```bash
npm install
```

2. 配置环境变量：
```bash
cp ../.env.example .env.local
```

3. 运行开发服务器：
```bash
npm run dev
```

打开 http://localhost:3000

## 项目结构

```
frontend/
├── src/
│   ├── app/                    # Next.js 14 app 目录
│   │   ├── layout.tsx         # 根布局
│   │   ├── page.tsx           # 首页
│   │   └── workspace/         # 工作空间路由
│   │       └── [id]/
│   │           └── page.tsx   # 工作空间详情
│   ├── components/
│   │   ├── workspace/
│   │   │   ├── FileList.tsx          # 左侧面板：文件列表
│   │   │   ├── ChatPanel.tsx         # 中间面板：对话与清单
│   │   │   ├── DocumentViewer.tsx    # 右侧面板：PDF 阅读器
│   │   │   └── WorkspaceLayout.tsx   # 三栏布局
│   │   ├── evidence/
│   │   │   ├── EvidenceCard.tsx      # 可折叠的证据来源
│   │   │   ├── HighlightOverlay.tsx  # 精确文本/视觉高亮
│   │   │   └── DocumentReference.tsx # 页面级后备引用
│   │   ├── checklist/
│   │   │   ├── CheckItem.tsx
│   │   │   └── ChecklistPanel.tsx
│   │   └── ui/                       # shadcn/ui 组件
│   ├── lib/
│   │   ├── assistant/
│   │   │   ├── runtime.ts            # 自定义 assistant-ui 运行时
│   │   │   ├── adapter.ts            # 后端 SSE 适配器
│   │   │   └── tool-ui.tsx           # 自定义工具 UI 组件
│   │   ├── pdf/
│   │   │   ├── viewer.ts             # PDF.js 集成
│   │   │   └── coordinates.ts        # 坐标转换
│   │   └── api/
│   │       └── client.ts             # API 客户端
│   └── types/
│       ├── workspace.ts
│       ├── document.ts
│       ├── evidence.ts
│       └── events.ts                 # SSE 事件类型
├── public/
│   └── pdf.worker.js                 # PDF.js worker
└── tests/
    └── components/
```

## 核心技术

- **Next.js 14**: App router, 服务端组件
- **React 18**: UI 库
- **TypeScript**: 类型安全
- **Tailwind CSS**: 样式
- **shadcn/ui**: UI 组件
- **assistant-ui**: AI 对话界面
- **PDF.js**: PDF 渲染

## 开发

运行测试：
```bash
npm test
```

构建：
```bash
npm run build
```

代码检查：
```bash
npm run lint
```

类型检查：
```bash
npm run type-check
```

## 环境变量

详见 `../.env.example` 中的配置。

关键变量：
- `NEXT_PUBLIC_API_URL`: 后端 API 地址
- `NEXT_PUBLIC_WS_URL`: WebSocket 地址（用于 SSE）
