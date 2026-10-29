# 有据 EvidenceDesk

面向需要依据文档作出决定的人，提供"问题—结论—证据—条件核查—人工确认"的可视化工作台。

## 产品定位

用户可以是项目申报负责人、企业制度执行者、采购或服务条款核对人员等。界面和数据结构不绑定单一行业。

首版用三个案例验证同一套流程：

- 项目申报条件
- 费用报销制度
- 设备保修或服务条款

## 核心能力

- **精确引用定位**：点击引用跳转到原文并高亮具体位置
- **引用完整性校验**：验证每条结论是否有真实文档证据支持
- **条件核对清单**：根据文档规则与用户事实自动生成核对项
- **缺失信息补问**：识别缺少的关键事实，避免擅自判断
- **版本与条款对照**：比较不同文档版本或适用范围
- **视觉证据框**：支持对 PDF 页面截图标注关键证据位置
- **可追溯报告**：导出带证据链的核验报告

## 技术架构

### 前端

- **框架**：Next.js + React + TypeScript
- **UI**：Tailwind CSS + shadcn/ui
- **AI 交互**：assistant-ui (自定义 Runtime/Adapter)
- **PDF 渲染**：PDF.js
- **布局**：三栏工作台（文件列表 | 对话与清单 | 文档阅读器）

### 后端

- **API**：FastAPI (Python)
- **文档解析**：pdfplumber (抽取文本与坐标)
- **检索**：Chroma (向量) + BM25 (关键词)
- **元数据**：SQLite
- **AI 模型**：支持结构化输出、工具调用和图像输入的模型

## 快速开始

### 环境要求

- Node.js >= 18
- Python >= 3.10
- Git

### 安装步骤

1. 克隆仓库

```bash
git clone <repository-url>
cd evidence-desk
```

2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填写必要的 API 密钥
```

3. 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

5. 访问 http://localhost:3000

### 开发样例

开发样例位于 `data/examples/` 目录：

- `project-application/`：项目申报条件
- `expense-reimbursement/`：费用报销制度
- `warranty-service/`：设备保修或服务条款

每个样例包含：

- 文档文件（PDF/TXT）
- 来源说明（source.md）
- 开发测试问题（dev-questions.md）
- 保留测试问题（eval-questions.md）

## 项目状态

**当前版本**：v0.1.0-dev (Day 2)

**完成进度**：

- [X] Day 1: 项目初始化与范围定义
- [X] Day 2: 三栏工作台与流式对话
- [ ] Day 3: 文档导入与解析
- [ ] Day 4: 精确高亮定位
- [ ] Day 5: 检索链路
- [ ] Day 6: 带证据回答
- [ ] Day 7: 引用校验
- [ ] Day 8: 条件核对与补问
- [ ] Day 9: 工具调用工作流
- [ ] Day 10: 版本对照与报告导出
- [ ] Day 11: 视觉证据框
- [ ] Day 12: 评估与用户测试
- [ ] Day 13: 部署与修复
- [ ] Day 14: 技术文档与演示视频
- [ ] Day 15: 最终验收

## 技术文档

详细设计文档位于 `docs/` 目录：

- [产品范围](docs/product-scope.md)
- [系统架构](docs/architecture.md)
- [数据模型](docs/data-model.md)
- [API 规范](docs/api-spec.md)
- [开发进度](docs/progress.md)

## 限制与约束

**首版限制**：

- 每个资料空间最多 10 个文件
- 单个 PDF 最多 30 页、10 MB
- 仅支持带文字层的 PDF、TXT、Markdown
- 加密或损坏的 PDF 会返回明确错误状态

## 团队信息

- 开发团队：[待填写]
- 联系方式：[待填写]
- 比赛信息：2024 年度人工智能赛道

## 许可说明

本项目使用的第三方组件：

- assistant-ui: Apache-2.0 License
- PDF.js: Apache-2.0 License
- shadcn/ui: MIT License
- 其他依赖详见 package.json 和 requirements.txt

## 致谢

- 基础 UI 组件参考 assistant-ui 项目
- 比赛指导与真实案例来源：[待填写]
