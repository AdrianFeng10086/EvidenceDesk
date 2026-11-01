"""三种不同布局 PDF 的原文、页码与文字框核对。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import fixtures
from tests.helpers import upload_pdf


def _upload(client, workspace_id: str, name: str, path: Path) -> tuple[str, dict]:
    response = upload_pdf(client, workspace_id, name, path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]
    detail_response = client.get(f"/api/documents/{version_id}")
    assert detail_response.status_code == 200, detail_response.text
    return version_id, detail_response.json()


def _page(client, version_id: str, page: int = 1) -> dict:
    response = client.get(f"/api/documents/{version_id}/content", params={"page": page})
    assert response.status_code == 200, response.text
    return response.json()


def _assert_span_mapping(page: dict) -> None:
    text = page["text"]
    for span in page["spans"]:
        assert text[span["char_start"] : span["char_end"]] == span["text"]
        for box in span["bboxes"]:
            assert 0 <= box["x0"] < box["x1"] <= box["page_width"]
            assert 0 <= box["y0"] < box["y1"] <= box["page_height"]
            # 每个文字框覆盖的字符范围必须落在片段文本内，且与页面原文一致
            covered = text[box["char_start"] : box["char_end"]]
            assert covered
            assert covered in span["text"]
            assert len(covered) <= box["char_end"] - box["char_start"]


def test_single_column_pdf_text_pages_and_boxes(client, workspace_id, fixture_dir):
    path = fixtures.make_single_column_pdf(fixture_dir / "single-column.pdf")
    version_id, detail = _upload(client, workspace_id, "单栏指南.pdf", path)

    version = detail["version"]
    assert version["parse_status"] == "success"
    assert version["support_level"] == "full"
    assert version["page_count"] == 2
    assert detail["parse_job"]["status"] == "success"
    assert len(detail["pages"]) == 2

    page = _page(client, version_id, 1)
    assert fixtures.HEADING in page["text"]
    assert fixtures.BODY_1 in page["text"]
    assert fixtures.BODY_2 in page["text"]
    assert page["width"] and page["width"] > 500
    assert page["height"] and page["height"] > 700
    _assert_span_mapping(page)

    kinds = {span["kind"] for span in page["spans"]}
    assert "heading" in kinds
    assert "list_item" in kinds

    heading = next(span for span in page["spans"] if span["text"] == fixtures.HEADING)
    assert heading["kind"] == "heading"
    assert heading["bboxes"], "标题应保留文字框"
    assert heading["bboxes"][0]["page_width"] == pytest.approx(page["width"], abs=0.1)

    paragraph = next(
        span
        for span in page["spans"]
        if fixtures.BODY_1 in span["text"] and fixtures.BODY_2 in span["text"]
    )
    assert paragraph["kind"] == "paragraph"
    assert len(paragraph["bboxes"]) >= 2, "跨行段落应为每一行保留文字框"

    page2 = _page(client, version_id, 2)
    assert fixtures.PAGE_2_HEADING in page2["text"]
    assert fixtures.PAGE_2_BODY in page2["text"]
    _assert_span_mapping(page2)


def test_two_column_pdf_is_marked_restricted(client, workspace_id, fixture_dir):
    path = fixtures.make_two_column_pdf(fixture_dir / "two-column.pdf")
    version_id, detail = _upload(client, workspace_id, "双栏指南.pdf", path)

    version = detail["version"]
    assert version["parse_status"] == "success"
    assert version["support_level"] == "restricted"
    codes = {warning["code"] for warning in version["warnings"]}
    assert "LAYOUT_MULTI_COLUMN" in codes

    page = _page(client, version_id, 1)
    assert fixtures.LEFT_LINES[0] in page["text"]
    assert fixtures.RIGHT_LINES[0] in page["text"]
    assert page["spans"]
    # 布局不可靠时退回逐行片段，不伪装为可靠的段落切分
    assert {span["kind"] for span in page["spans"]} == {"line"}
    _assert_span_mapping(page)


def test_table_pdf_is_restricted_but_text_is_kept(client, workspace_id, fixture_dir):
    path = fixtures.make_table_pdf(fixture_dir / "table.pdf")
    version_id, detail = _upload(client, workspace_id, "申报信息表.pdf", path)

    version = detail["version"]
    assert version["parse_status"] == "success"
    assert version["support_level"] == "restricted"
    codes = {warning["code"] for warning in version["warnings"]}
    assert "LAYOUT_TABLES" in codes

    page = _page(client, version_id, 1)
    assert fixtures.TABLE_TEXT in page["text"]
    assert fixtures.TABLE_VALUE in page["text"]
    assert page["spans"]
    _assert_span_mapping(page)
