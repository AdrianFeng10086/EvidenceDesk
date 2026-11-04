# 开发集检索召回记录

## 文件

- `dev_retrieval_ground_truth.json`：24 个开发问题（三个样例各 8 个）及人工期望词项。
  命中定义为 Top-K 结果文本包含任一期望词项（忽略空白）。保留集问题不在此处。
- `day5-dev-recall.json`：本地确定性哈希向量（256 维）的召回记录，可离线复现。
- `day5-dev-recall-cloudflare.json`：当前配置的真实嵌入模型
  `@cf/baai/bge-m3`（1024 维）的召回记录。

每份记录都保存 `index_version`、嵌入提供方/模型/维度、分块策略、
分词器版本、融合策略、逐题 Top-K 结果以及向量基线与融合结果的对比。

## 复现

```bash
cd backend
python scripts/evaluate_retrieval.py

python scripts/evaluate_retrieval.py --provider cloudflare \
  --model @cf/baai/bge-m3 --dimension 1024 \
  --output ../data/eval/day5-dev-recall-cloudflare.json
```

脚本使用临时数据库、上传目录与 Chroma 目录，不修改开发数据。
