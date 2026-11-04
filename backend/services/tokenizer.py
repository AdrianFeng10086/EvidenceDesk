"""中文/英文混合分词，用于 BM25 与本地哈希向量。

首版不依赖第三方分词器，使用可复现的字符 n-gram 方案：

- 中文连续片段：单字 + 相邻二元组 + 2~8 字的完整片段
- 英文/数字：按连续字母数字切分并转小写
- 去掉高频疑问词和虚词，避免“什么/多少/是否”抢占 BM25 权重

选择二元组而不是词典分词，是为了让“住宿费标准”“住宿标准”这类
没有空格的中文表达也能稳定产生重叠词项；分词版本会写入索引配置。
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

TOKENIZER_VERSION = "cjk-uni-bigram-v1"

CJK_RUN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")
ASCII_TERM_RE = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*")

# 单字虚词/疑问词，以及常见问句短语
STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "及",
    "或",
    "为",
    "对",
    "把",
    "被",
    "有",
    "无",
    "吗",
    "呢",
    "啊",
    "呀",
    "什么",
    "多少",
    "怎么",
    "如何",
    "哪些",
    "哪个",
    "是否",
    "可以",
    "需要",
    "请问",
    "一下",
    "分别",
    "时候",
    "多久",
    "多长",
    "几项",
    "哪些",
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "or",
    "is",
    "are",
    "what",
    "which",
    "how",
}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize(text: str) -> List[str]:
    """返回保留重复次数的词项列表（BM25 需要词频）。"""
    normalized = _normalize(text)
    tokens: List[str] = []

    for run in CJK_RUN_RE.findall(normalized):
        if len(run) == 1:
            if run not in STOPWORDS:
                tokens.append(run)
            continue

        # 单字：仅保留非虚词，帮助处理单字实体（如“床”）
        for char in run:
            if char not in STOPWORDS:
                tokens.append(char)

        # 相邻二元组：中文检索的主要信号
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in STOPWORDS:
                tokens.append(bigram)

        # 较短完整片段本身也可能是术语（如“延保”“发票”）
        if 2 <= len(run) <= 8 and run not in STOPWORDS:
            tokens.append(run)

    for term in ASCII_TERM_RE.findall(normalized):
        if term in STOPWORDS:
            continue
        if len(term) >= 2 or term.isdigit():
            tokens.append(term)

    return tokens


def query_terms(text: str) -> List[str]:
    """查询词项去重并保持稳定顺序。"""
    seen = set()
    result: List[str] = []
    for token in tokenize(text):
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def tokenized_corpus(texts: List[str]) -> List[List[str]]:
    return [tokenize(text) for text in texts]
