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
│   │   │   ├── EvidenceCard.tsx      # 可折叠的证据来源与定位入口
│   │   │   ├── DocumentViewer.tsx    # 右侧面板：PDF / 文本阅读器
│   │   │   └── WorkspaceLayout.tsx   # 三栏布局
│   │   ├── evidence/
│   │   │   ├── PdfPageView.tsx       # PDF.js canvas 渲染
│   │   │   ├── HighlightOverlay.tsx  # 红色实线证据矩形
│   │   │   └── DocumentReference.tsx # assistant-ui 页级后备引用
│   │   ├── checklist/
│   │   │   ├── CheckItem.tsx
│   │   │   └── ChecklistPanel.tsx
│   │   └── ui/                       # shadcn/ui 组件
│   ├── lib/
│   │   ├── pdf/
│   │   │   └── coordinates.ts        # PDF 点 -> CSS 像素坐标转换
│   │   ├── evidence/
│   │   │   ├── location-status.ts    # 定位状态文案与配色
│   │   │   └── text-range.ts         # 段落 / 行范围
│   │   └── stores/
│   │       └── evidence-locator.ts   # 证据定位状态（zustand）
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
# 坐标换算（75/100/150%、面板尺寸、旋转、镜像回归）与文本行范围
npm run test:coordinates
```

PDF.js worker 由 `scripts/copy-pdf-worker.mjs` 在 `postinstall`、`predev`、
`prebuild` 时复制到 `public/pdf.worker.min.mjs`，不依赖 CDN。

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
