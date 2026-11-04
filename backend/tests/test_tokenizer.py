"""中文 BM25 分词验证。"""

from __future__ import annotations

from services.tokenizer import TOKENIZER_VERSION, query_terms, tokenize


def test_chinese_query_produces_content_bigrams_and_drops_question_words():
    terms = query_terms("员工手机话费补贴的上限是多少")
    assert "手机" in terms
    assert "话费" in terms
    assert "补贴" in terms
    assert "上限" in terms
    assert "多少" not in terms
    assert "什么" not in terms
    assert TOKENIZER_VERSION


def test_mixed_chinese_ascii_and_numbers_are_tokenized():
    terms = tokenize("单笔 2000 元 OA 审批需要部门总监")
    assert "2000" in terms
    assert "oa" in terms
    assert "审批" in terms
    assert "部门" in terms


def test_punctuation_and_whitespace_do_not_create_empty_terms():
    terms = query_terms("？。！  \n\t")
    assert terms == []
