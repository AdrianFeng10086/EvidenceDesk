# 开发进度记录

## 2026-11-03 / Day 5：检索链路

今日完成的用户能力：

- 文档解析成功后自动分块、嵌入并写入 Chroma；索引状态与解析状态分开记录。
- `retrieve_evidence(case_id)` 以 Case 固定范围检索，可同时引用多个资料空间的版本。
- 支持空间、版本、文档、文件类型、片段类型、适用范围、删除状态过滤。
- 向量召回基线 + 中文 BM25 + RRF 融合；结果返回真实片段、空间名、版本与稳定 chunk/span ID。
- 空结果区分 `NO_SCOPE / ALL_SOURCES_DELETED / SOURCES_UNAVAILABLE /
  INDEX_NOT_READY / FILTERED_OUT / NO_SEARCHABLE_CONTENT / NO_MATCH`。
- 文档删除后立即从向量与候选块移除；历史检索日志按当前来源状态标注“已删除/不可用”。
- Case 范围变更后旧 Run 标记 `stale`；新增 Case、范围、检索、索引状态、日志与重建接口。
- 新增中文 BM25 分词验证与开发集召回记录（24 题，融合 Hit@5 = 1.000）。

对应文档：

- [Day 5 实现说明](day5-implementation.md)
- [API 规范](api-spec.md)

实际运行的检查及结果：

```bash
cd backend && python -m pytest tests -q
# 51 passed

cd backend && python scripts/evaluate_retrieval.py
# 融合 Hit@1=0.667 Hit@5=1.000 MRR=0.823
# 向量基线 Hit@1=0.500 Hit@5=0.958 MRR=0.715

cd backend && python scripts/evaluate_retrieval.py --provider cloudflare \
  --model @cf/baai/bge-m3 --dimension 1024 \
  --output ../data/eval/day5-dev-recall-cloudflare.json
# 融合 Hit@1=0.542 Hit@5=1.000 MRR=0.735
# 向量基线 Hit@1=0.417 Hit@5=0.875 MRR=0.615
```

发现的错误或失败案例：

- Chroma 集合初始化时嵌套获取非重入锁导致死锁，已改为 `RLock`。
- 纯文本样例中的 Markdown/中文序号标题原被当成普通段落，导致“申报材料”
  等列表项丢失章节词；分块阶段补充标题识别并写入 `section_title`。
- 向量最近邻总会返回结果，已增加“多字词项命中或相似度阈值”判断，避免把
  无关最近邻当成证据。

当前限制：

- 本地哈希向量只用于离线测试；生产效果以 Cloudflare `@cf/baai/bge-m3` 记录为准。
- 相似度阈值与 RRF 权重尚未在保留集上系统调参。
- 表格仍按整表片段检索，单元格级引用留到后续版本对照。

下一步最重要的一个任务：

- 基于 `retrieve_evidence` 与真实 EvidenceSpan 进入 Day 6 带证据回答，
  让每条结论只引用检索返回的稳定 span ID。

## 2026-11-02 / Day 1–4 修补

今日完成的用户能力：

- 补齐资料空间、Case 检索范围、文档/空间删除状态、来源墓碑的数据模型。
- 文档支持软删除、回收站、恢复、删除影响展示；删除后列表、详情、原文与检索立即不可用。
- 同名文件软删除后重传会恢复原文档并追加版本或复用同哈希版本，不触发唯一约束。
- 三个开发样例补齐自建演示文档，并按 8 个开发问题 + 12 个保留问题完成划分。
- 模型连通性验证：LLM 可用；Cloudflare embedding（`@cf/baai/bge-m3`，1024 维）可用；当前视觉模型不支持图片输入，视觉证据能力待 Day 11 换模型。

对应提交：

- 待提交（本轮修改尚未 commit）。

实际运行的检查及结果：

```bash
cd backend && python -m pytest tests -q
# 38 passed

cd frontend && npm run type-check
# 通过

cd frontend && npm run test:coordinates
# 10 passed

cd frontend && npm run build
# 编译、Lint、类型检查与静态生成通过
```

浏览器冒烟（Chrome + Playwright，真实后端 + Next dev）：

- 选中文档 → 打开删除影响弹窗 → 确认删除 → 列表移除且阅读器清空 → 回收站显示“已删除” → 恢复后文档回到列表。通过。

模型验证：

```bash
cd backend && PYTHONIOENCODING=utf-8 python verify_models.py
# LLM: deepseek-flash OK
# Embedding: @cf/baai/bge-m3 OK (1024)
# Vision: 当前 deepseek-flash 不支持图片输入（非阻断）
```

发现的错误或失败案例：

- 上一轮“原始文件缺失就隐藏文档”的热补丁已移除，改为显式软删除状态。
- 当前视觉模型不可用，Day 11 前需要换用支持图片输入的模型，否则视觉证据框无法验证。
- 真实可核实案例尚未取得；三个样例均为自建演示规则，已在文件与 `source.md` 中标注。

当前限制：

- Day 5 尚未接入 Chroma 向量索引与 BM25；当前检索仍是关键词召回。
- 工作空间硬删除、保留期自动清理任务尚未实现（Day 13）。
- Case CRUD 与检索范围 API 尚未实现（Day 5–8），当前先落数据模型。

下一步最重要的一个任务：

- 按 Day 5 实现 `retrieve_evidence(case_id)`、Chroma 索引、空间/版本/类型/适用范围/删除状态过滤与检索日志。
